# add_admin.py
from main import db
from app.models import Admin, ArtworkApprovalAdmin, ProductionRoundAdmin, ProductApprovalAdmin, WarehouseAdmin, DeliveryAdmin, CustomerServiceAdmin,InfoAdmin, FinanceAdmin
from werkzeug.security import generate_password_hash
from flask import Flask

# Initialize the Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///art_platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database
db.init_app(app)

# Function to add a new admin
def add_admin(name, email, password, role):
    with app.app_context():

        existing_admin = db.session.query(Admin).filter_by(email=email).first()
        # Check if the email is already in use
        if existing_admin:
            print(f"An account with the email {email} already exists.")
            return
        
        hashed_password = generate_password_hash(password)
        new_admin = None

        if role == 'artwork_approval_admin':
            new_admin = ArtworkApprovalAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'order_management_admin':
            new_admin = ProductionRoundAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'product_approval_admin':
            new_admin = ProductApprovalAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'warehouse_admin':
            new_admin = WarehouseAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'delivery_admin':
            new_admin = DeliveryAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'info_admin':
            new_admin = InfoAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'finance_admin':
            new_admin = FinanceAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'customer_service_admin':
            new_admin = CustomerServiceAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        else:
            print(f"Invalid role '{role}' specified. Please choose from 'artwork_approval_admin', 'production_round_admin', 'product_approval_admin', 'info_admin', 'finance_admin' or 'customer_service_admin'.")
            return

        # Add the new admin to the database
        db.session.add(new_admin)
        db.session.commit()
        print(f"{role.replace('_', ' ').title()} {name} added successfully with email {email}.")

# Run the script to add an admin
if __name__ == '__main__':
    import getpass

    # Input details from the command line
    name = input("Enter the name for the new admin: ")
    email = input("Enter the email for the new admin: ")
    password = getpass.getpass("Enter the password for the new admin: ")
    role = input("Enter the role for the new admin (artwork_approval_admin, production_round_admin, product_approval_admin, warehouse_admin, delivery_admin, info_admin, finance_admin, customer_service_admin): ").strip().lower()

    add_admin(name, email, password, role)