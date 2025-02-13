from models import Product

def test_get_products(client):
    """Test de récupération de la liste des produits via `GET /products`."""
    
    response = client.get("/products")  # Envoi d'une requête GET à `/products`
    
    assert response.status_code == 200  # Vérifie que la réponse est 200 OK
    assert len(response.json["products"]) == 1  # Vérifie qu'au moins un produit est retourné

def test_create_order_success(client):
    """Test de création d'une commande valide via `POST /order`."""
    
    response = client.post("/order", json={"product": {"id": 1, "quantity": 2}})
    
    assert response.status_code == 302  # Vérifie que la commande a été créée avec une redirection

def test_create_order_missing_product(client):
    """Test de création d'une commande sans produit spécifié."""
    
    response = client.post("/order", json={})  # Envoi d'une requête vide
    
    assert response.status_code == 422  # Vérifie que la requête est refusée
    assert response.json["errors"]["product"]["code"] == "missing-fields"  # Vérifie le code d'erreur
    assert "Champs manquants" in response.json["errors"]["product"]["name"]  # Vérifie le message d'erreur

def test_quantity_edge_cases(client):
    """Test des valeurs limites pour la quantité d'un produit."""
    
    response = client.post("/order", json={"product": {"id": 1, "quantity": 0}})
    assert response.status_code == 422  # Vérifie que la quantité de 0 est refusée

    response = client.post("/order", json={"product": {"id": 1, "quantity": -5}})
    assert response.status_code == 422  # Vérifie que la quantité négative est refusée

def test_create_order_no_id(client):
    """Test de création d'une commande avec des valeurs manquantes."""
    
    response = client.post("/order", json={"product": {"id": "", "quantity": 1}})
    assert response.status_code == 422  # Vérifie que l'ID vide est refusé

    response = client.post("/order", json={"product": {"id": 1, "quantity": ""}})
    assert response.status_code == 422  # Vérifie que la quantité vide est refusée

def test_inventory_check(client):
    """Test de commande d'un produit hors stock."""
    
    Product.create(id=99, name="Produit HS", in_stock=False, price=100, weight=500, description="Hors stock", image="hs.jpg")

    response = client.post("/order", json={"product": {"id": 99, "quantity": 1}})
    
    assert response.status_code == 422  # Vérifie que la commande est refusée
    assert response.json["errors"]["product"]["code"] == "out-of-inventory"  # Vérifie le code d'erreur
    assert "Le produit demandé n'est pas en inventaire" in response.json["errors"]["product"]["name"]  # Vérifie le message d'erreur
