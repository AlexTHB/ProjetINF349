from peewee import *

db = SqliteDatabase('database.db')

class BaseModel(Model):
    class Meta:
        database = db

class Product(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField()
    description = TextField()
    price = FloatField()
    weight = IntegerField()
    in_stock = BooleanField()
    image = CharField()

class Order(BaseModel):
    id = AutoField()
    product_id = IntegerField()
    quantity = IntegerField()
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

def initialize_db():
    db.connect()
    db.create_tables([Product, Order], safe=True)
    db.close()