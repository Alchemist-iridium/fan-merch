from flask import Flask
import os
from app.uuid6_converter import UUID6Converter
from app.extensions import db
from flask_login import LoginManager  # Add this import
import uuid

def create_app():
    app = Flask(__name__)
    app.secret_key = 'supersecretkey'
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///art_platform.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize db with the app
    db.init_app(app)

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'user_interface.login'  # Endpoint for login page

    # User loader callback
    @login_manager.user_loader
    def load_user(user_id):
        try:
            from app.models import User  # Import here to avoid circular imports
            return User.query.get(uuid.UUID(user_id))
        except ValueError:
            return None

    # Register the UUID6 converter
    app.url_map.converters['uuid6'] = UUID6Converter

    # Register the blueprints
    from app.routes.user_routes import user_interface
    from app.routes.admin_routes import admin_interface

    app.register_blueprint(user_interface, url_prefix='/')
    app.register_blueprint(admin_interface, url_prefix='/admin')

    return app