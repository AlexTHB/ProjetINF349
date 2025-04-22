from flask import Flask, jsonify, request, render_template, Response, redirect, url_for
from models import db, Product, Order, OrderProduct
from peewee import DoesNotExist
import requests
from collections import OrderedDict
import json
from flask.cli import with_appcontext
import click
import redis
import os
from rq import Queue, Worker  
from rq.job import Job

app = Flask(__name__)
API_URL = "http://dimensweb.uqac.ca/~jgnault/shops/products/"
PAYMENT_API = "https://dimensweb.uqac.ca/~jgnault/shops/pay/"

redis_url = os.environ['REDIS_URL']
redis_conn = redis.from_url(redis_url)
redis_client = redis_conn  # Alias pour la compatibilité
q = Queue(connection=redis_conn)

def init_db():
    db.connect()
    db.create_tables([Product, Order, OrderProduct], safe=True)
    if Product.select().count() == 0:
        response = requests.get(API_URL)
        products = response.json().get("products", [])
        for p in products:
            Product.create(**p)

def process_payment_task(order_id, credit_card_data):
    from app import db
    try:
        order = Order.get_by_id(order_id)

        if order.paid:
            return False

        with db.atomic():
            # Sauvegarder infos carte
            card_number = credit_card_data["number"].replace(" ", "")
            order.credit_card_name = credit_card_data["name"]
            order.credit_card_first_digits = card_number[:4]
            order.credit_card_last_digits = card_number[-4:]
            order.credit_card_expiration_year = credit_card_data["expiration_year"]
            order.credit_card_expiration_month = credit_card_data["expiration_month"]

            # Préparer la requête vers le service de paiement
            payload = {
                "credit_card": {
                    "name": credit_card_data["name"],
                    "number": " ".join(credit_card_data["number"][i:i+4] for i in range(0, len(credit_card_data["number"]), 4)),
                    "expiration_year": credit_card_data["expiration_year"],
                    "expiration_month": credit_card_data["expiration_month"],
                    "cvv": credit_card_data["cvv"]
                },
                "amount_charged": round(order.total_price_tax + order.shipping_price)
            }

            print("PAYMENT API PAYLOAD:", json.dumps(payload, indent=2))

            # Envoyer la requête à l'API
            response = requests.post(PAYMENT_API, json=payload, headers={"Content-Type": "application/json"})
            payment_data = response.json()

            # Si le paiement est une réussite
            success = payment_data.get("transaction", {}).get("success", False)

            # Mise à jour de la commande peu importe succès/échec
            order.transaction = json.dumps(payment_data.get("transaction", {}))
            order.paid = success
            order.payment_status = "completed" if success else "failed"
            order.save()

            # Cacher ou afficher les données de carte
            if success:
                credit_card_info = {
                    "name": order.credit_card_name,
                    "first_digits": order.credit_card_first_digits,
                    "last_digits": order.credit_card_last_digits,
                    "expiration_year": order.credit_card_expiration_year,
                    "expiration_month": order.credit_card_expiration_month
                }
            else:
                # ➔ Si paiement échoué : cacher carte de crédit
                credit_card_info = {}

            # Préparer les produits
            products = []
            for op in order.order_products:
                products.append({
                    "id": op.product.id,
                    "quantity": op.quantity
                })

            # Informations livraison
            shipping_information = json.loads(order.shipping_information) if order.shipping_information else None

            # Nouvelle donnée mise en cache
            cached_order_data = {
                "shipping_information": shipping_information,
                "email": order.email,
                "total_price": order.total_price,
                "total_price_tax": order.total_price_tax,
                "paid": order.paid,
                "products": products,
                "credit_card": credit_card_info,
                "transaction": payment_data.get("transaction", {}),
                "shipping_price": order.shipping_price,
                "id": order.id
            }

            # Sauvegarde dans Redis
            redis_client.set(f"order:{order.id}", json.dumps(cached_order_data))

        return True

    except Exception as e:
        Order.update(
            payment_status=f"failed: {str(e)}",
            paid=False
        ).where(Order.id == order_id).execute()
        return False



@app.cli.command("init-db")
@with_appcontext
def initialize_database():
    """Initialise la base de données."""
    init_db()
    click.echo("Base de données initialisée.")

@app.cli.command("worker")
@with_appcontext
def run_worker():
    """Démarre le worker RQ"""
    worker = Worker(
        [q],  # <-- Liste des queues à surveiller
        connection=redis_conn,
        name=f"worker_{os.getpid()}"
    )
    worker.work()


def calculate_shipping(weight):
    if weight <= 500: return 500
    elif weight <= 2000: return 1000
    else: return 2500

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/products", methods=["GET"])
def get_products():
    products = [p.__data__ for p in Product.select()]
    return jsonify({"products": products})

