from flask_sqlalchemy import SQLAlchemy
from celery import Celery

# Initialize database
db = SQLAlchemy()

# Initialize Celery
celery = Celery()

def init_extensions(app):
    """
    Initialize extensions with the Flask app.
    """
    db.init_app(app)
    celery.conf.update(
        broker_url='redis://localhost:6379/0',  # Redis as message broker
        result_backend='redis://localhost:6379/0'  # Redis as result backend
    )
