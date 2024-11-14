# add_admin.py

from main import db, User
from werkzeug.security import generate_password_hash
from flask import Flask

# Initialize the Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///art_platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database
db.init_app(app)

# Function to add a new admin
def add_admin(name, email, password):
    with app.app_context():
        # Check if the email is already in use
        if User.query.filter_by(email=email).first():
            print(f"An account with the email {email} already exists.")
            return

        hashed_password = generate_password_hash(password)
        new_admin = User(name=name, email=email, password_hash=hashed_password, role='Admin')
        db.session.add(new_admin)
        db.session.commit()
        print(f"Admin {name} added successfully with email {email}.")

# Run the script to add an admin
if __name__ == '__main__':
    import getpass

    # Input details from the command line
    name = input("Enter the name for the new admin: ")
    email = input("Enter the email for the new admin: ")
    password = getpass.getpass("Enter the password for the new admin: ")

    add_admin(name, email, password)