from peewee import Model, CharField, BooleanField, IntegerField, TextField, SqliteDatabase

# Configuration de la base de données
db = SqliteDatabase('database.db')

class BaseModel(Model):
    class Meta:
        database = db

class Product(BaseModel):
    id = IntegerField(primary_key=True)  # ID unique requis par l'API
    name = CharField()
    description = CharField()
    price = IntegerField()  # Stocker le prix en centimes (ex: 28.1€ = 2810)
    weight = IntegerField()
    in_stock = BooleanField()
    image = CharField()

class Order(BaseModel):
    id = IntegerField(primary_key=True)
    product_id = IntegerField()
    quantity = IntegerField()
    email = CharField(null=True)
    shipping_information = TextField(null=True)  # JSON stocké sous forme de texte
    total_price = IntegerField()  # Prix total en centimes
    total_price_tax = IntegerField(null=True)
    shipping_price = IntegerField(null=True)
    paid = BooleanField(default=False)
    transaction_id = CharField(null=True)  # Stocker l'ID de transaction après paiement

# Initialisation de la base de données
def initialize_db():
    db.connect()
    db.create_tables([Product, Order], safe=True)
    db.close()