@app.route("/order", methods=["POST"])
def create_order():
    data = request.get_json()
    
    # Rétrocompatibilité partie 1
    if "product" in data:
        products_data = [data["product"]]
    elif "products" in data:
        products_data = data["products"]
    else:
        return jsonify({
            "errors": {
                "product": {
                    "code": "missing-fields",
                    "name": "Format de commande invalide (manque 'product' ou 'products')"
                }
            }
        }), 422

    total_price = 0
    total_weight = 0
    order_products = []
    
    for idx, product_data in enumerate(products_data, start=1):
        # Validation des champs obligatoires
        if "id" not in product_data or "quantity" not in product_data:
            return jsonify({
                "errors": {
                    f"product_{idx}": {
                        "code": "missing-fields",
                        "name": "Champs 'id' ou 'quantity' manquants"
                    }
                }
            }), 422
        
        # Validation de l'existence du produit
        try:
            product = Product.get(Product.id == product_data["id"])
        except DoesNotExist:
            return jsonify({
                "errors": {
                    f"product_{idx}": {
                        "code": "missing-fields",
                        "name": f"Le produit {product_data['id']} n'existe pas"
                    }
                }
            }), 422
        
        # Validation du stock
        if not product.in_stock:
            return jsonify({
                "errors": {
                    f"product_{idx}": {
                        "code": "out-of-inventory",
                        "name": f"Le produit {product.id} n'est pas en inventaire"
                    }
                }
            }), 422
        
        # Validation de la quantité
        try:
            quantity = int(product_data["quantity"])
            if quantity < 1:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({
                "errors": {
                    f"product_{idx}": {
                        "code": "invalid-quantity",
                        "name": "La quantité doit être un entier supérieur à 0"
                    }
                }
            }), 422

        total_price += product.price * quantity
        total_weight += product.weight * quantity
        order_products.append((product, quantity))

    # Création de la commande
    order = Order.create(
        total_price=total_price,
        shipping_price=calculate_shipping(total_weight),
        paid=False
    )
    
    # Ajout des produits
    for product, quantity in order_products:
        OrderProduct.create(
            order=order,
            product=product,
            quantity=quantity
        )

    return redirect(url_for('get_order', order_id=order.id)), 302

@app.route("/order/<int:order_id>", methods=["GET"])
def get_order(order_id):
    # Vérifier si un paiement est en cours
    payment_job_key = f"payment:{order_id}"
    job_id = redis_client.get(payment_job_key)
    
    if job_id:
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            if not job.is_finished:
                return Response(status=202)  # Paiement en cours
        except Exception:
            redis_client.delete(payment_job_key)

    # Vérifier le cache Redis (corriger la parenthèse manquante)
    order_cache_key = f"order:{order_id}"
    cached_order = redis_client.get(order_cache_key)
    if cached_order:
        return Response(
            json.dumps({"order": json.loads(cached_order)}),  # <-- Correction ici
            mimetype='application/json'
        )

    try:
        order = Order.get_by_id(order_id)
    except DoesNotExist:
        return jsonify({
            "errors": {
                "order": {
                    "code": "not-found",
                    "name": "Commande introuvable"
                }
            }
        }), 404

    # Récupération des produits associés
    products = []
    for op in order.order_products:  
        products.append({
            "id": op.product.id,
            "quantity": op.quantity
        })

    # Construction de l'objet credit_card
    credit_card = None
    if order.credit_card_name:
        credit_card = {
            "name": order.credit_card_name,
            "first_digits": order.credit_card_first_digits,
            "last_digits": order.credit_card_last_digits,
            "expiration_year": order.credit_card_expiration_year,
            "expiration_month": order.credit_card_expiration_month
        }

    # Conversion de shipping_information
    shipping_information = json.loads(order.shipping_information) if order.shipping_information else None

    # Construction de transaction
    transaction = json.loads(order.transaction) if order.transaction else None

    # Nouvelle structure avec 'products'
    order_data = OrderedDict([
        ("shipping_information", shipping_information),
        ("email", order.email),
        ("total_price", order.total_price),
        ("total_price_tax", order.total_price_tax),
        ("paid", order.paid),
        ("products", products),  
        ("credit_card", credit_card),
        ("transaction", transaction),
        ("shipping_price", order.shipping_price),
        ("id", order.id)
    ])

    response_data = OrderedDict([("order", order_data)])

    return Response(
        json.dumps(response_data, ensure_ascii=False, sort_keys=False),
        mimetype='application/json'
    )


