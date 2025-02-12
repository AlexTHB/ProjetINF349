import json

def test_get_products(client, init_database):
    """Test pour récupérer la liste des produits"""
    response = client.get("/products")
    assert response.status_code == 200
    data = response.get_json()

    assert "products" in data
    assert len(data["products"]) == 1  # Vérifie qu'on récupère le produit ajouté
    assert data["products"][0]["name"] == "Laptop"

def test_create_order_success(client, init_database):
    """Test de création d'une commande réussie"""
    response = client.post("/order", json={"product": {"id": 1, "quantity": 2}})
    assert response.status_code == 302  # Vérifie la redirection vers la commande créée
