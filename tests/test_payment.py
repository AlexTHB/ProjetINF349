import pytest
from unittest.mock import patch
from models import Order

# URL de l'API de paiement
PAYMENT_API_URL = "https://dimensweb.uqac.ca/~jgnault/shops/pay/"

# Données de cartes de crédit pour différents scénarios de paiement
VALID_CREDIT_CARD = {  # Carte valide pour un paiement réussi
    "credit_card": {
        "name": "Client Test",
        "number": "4242424242424242",
        "expiration_month": 12,
        "expiration_year": 2025,
        "cvv": "123"
    }
}

DECLINED_CREDIT_CARD = {  # Carte déclinée pour tester un échec de paiement
    "credit_card": {
        "name": "John Doe",
        "number": "4000000000000002",
        "expiration_month": 9,
        "expiration_year": 2024,
        "cvv": "123"
    }
}

INVALID_CREDIT_CARD = {  # Carte avec un numéro incorrect pour tester une erreur de format
    "credit_card": {
        "name": "Jane Doe",
        "number": "5555555555555555",
        "expiration_month": 12,
        "expiration_year": 2025,
        "cvv": "123"
    }
}

# Données d'expédition valides
SHIPPING_DATA = {
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

# Fixture pour simuler l'API de paiement
@pytest.fixture
def mock_payment_api():
    with patch("requests.post") as mock_post:
        yield mock_post

# Fixture pour créer une commande et retourner son ID
@pytest.fixture
def created_order(client):
    """Crée une commande et retourne son identifiant."""
    response = client.post("/order", json={"product": {"id": 1, "quantity": 1}})
    assert response.status_code == 302  # Vérifie que la commande a été créée avec redirection
    return int(response.headers["Location"].split("/")[-1])  # Extrait l'ID de la commande depuis l'URL

# Fixture pour préparer une commande avec des informations d'expédition
@pytest.fixture
def prepared_order(client, created_order):
    """Ajoute des informations client à une commande existante."""
    client.put(f"/order/{created_order}", json=SHIPPING_DATA)
    return created_order

# Test : Vérifie que l'API de paiement est bien appelée lors du paiement
def test_payment_api_called(client, prepared_order, mock_payment_api):
    """Vérifie que l'API de paiement est appelée correctement."""
    # Simule une réponse réussie de l'API de paiement
    mock_payment_api.return_value.status_code = 200
    mock_payment_api.return_value.json.return_value = {
        "transaction": {"id": "test123", "success": True, "amount_charged": 1150}
    }

    response = client.put(f"/order/{prepared_order}", json=VALID_CREDIT_CARD)
    assert response.status_code == 200  # Vérifie que le paiement a réussi

    # Vérifie que l'API de paiement a été appelée une fois avec la bonne URL
    mock_payment_api.assert_called_once()
    args, kwargs = mock_payment_api.call_args
    assert args[0] == PAYMENT_API_URL

# Test : Vérifie qu'un paiement est impossible sans email et adresse de livraison
def test_payment_without_email_or_shipping(client, created_order):
    """Teste le refus de paiement sans informations client."""
    response = client.put(f"/order/{created_order}", json=VALID_CREDIT_CARD)
    assert response.status_code == 422  # Vérifie que le paiement échoue

    data = response.get_json()
    assert data["errors"]["order"]["code"] == "missing-fields"
    assert "Les informations du client sont nécessaire avant d'appliquer une carte de crédit" in data["errors"]["order"]["name"]

# Test : Vérifie qu'on ne peut pas payer deux fois la même commande
def test_cannot_pay_twice(client, prepared_order, mock_payment_api):
    """Vérifie qu'un paiement en double est refusé."""
    # Simule un paiement réussi
    mock_payment_api.return_value.status_code = 200
    mock_payment_api.return_value.json.return_value = {
        "transaction": {"id": "test123", "success": True, "amount_charged": 1150}
    }

    response = client.put(f"/order/{prepared_order}", json=VALID_CREDIT_CARD)
    assert response.status_code == 200  # Vérifie que le premier paiement réussit

    response = client.put(f"/order/{prepared_order}", json=VALID_CREDIT_CARD)
    assert response.status_code == 422  # Vérifie que le deuxième paiement échoue

    data = response.get_json()
    assert data["errors"]["order"]["code"] == "already-paid"
    assert "La commande est déjà payée" in data["errors"]["order"]["name"]

# Test : Vérifie le refus de paiement si la carte est déclinée
def test_declined_card(client, prepared_order, mock_payment_api):
    """Teste le paiement avec une carte déclinée."""
    # Simule un refus de la banque
    mock_payment_api.return_value.status_code = 422
    mock_payment_api.return_value.json.return_value = {
        "errors": {
            "credit_card": {"code": "card-declined", "name": "La carte de crédit a été déclinée."}
        }
    }

    response = client.put(f"/order/{prepared_order}", json=DECLINED_CREDIT_CARD)
    assert response.status_code == 422  # Vérifie que le paiement est refusé
    assert response.json["errors"]["credit_card"]["code"] == "card-declined"
    assert Order.get_by_id(prepared_order).paid is False  # Vérifie que la commande n'est pas marquée comme payée

# Test : Vérifie que le paiement est refusé si le numéro de carte est invalide
def test_invalid_card_number(client, prepared_order, mock_payment_api):
    """Teste le paiement avec un numéro de carte invalide."""
    mock_payment_api.return_value.status_code = 422
    mock_payment_api.return_value.json.return_value = {
        "errors": {
            "credit_card": {"code": "incorrect-number", "name": "Numéro de carte invalide"}
        }
    }

    response = client.put(f"/order/{prepared_order}", json=INVALID_CREDIT_CARD)
    assert response.status_code == 422  # Vérifie que le paiement est refusé
    assert response.json["errors"]["credit_card"]["code"] == "incorrect-number"
    assert Order.get_by_id(prepared_order).paid is False  # Vérifie que la commande reste impayée

# Test : Vérifie le refus du paiement si la carte est expirée
def test_expired_card(client, prepared_order, mock_payment_api):
    """Teste le paiement avec une carte expirée."""
    mock_payment_api.return_value.status_code = 502
    mock_payment_api.return_value.json.return_value = {
        "errors": {
            "payment": {"code": "card-declined", "name": "La carte est expirée."}
        }
    }

    expired_card = {
        "credit_card": {
            "number": "4242424242424242",
            "expiration_year": 2024,
            "expiration_month": 1,
            "cvv": "123",
            "name": "Expired User"
        }
    }

    response = client.put(f"/order/{prepared_order}", json=expired_card)
    assert response.status_code == 502  # Vérifie que le paiement échoue
    assert response.json["errors"]["payment"]["code"] == "card-declined"
    assert Order.get_by_id(prepared_order).paid is False  # Vérifie que la commande n'est pas payée
