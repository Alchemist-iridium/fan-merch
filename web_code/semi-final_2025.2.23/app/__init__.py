from flask import Flask
import os
from app.uuid6_converter import UUID6Converter
from app.extensions import db  # Import db here

def create_app():
    app = Flask(__name__)
    app.secret_key = 'supersecretkey'
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///art_platform.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize db with the app
    db.init_app(app)

    # Register the UUID6 converter
    app.url_map.converters['uuid6'] = UUID6Converter

    # Register the blueprints
    from app.routes.user_routes import user_interface
    from app.routes.admin_routes import admin_interface

    app.register_blueprint(user_interface, url_prefix='/')
    app.register_blueprint(admin_interface, url_prefix='/admin')

    return app