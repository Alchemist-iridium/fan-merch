# main.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from extensions import db

def create_app():
    # Create the Flask app
    app = Flask(__name__)
    app.secret_key = 'supersecretkey'
    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///art_platform.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize the database with the app
    db.init_app(app)

    # Register the blueprints here, after the app and db are initialized
    from user_interface import user_interface
    app.register_blueprint(user_interface)

    return app

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
    app.run(debug=True)
