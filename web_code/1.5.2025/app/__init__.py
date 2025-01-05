from flask import Flask
from app.extensions import db
import os
def create_app():
    # Create the Flask app
    app = Flask(__name__)
    app.secret_key = 'supersecretkey'
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///art_platform.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize the database with the app
    db.init_app(app)

    # Register the blueprints here, after the app and db are initialized
    from app.routes.user_routes import user_interface
    from app.routes.admin_routes import admin_interface

    app.register_blueprint(user_interface, url_prefix='/')
    app.register_blueprint(admin_interface, url_prefix='/admin')

    return app
