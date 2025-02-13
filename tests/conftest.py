import pytest
from peewee import SqliteDatabase
from app import app
from models import Product, Order

@pytest.fixture(scope='session')
def test_database():
    """Configurer une base de données SQLite en mémoire pour les tests."""
    
    db = SqliteDatabase(':memory:')
    db.bind([Product, Order])
    db.connect()
    db.create_tables([Product, Order])
    
    # Insérer un produit de test dans la base de données.
    Product.create(
        id=1,
        name="Laptop",
        price=1000,
        weight=2000,
        in_stock=True,
        description="Un bon PC",
        image="laptop.jpg"
    )
    
    yield db  # Fournir la base de données pour les tests.
    
    db.drop_tables([Product, Order])  # Nettoyer les tables après les tests.
    db.close()  # Fermer la connexion à la base de données.

@pytest.fixture
def client(test_database):
    """Créer un client de test Flask pour tester l'API."""
    
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client  # Retourner le client de test à utiliser dans les tests.

@pytest.fixture
def empty_order(client):
    """Créer une commande par défaut pour les tests."""
    
    order = Order.create(product_id=1, quantity=1)  # Créer une commande d'exemple.
    return order  # Retourner la commande créée.