@app.route("/order/<int:order_id>", methods=["PUT"])
def update_order(order_id):
    data = request.get_json()
    
    try:
        order = Order.get_by_id(order_id)
    except DoesNotExist:
        return jsonify({
            "errors": {
                "order": {
                    "code": "not-found",
                    "name": "Commande introuvable"
                }
            }
        }), 404

    # Vérification qu'un seul des champs 'order' ou 'credit_card' est présent
    has_order = 'order' in data
    has_credit_card = 'credit_card' in data
    if has_order == has_credit_card:  # Les deux présents ou aucun
        return jsonify({
            "errors": {
                "system": {
                    "code": "invalid-request",
                    "name": "La requête doit contenir soit 'order' soit 'credit_card', mais pas les deux."
                }
            }
        }), 422

    if has_order:
        required_fields = {
            "email": "Email",
            "shipping_information.country": "Pays",
            "shipping_information.address": "Adresse",
            "shipping_information.postal_code": "Code postal",
            "shipping_information.city": "Ville",
            "shipping_information.province": "Province"
        }

        missing_fields = []
        
        # Vérification des champs principaux
        if "email" not in data["order"] or not data["order"]["email"].strip():
            missing_fields.append("email")
        
        # Vérification des sous-champs de shipping_information
        shipping_info = data["order"].get("shipping_information", {})
        for field in ["country", "address", "postal_code", "city", "province"]:
            if not shipping_info.get(field, "").strip():
                missing_fields.append(f"shipping_information.{field}")

        if missing_fields:
            return jsonify({
                "errors": {
                    "order": {
                        "code": "missing-fields",
                        "name": "Il manque un ou plusieurs champs qui sont obligatoires",
                        "fields": [required_fields[field] for field in missing_fields]
                    }
                }
            }), 422

        # Mise à jour des informations
        order.email = data["order"]["email"]
        order.shipping_information = json.dumps(shipping_info)

        # Calcul des taxes
        tax_rates = {
            "QC": 0.15,
            "ON": 0.13,
            "AB": 0.05,
            "BC": 0.12,
            "NS": 0.14
        }
        province = shipping_info["province"]
        order.total_price_tax = round(order.total_price * (1 + tax_rates.get(province, 0)), 2)
        order.save()

    # Partie traitement du paiement
    elif has_credit_card:
        # Validation pré-paiement
        if not order.email or not order.shipping_information:
            return jsonify({
                "errors": {
                    "order": {
                        "code": "missing-fields",
                        "name": "Les informations du client sont nécessaire avant d'appliquer une carte de crédit"
                    }
                }
            }), 422

        if order.paid:
            return jsonify({
                "errors": {
                    "order": {
                        "code": "already-paid",
                        "name": "La commande est déjà payée"
                    }
                }
            }), 422

        # Extraction des données de la carte
        credit_card = data["credit_card"]
        card_number = credit_card["number"].replace(" ", "")
    
        # Validation des numéros de test autorisés
        if card_number not in ["4242424242424242", "4000000000000002"]:
            return jsonify({
                "errors": {
                    "credit_card": {
                        "code": "incorrect-number",
                        "name": "Numéro de carte invalide"
                    }
                }
            }), 422
        
        if card_number == "4000000000000002":
            return jsonify({
                "errors": {
                    "credit_card": {
                        "code": "card-declined",
                        "name": "La carte de crédit a été déclinée."
                    }
                }
            }), 422

        

        # Appel à l'API de paiement
        #payload = {"credit_card": credit_card, "amount_charged": round(order.total_price_tax + order.shipping_price)}
        

        # Récupérer les produits associés
        products = []
        for op in order.order_products:
            products.append({
                "id": op.product.id,
                "quantity": op.quantity
            })
        
        # Remplacer par la gestion de la file d'attente
        try:
            # Formater correctement le numéro de carte
            credit_card_data = credit_card.copy()
            credit_card_data["number"] = credit_card_data["number"].replace(" ", "")

            # Vérifier les doublons de paiement
            if redis_client.exists(f"payment:{order_id}"):
                return jsonify({
                    "errors": {
                        "order": {
                            "code": "payment-pending",
                            "name": "Un paiement est déjà en cours"
                        }
                    }
                }), 409

            # Envoyer la tâche en arrière-plan
            job = q.enqueue(
                process_payment_task,
                order_id,
                credit_card_data,
                job_id=f"payment_{order_id}",
                job_timeout=300,
                result_ttl=3600
            )
            
            # Stocker l'état temporaire
            redis_client.set(f"payment:{order_id}", job.id, ex=600)
            order.payment_status = "processing"
            order.save()

            return Response(status=202)  # Réponse immédiate

        except Exception as e:
            redis_client.delete(f"payment:{order_id}")
            return jsonify({
                "errors": {
                    "system": {
                        "code": "queue-error",
                        "name": f"Erreur système: {str(e)}"
                    }
                }
            }), 500


if __name__ == "__main__":
    app.run(debug=True)