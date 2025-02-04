from flask import Flask, jsonify, request, render_template, redirect, url_for
from peewee import Model, CharField, IntegerField, BooleanField, SqliteDatabase
import requests

app = Flask(__name__)
db = SqliteDatabase("database.db")
API_URL = "http://dimensweb.uqac.ca/~jgnault/shops/products/"
PAYMENT_API = "http://dimensweb.uqac.ca/~jgnault/shops/pay/"

# Modèles de base de données
class BaseModel(Model):
    class Meta:
        database = db

class Product(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField()
    description = CharField()
    price = IntegerField()
    weight = IntegerField()
    in_stock = BooleanField()
    image = CharField()

class Order(BaseModel):
    id = IntegerField(primary_key=True)
    product_id = IntegerField()
    quantity = IntegerField()
    total_price = IntegerField()
    total_price_tax = IntegerField(null=True)
    shipping_price = IntegerField(null=True)
    email = CharField(null=True)
    shipping_information = CharField(null=True)
    paid = BooleanField(default=False)
    transaction_id = CharField(null=True)

# Initialisation de la base de données
def fetch_products():
    response = requests.get(API_URL)
    if response.status_code == 200:
        return response.json().get("products", [])
    return []

def init_db():
    db.connect()
    db.create_tables([Product, Order], safe=True)
    if Product.select().count() == 0:
        for p in fetch_products():
            Product.create(
                id=p["id"], name=p["name"], description=p["description"],
                price=p["price"], weight=p["weight"], in_stock=p["in_stock"], image=p["image"]
            )
    db.close()

init_db()

def calculate_shipping_price(weight):
    """Calcule le prix d'expédition en fonction du poids total."""
    if weight <= 500:
        return 500  # 5$
    elif weight < 2000:
        return 1000  # 10$
    else:
        return 2500  # 25$

@app.route("/")
def index():
    products = Product.select()
    return render_template("index.html", products=products)

@app.route("/products", methods=["GET"])
def get_products():
    return jsonify({"products": [product.__data__ for product in Product.select()]})

@app.route("/order", methods=["POST"])
def create_order():
    data = request.get_json()

    # Vérifier que l'objet "product" existe
    if not data or "product" not in data:
        return jsonify({"errors": {"product": {"code": "missing-fields", "name": "La création d'une commande nécessite un produit"}}}), 422

    product = data["product"]

    # Vérifier que le produit existe et s'il manque l'objet product
    product_id = product["id"]
    product_obj = Product.get_or_none(Product.id == product_id)
    if not product_obj:
        return jsonify({"errors": {"product": {"code": "missing-fields", "name": "La création d'une commande nécessite un produit"}}}), 422
    
    # Vérifier que quantity est bien un entier valide et qu'il contient le champs quantity
    try:
        quantity = int(product["quantity"])
    except (ValueError, TypeError):
        return jsonify({"errors": {"product": {"code": "missing-fields", "name": "Un produit doit contenir une quantité"}}}), 422

    # Vérifier que la quantité est >= 1
    if quantity < 1:
        return jsonify({"errors": {"product": {"code": "invalid-quantity", "name": "Quantité invalide. Doit être supérieure ou égale à 1."}}}), 422

    # Vérifier que le produit est en stock
    if not product_obj.in_stock:
        return jsonify({"errors": {"product": {"code": "out-of-inventory", "name": "Le produit demandé n'est pas en inventaire"}}}), 422

    # Calculer le prix total et le poids total
    total_price = product_obj.price * quantity
    total_weight = product_obj.weight * quantity

    # Calculer le prix de livraison
    shipping_price = calculate_shipping_price(total_weight)

    # Créer la commande
    order = Order.create(
        product_id=product_id,
        quantity=quantity,
        total_price=total_price,
        shipping_price=shipping_price
    )

    # Retourner un code 302 avec la redirection vers la commande créée
    return redirect(url_for("get_order", order_id=order.id), code=302)

@app.route("/order/<int:order_id>", methods=["GET"])
def get_order(order_id):
    order = Order.get_or_none(Order.id == order_id)
    if not order:
        return jsonify({"errors": {"order": {"code": "missing-fields", "name": "Commande introuvable."}}}), 404
    return jsonify({"order": order.__data__})

@app.route("/order/<int:order_id>", methods=["PUT"])
def update_order(order_id):
    data = request.get_json()
    order = Order.get_or_none(Order.id == order_id)

    # Vérifier si la commande existe
    if not order:
        return jsonify({"errors": {"order": {"code": "not-found", "name": "Commande introuvable."}}}), 404
    
    # Vérifier si les champs obligatoires sont présents
    if "order" not in data or "email" not in data["order"] or "shipping_information" not in data["order"]:
        return jsonify({"errors": {"order": {"code": "missing-fields", "name": "Il manque un ou plusieurs champs obligatoires."}}}), 422
    
    shipping_info = data["order"]["shipping_information"]
    required_fields = ["country", "address", "postal_code", "city", "province"]
    
    if not all(field in shipping_info for field in required_fields):
        return jsonify({"errors": {"order": {"code": "missing-fields", "name": "Il manque un ou plusieurs champs dans l'adresse de livraison."}}}), 422
    
    # Mettre à jour l'email et l'adresse de livraison
    order.email = data["order"]["email"]
    order.shipping_information = str(shipping_info)

    # Déterminer la taxe en fonction de la province
    TAX_RATES = {
        "QC": 0.15,  # Québec 15%
        "ON": 0.13,  # Ontario 13%
        "AB": 0.05,  # Alberta 5%
        "BC": 0.12,  # Colombie-Britannique 12%
        "NS": 0.14   # Nouvelle-Écosse 14%
    }
    
    province = shipping_info["province"]
    tax_rate = TAX_RATES.get(province, 0)  # Default to 0 if province is not in the list

    # Calcul du total avec taxes
    order.total_price_tax = int(order.total_price * (1 + tax_rate))

    # Sauvegarde des modifications
    order.save()
    
    return jsonify({"order": order.__data__}), 200


@app.route("/order/<int:order_id>/pay", methods=["PUT"])
def pay_order(order_id):
    data = request.get_json()
    order = Order.get_or_none(Order.id == order_id)
    if not order:
        return jsonify({"errors": {"order": {"code": "not-founde", "name": "Commande introuvable."}}}), 404
    
    if not order.email or not order.shipping_information:
        return jsonify({"errors": {"order": {"code": "missing-fields", "name": "Informations client requises."}}}), 422
    
    if order.paid:
        return jsonify({"errors": {"order": {"code": "already-paid", "name": "La commande est déjà payée."}}}), 422
    
    response = requests.post(PAYMENT_API, json={"credit_card": data["credit_card"], "amount_charged": order.total_price})
    if response.status_code == 200:
        transaction = response.json().get("transaction")
        order.paid = True
        order.transaction_id = transaction["id"]
        order.save()
        return jsonify({"order": order.__data__})
    else:
        return response.json(), response.status_code

if __name__ == "__main__":
    app.run(debug=True)
