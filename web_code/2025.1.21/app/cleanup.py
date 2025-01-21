from datetime import datetime, timedelta
from app.extensions import db
from app.models import ItemOrder

def clean_expired_unpaid_orders():
    try:
        expiration_time = datetime.now() - timedelta(minutes=30)
        expired_orders = ItemOrder.query.filter(
            ItemOrder.payment_status == 'unpaid',
            ItemOrder.created_at < expiration_time
        ).all()

        if not expired_orders:
            print("No expired unpaid orders found.")
            return

        for order in expired_orders:
            print(f"Deleting expired order: {order.id}, created at: {order.created_at}")
            db.session.delete(order)

        db.session.commit()
        print(f"Deleted {len(expired_orders)} expired unpaid orders.")
    except Exception as e:
        db.session.rollback()
        print(f"Error while cleaning expired unpaid orders: {e}")
