from app import calculate_shipping

def test_calculate_shipping():
    """Test du calcul des frais de livraison"""
    assert calculate_shipping(400) == 500
    assert calculate_shipping(1000) == 1000
    assert calculate_shipping(2500) == 2500
