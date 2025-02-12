import json

def test_full_order_process(client, init_database):
    """Test d'intégration du processus de commande"""

    # Étape 1 : Créer une commande
    order_response = client.post("/order", json={"product": {"id": 1, "quantity": 1}})
    assert order_response.status_code == 302  # Redirection vers la commande créée

    # Récupérer l'ID de la commande
    order_id = int(order_response.headers["Location"].split("/")[-1])

    # Étape 2 : Vérifier la commande créée
    response = client.get(f"/order/{order_id}")
    assert response.status_code == 200
    order_data = response.get_json()["order"]

    # Vérifier les données de la commande
    assert order_data["product"]["id"] == 1
    assert order_data["total_price"] == 1000 * 100
