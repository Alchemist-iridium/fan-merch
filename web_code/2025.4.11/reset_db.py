# reset_db.py
# this script is used
from app.models import db
from flask import Flask

# Define Flask app
app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['PRODUCT_UPLOAD_FOLDER'] = 'static/product_images' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///art_platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database with SQLAlchemy
db.init_app(app)

# Reset the database

with app.app_context():
    db.drop_all()
    db.create_all()
    print("Database reset: all tables dropped and recreated.")
