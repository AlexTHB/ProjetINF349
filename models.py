from peewee import *
from peewee import DeferredThroughModel
import os

# Configuration de la base de données PostgreSQL
db = PostgresqlDatabase(
    os.environ.get('DB_NAME', 'api8inf349'),
    user=os.environ.get('DB_USER', 'user'),
    password=os.environ.get('DB_PASSWORD', 'pass'),
    host=os.environ.get('DB_HOST', 'postgres'),
    port=int(os.environ.get('DB_PORT', 5432))
)

# Modèle de base
class BaseModel(Model):
    class Meta:
        database = db

# Déclaration différée pour la relation ManyToMany
OrderProductThroughDeferred = DeferredThroughModel()

# Modèle Product
class Product(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField()
    description = TextField()
    price = FloatField()
    weight = IntegerField()
    in_stock = BooleanField()
    image = CharField()

# Modèle Order
class Order(BaseModel):
    email = CharField(null=True)
    shipping_information = TextField(null=True)
    total_price = FloatField()
    total_price_tax = FloatField(null=True)
    shipping_price = FloatField()
    paid = BooleanField(default=False)
    transaction_id = CharField(null=True)
    credit_card_name = CharField(null=True)
    credit_card_first_digits = CharField(null=True)
    credit_card_last_digits = CharField(null=True)
    credit_card_expiration_year = IntegerField(null=True)
    credit_card_expiration_month = IntegerField(null=True)
    payment_status = CharField(null=True)
    transaction = TextField(null=True)

    products = ManyToManyField(
        Product,
        through_model=OrderProductThroughDeferred,
        backref='orders'
    )

# Modèle de liaison OrderProduct
class OrderProduct(BaseModel):
    order = ForeignKeyField(Order, backref='order_products')
    product = ForeignKeyField(Product)
    quantity = IntegerField()
    class Meta:
        table_name = 'orderproduct'  

# Résolution de la référence différée
OrderProductThroughDeferred.set_model(OrderProduct)

def initialize_db():
    db.connect()
    db.create_tables([Product, Order, OrderProduct], safe=True)
    db.close()