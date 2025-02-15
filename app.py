from flask import Flask, jsonify, request, render_template, Response, redirect, url_for
from models import db, Product, Order
from peewee import DoesNotExist
import requests
from collections import OrderedDict
import json
from flask.cli import with_appcontext
import click

app = Flask(__name__)
API_URL = "http://dimensweb.uqac.ca/~jgnault/shops/products/"
PAYMENT_API = "https://dimensweb.uqac.ca/~jgnault/shops/pay/"

def init_db():
    db.connect()
    db.create_tables([Product, Order], safe=True)
    if Product.select().count() == 0:
        response = requests.get(API_URL)
        products = response.json().get("products", [])
        for p in products:
            Product.create(**p)
    db.close()

@app.cli.command("init-db")
@with_appcontext
def initialize_database():
    """Initialise la base de données."""
    init_db()
    click.echo("Base de données initialisée.")

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
    
    if "product" not in data or "id" not in data["product"] or "quantity" not in data["product"]:
        return jsonify({"errors": {"product": {"code": "missing-fields", "name": "Champs manquants"}}}), 422
    
    try:
        product = Product.get(Product.id == data["product"]["id"])
    except DoesNotExist:
        return jsonify({"errors": {"product": {"code": "missing-fields", "name": "La création d'une commande nécessite un produit"}}}), 422

    if not product.in_stock:
        return jsonify({"errors": {"product": {"code": "out-of-inventory", "name": "Le produit demandé n'est pas en inventaire"}}}), 422
    
    try:
        quantity = int(data["product"]["quantity"])
    except (ValueError, TypeError):
        return jsonify({
            "errors": {
                "product": {
                    "code": "invalid-quantity",
                    "name": "La quantité doit être un nombre entier"
                }
            }
        }), 422
    
    if quantity < 1 :
        return jsonify({"errors": {"product": {"code": "missing-fields", "name": "La quantite doit etre superieure ou egal a 1"}}}), 422

    order = Order.create(
        product_id=product.id,
        quantity=data["product"]["quantity"],
        total_price=product.price * data["product"]["quantity"] * 100,
        shipping_price=calculate_shipping(product.weight * data["product"]["quantity"])
    )

    return redirect(url_for('get_order', order_id=order.id)), 302

@app.route("/order/<int:order_id>", methods=["GET"])
def get_order(order_id):
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

    # Construction de l'objet credit_card si des informations sont présentes
    credit_card = None
    if order.credit_card_name:
        credit_card = {
            "name": order.credit_card_name,
            "first_digits": order.credit_card_first_digits,
            "last_digits": order.credit_card_last_digits,
            "expiration_year": order.credit_card_expiration_year,
            "expiration_month": order.credit_card_expiration_month
        }

    # Conversion de shipping_information si disponible
    shipping_information = json.loads(order.shipping_information) if order.shipping_information else None

    # Construction de l'objet transaction si applicable
    transaction = None
    if order.transaction_id:
        transaction = OrderedDict([
            ("id", order.transaction_id),
            ("success", order.paid),
            ("amount_charged", round(order.total_price_tax + order.shipping_price))
        ])

    # Construction de l'objet order avec l'ordre de clés souhaité
    order_data = OrderedDict([
        ("shipping_information", shipping_information),
        ("email", order.email),
        ("total_price", order.total_price),
        ("total_price_tax", order.total_price_tax),
        ("paid", order.paid),
        ("product", {"id": order.product_id, "quantity": order.quantity}),
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

        credit_card["number"] = " ".join(credit_card["number"][i:i+4] for i in range(0, len(credit_card["number"]), 4))

        # Appel à l'API de paiement
        payload = {"credit_card": credit_card, "amount_charged": round(order.total_price_tax + order.shipping_price)}
        
        try:
            response = requests.post(PAYMENT_API, json=payload, headers={"Content-Type": "application/json"})
            response.raise_for_status()
            payment_data = response.json()
        except requests.exceptions.RequestException as e:
            return jsonify({
                "errors": {
                    "payment": {
                        "code": "card-declined",
                        "name": "la carte est expirée."
                    }
                }
            }), 502
        except json.JSONDecodeError:
            return jsonify({
                "errors": {
                    "payment": {
                        "code": "card-declined",
                        "name": "Réponse invalide du processeur de paiement"
                    }
                }
            }), 502

        if "transaction" not in payment_data:
            return jsonify({
                "errors": {
                    "payment": {
                        "code": "card-declined",
                        "name": "La transaction n'a pas été enregistrée."
                    }
                }
            }), 502

        # Mise à jour finale après le paiement
        order.credit_card_name = credit_card["name"]
        order.credit_card_first_digits = card_number[:4]
        order.credit_card_last_digits = card_number[-4:]
        order.credit_card_expiration_year = int(credit_card["expiration_year"])
        order.credit_card_expiration_month = int(credit_card["expiration_month"])
        order.transaction_id = payment_data["transaction"]["id"]
        order.paid = True
        order.save()

    # Construction de la réponse
    credit_card_info = None
    if order.credit_card_name:
        credit_card_info = {
            "name": order.credit_card_name,
            "first_digits": order.credit_card_first_digits,
            "last_digits": order.credit_card_last_digits,
            "expiration_year": order.credit_card_expiration_year,
            "expiration_month": order.credit_card_expiration_month
        }

    response_data = {
        "order": {
            "id": order.id,
            "product": {"id": order.product_id, "quantity": order.quantity},
            "total_price": order.total_price,
            "total_price_tax": order.total_price_tax,
            "shipping_price": order.shipping_price,
            "email": order.email,
            "shipping_information": json.loads(order.shipping_information) if order.shipping_information else None,
            "paid": order.paid,
            "credit_card": credit_card_info,
            "transaction": {
                "id": order.transaction_id,
                "success": order.paid,
                "amount_charged": round(order.total_price_tax + order.shipping_price)
            } if order.transaction_id else None
        }
    }

    return jsonify(response_data), 200


if __name__ == "__main__":
    app.run(debug=True)