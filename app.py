from flask import Flask, jsonify, request, render_template
from models import db, Product, Order
from peewee import DoesNotExist
import requests
import json

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

init_db()

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
        return jsonify({"errors": {"product": {"code": "invalid-product", "name": "Produit introuvable"}}}), 422

    if not product.in_stock:
        return jsonify({"errors": {"product": {"code": "out-of-inventory", "name": "Produit non disponible"}}}), 422

    order = Order.create(
        product_id=product.id,
        quantity=data["product"]["quantity"],
        total_price=product.price * data["product"]["quantity"] * 100,
        shipping_price=calculate_shipping(product.weight * data["product"]["quantity"])
    )

    return jsonify({
        "order": {
            "id": order.id,
            "product": {"id": product.id, "quantity": order.quantity},
            "total_price": order.total_price,
            "shipping_price": order.shipping_price
        }
    }), 201

@app.route("/order/<int:order_id>", methods=["GET"])
def get_order(order_id):
    try:
        order = Order.get_by_id(order_id)
    except DoesNotExist:
        return jsonify({"errors": {"order": {"code": "not-found", "name": "Commande introuvable"}}}), 404

    credit_card = None
    if order.credit_card_name:
        credit_card = {
            "name": order.credit_card_name,
            "first_digits": order.credit_card_first_digits,
            "last_digits": order.credit_card_last_digits,
            "expiration_year": order.credit_card_expiration_year,
            "expiration_month": order.credit_card_expiration_month
        }

    return jsonify({
        "order": {
            "id": order.id,
            "product": {"id": order.product_id, "quantity": order.quantity},
            "total_price": order.total_price,
            "total_price_tax": order.total_price_tax,
            "shipping_price": order.shipping_price,
            "email": order.email,
            "shipping_information": json.loads(order.shipping_information) if order.shipping_information else None,
            "paid": order.paid,
            "transaction": {"id": order.transaction_id} if order.transaction_id else None,
            "credit_card": credit_card
        }
    })

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

    # Partie mise à jour des informations client
    if "order" in data:
        required_fields = ["email", "shipping_information"]
        if not all(field in data["order"] for field in required_fields):
            return jsonify({
                "errors": {
                    "order": {
                        "code": "missing-fields",
                        "name": "Champs obligatoires manquants"
                    }
                }
            }), 422

        shipping_info = data["order"]["shipping_information"]
        required_shipping = ["country", "address", "postal_code", "city", "province"]
        if not all(field in shipping_info for field in required_shipping):
            return jsonify({
                "errors": {
                    "order": {
                        "code": "invalid-shipping",
                        "name": "Informations de livraison incomplètes"
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
    credit_card = None  # Initialisation
    
    if "credit_card" in data:
        # Validation pré-paiement
        if not order.email or not order.shipping_information:
            return jsonify({
                "errors": {
                    "order": {
                        "code": "missing-fields",
                        "name": "Informations client requises avant paiement"
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
        credit_card["number"] = " ".join(credit_card["number"][i:i+4] for i in range(0, len(credit_card["number"]), 4))
        print(credit_card)

        # Appel à l'API de paiement
        payload = {"credit_card": credit_card, "amount_charged": round(order.total_price_tax + order.shipping_price)}
        print(payload)
        print(PAYMENT_API)
        
        try:
            response = requests.post(PAYMENT_API, json=payload, headers={"Content-Type": "application/json"})
            print(response)
            response.raise_for_status()
            payment_data = response.json()
        except requests.exceptions.RequestException as e:
            return jsonify({
                "errors": {
                    "payment": {
                        "code": "service-unavailable",
                        "name": f"Erreur de connexion au service de paiement: {str(e)}"
                    }
                }
            }), 502
        except json.JSONDecodeError:
            return jsonify({
                "errors": {
                    "payment": {
                        "code": "invalid-response",
                        "name": "Réponse invalide du processeur de paiement"
                    }
                }
            }), 502

        # Vérification de la réponse
        if not payment_data.get("transaction", {}).get("success", False):
            return jsonify({
                "errors": {
                    "payment": {
                        "code": "payment-failed",
                        "name": payment_data.get("errors", {}).get("credit_card", {}).get("name", "Paiement refusé")
                    }
                }
            }), 422

        # Mise à jour finale après le paiement
        card_number = credit_card["number"].replace(" ", "")
        order.credit_card_name = credit_card["name"]
        order.credit_card_first_digits = card_number[:4]
        order.credit_card_last_digits = card_number[-4:]
        order.credit_card_expiration_year = int(credit_card["expiration_year"])
        order.credit_card_expiration_month = int(credit_card["expiration_month"])
        order.transaction_id = payment_data["transaction"]["id"]
        order.paid = True
        order.save()

        # Mise à jour de credit_card pour masquer les infos sensibles
        credit_card = {
            "name": order.credit_card_name,
            "first_digits": order.credit_card_first_digits,
            "last_digits": order.credit_card_last_digits,
            "expiration_year": order.credit_card_expiration_year,
            "expiration_month": order.credit_card_expiration_month
        }

    # Construction de la réponse
    response_data = {
        "order": {
            "id": order.id,
            "product": {
                "id": order.product_id,
                "quantity": order.quantity
            },
            "total_price": order.total_price,
            "total_price_tax": order.total_price_tax,
            "shipping_price": order.shipping_price,
            "email": order.email,
            "shipping_information": json.loads(order.shipping_information),
            "paid": order.paid,
            "credit_card": credit_card,
            "transaction": {
                "id": order.transaction_id,
                "success": order.paid,
                "amount_charged": round(order.total_price + order.shipping_price, 2)
            }
        }
    }

    return jsonify(response_data), 200


if __name__ == "__main__":
    app.run(debug=True)