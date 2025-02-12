import pytest
import sys
import os
from app import app
from models import db, Product, Order

# Ajouter le dossier parent au chemin d'import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture
def client():
    """Client Flask pour les tests"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def init_database():
    """Création d'une base SQLite en mémoire pour les tests"""
    db.init(':memory:')  # Base temporaire
    db.connect()
    db.create_tables([Product, Order])

    # Ajouter un produit de test
    Product.create(id=1, name="Laptop", description="Un bon PC", price=1000, weight=2000, in_stock=True, image="laptop.jpg")

    yield db  # Permet d'utiliser cette base pour les tests

    db.drop_tables([Product, Order])
    db.close()
