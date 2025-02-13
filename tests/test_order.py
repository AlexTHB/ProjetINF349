import pytest

# 🔹 Données partagées (facteurisation)
VALID_SHIPPING_DATA = {
    "order": {
        "email": "client@example.com",
        "shipping_information": {
            "country": "Canada",
            "address": "123 Rue Exemple",
            "postal_code": "G1A 1A1",
            "city": "Québec",
            "province": "QC"
        }
    }
}

INCOMPLETE_SHIPPING_DATA = {
    "order": {
        "shipping_information": {
            "country": "Canada",
            "province": "QC"
        }
    }
}

# 🔹 Fixture pour créer une commande
@pytest.fixture
def created_order(client):
    """Crée une commande et retourne son ID."""
    response = client.post("/order", json={"product": {"id": 1, "quantity": 1}})
    assert response.status_code == 302
    return int(response.headers["Location"].split("/")[-1])

# 🔹 Test : Mise à jour des infos de livraison
def test_update_order_with_shipping_info(client, created_order):
    """Test de mise à jour d'une commande avec les informations de livraison."""
    response = client.put(f"/order/{created_order}", json=VALID_SHIPPING_DATA)
    assert response.status_code == 200  # Vérifie la réponse

    # Vérification des données mises à jour
    updated_order = client.get(f"/order/{created_order}").json["order"]
    assert updated_order["email"] == VALID_SHIPPING_DATA["order"]["email"]
    assert updated_order["shipping_information"] == VALID_SHIPPING_DATA["order"]["shipping_information"]

# 🔹 Test : Mise à jour avec des champs manquants
def test_update_order_missing_fields(client, created_order):
    """Test mise à jour d'une commande avec des champs manquants."""
    response = client.put(f"/order/{created_order}", json=INCOMPLETE_SHIPPING_DATA)
    assert response.status_code == 422  # Vérifie que l'API retourne une erreur

    data = response.get_json()
    assert data["errors"]["order"]["code"] == "missing-fields"
    assert "Il manque un ou plusieurs champs qui sont obligatoires" in data["errors"]["order"]["name"]
