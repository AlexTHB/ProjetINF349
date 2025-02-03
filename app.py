from flask import Flask, jsonify, request, render_template
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
    
    # Vérification des champs obligatoires
    if not data or "product" not in data or "id" not in data["product"] or "quantity" not in data["product"]:
        return jsonify({"errors": {"product": {"code": "missing-fields", "name": "Un produit est requis."}}}), 422

    product_id = data["product"]["id"]
    quantity = data["product"]["quantity"]
    
    # Vérification de la validité de la quantité
    if quantity < 1:
        return jsonify({"errors": {"product": {"code": "invalid-quantity", "name": "Quantité invalide."}}}), 422

    # Vérification de l'existence du produit
    product = Product.get_or_none(Product.id == product_id)
    if not product:
        return jsonify({"errors": {"product": {"code": "not-found", "name": "Produit introuvable."}}}), 422

    # Vérification de l'inventaire
    if not product.in_stock:
        return jsonify({"errors": {"product": {"code": "out-of-inventory", "name": "Le produit est en rupture de stock."}}}), 422

    # Calcul du prix total
    total_price = product.price * quantity

    # Création de la commande
    order = Order.create(product_id=product_id, quantity=quantity, total_price=total_price)

    return jsonify({"order_id": order.id}), 302

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
    if not order:
        return jsonify({"errors": {"order": {"code": "missing-fields", "name": "Commande introuvable."}}}), 404
    
    if "order" not in data or "email" not in data["order"] or "shipping_information" not in data["order"]:
        return jsonify({"errors": {"order": {"code": "missing-fields", "name": "Champs obligatoires manquants."}}}), 422
    
    order.email = data["order"]["email"]
    order.shipping_information = str(data["order"]["shipping_information"])
    order.save()
    return jsonify({"order": order.__data__})

@app.route("/order/<int:order_id>/pay", methods=["PUT"])
def pay_order(order_id):
    data = request.get_json()
    order = Order.get_or_none(Order.id == order_id)
    if not order:
        return jsonify({"errors": {"order": {"code": "not-found", "name": "Commande introuvable."}}}), 404
    
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
