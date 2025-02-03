import pytest
from app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_get_products(client):
    response = client.get("/products")
    assert response.status_code == 200

def test_create_order_missing_fields(client):
    response = client.post("/order", json={})
    assert response.status_code == 422
