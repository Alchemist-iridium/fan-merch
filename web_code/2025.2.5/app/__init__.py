from flask import Flask
from app.extensions import db, celery, init_extensions
import os
from app.uuid6_converter import UUID6Converter  # Replace with the actual module where you define UUID6Converter


def create_app():
    # Create the Flask app
    app = Flask(__name__)
    app.secret_key = 'supersecretkey'
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///art_platform.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


    # Initialize extensions
    init_extensions(app)

    # Register the UUID6 converter
    app.url_map.converters['uuid6'] = UUID6Converter

    # Register the blueprints here
    from app.routes.user_routes import user_interface
    from app.routes.admin_routes import admin_interface

    app.register_blueprint(user_interface, url_prefix='/')
    app.register_blueprint(admin_interface, url_prefix='/admin')

    return app
