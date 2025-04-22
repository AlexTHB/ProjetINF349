import json
import requests
from models import Order, OrderProduct
from app import redis_client

def process_payment(order_id, credit_card):
    from app import db  # Import retardé pour éviter les problèmes circulaires
    try:
        order = Order.get_by_id(order_id)
    except Order.DoesNotExist:
        return

    if order.paid:
        return

    payload = {
        "credit_card": credit_card,
        "amount_charged": round(order.total_price_tax + order.shipping_price)
    }

    try:
        response = requests.post(
            "https://dimensweb.uqac.ca/~jgnault/shops/pay/",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        payment_data = response.json()
    except Exception as e:
        order.transaction = json.dumps({
            "success": False,
            "error": {"code": "payment-error", "name": str(e)},
            "amount_charged": payload["amount_charged"]
        })
        order.paid = False
        order.save()
        return

    if "transaction" in payment_data:
        order.credit_card_name = credit_card["name"]
        card_number = credit_card["number"].replace(" ", "")
        order.credit_card_first_digits = card_number[:4]
        order.credit_card_last_digits = card_number[-4:]
        order.credit_card_expiration_year = int(credit_card["expiration_year"])
        order.credit_card_expiration_month = int(credit_card["expiration_month"])
        order.transaction = json.dumps(payment_data["transaction"])
        order.paid = payment_data["transaction"]["success"]
        order.save()

        # Mise en cache dans Redis après succès
        products = [{"id": op.product.id, "quantity": op.quantity} for op in order.order_products]

        cached_data = {
            "id": order.id,
            "total_price": order.total_price,
            "total_price_tax": order.total_price_tax,
            "email": order.email,
            "shipping_information": json.loads(order.shipping_information) if order.shipping_information else None,
            "paid": order.paid,
            "shipping_price": order.shipping_price,
            "products": products,
            "credit_card": {
                "name": order.credit_card_name,
                "first_digits": order.credit_card_first_digits,
                "last_digits": order.credit_card_last_digits,
                "expiration_year": order.credit_card_expiration_year,
                "expiration_month": order.credit_card_expiration_month
            },
            "transaction": payment_data["transaction"]
        }

        redis_client.set(f"order:{order.id}", json.dumps(cached_data))
