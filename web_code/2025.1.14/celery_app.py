from celery import Celery
from app import create_app  # Import the Flask app factory
from app.extensions import db

# Create a Celery instance
def make_celery(app):
    celery = Celery(
        app.import_name,
        backend='redis://localhost:6379/0',  # Redis as result backend
        broker='redis://localhost:6379/0'   # Redis as message broker
    )
    celery.conf.update(app.config)
    return celery

# Initialize Flask app
flask_app = create_app()

# Create Celery and bind it to the Flask app
celery = make_celery(flask_app)

# Optional: Example Celery task
@celery.task
def example_task():
    print("This is an example task.")
