# user_utils.py

from flask import flash, redirect, url_for
from functools import wraps
import logging
from uuid import UUID
from app.models import Artwork, User
from datetime import datetime
from app.extensions import db
from flask_login import current_user, login_required  # Add this import

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


VALID_USER_ROLES = {
    'artist',
    'customer'
}

def to_uuid(value, field_name="UUID"):
    try:
        return UUID(value)  # Returns a UUID object
    except ValueError:
        raise ValueError(f"Invalid {field_name}: {value}")

# Updated user_role_required (if still needed)
def user_role_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role not in VALID_USER_ROLES:
            flash("You do not have permission to access this page.")
            return redirect(url_for('user_interface.login'))
        return f(*args, **kwargs)
    return decorated_function

# Fixed customer_required
def customer_required(f):  # Simplified to take f directly
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'customer':
            flash("You must be a customer to access this page.")
            return redirect(url_for('user_interface.login'))
        return f(*args, **kwargs)
    return decorated_function

# Fixed artist_required
def artist_required(f):  # Simplified to take f directly
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'artist':
            flash("You must be an artist to access this page.")
            return redirect(url_for('user_interface.login'))
        return f(*args, **kwargs)
    return decorated_function

def update_artwork_timestamp(artwork, commit=False):
    """
    Update the updated_at timestamp of an Artwork instance to the current time.
    
    Args:
        artwork: An Artwork model instance.
        commit: If True, commit the change to the database immediately (default: False).
                Note: This commits all pending changes in the current session, not just
                the updated_at field. Use with caution if other objects are dirty.
    
    Returns:
        None
    
    Raises:
        ValueError: If the argument is not an Artwork instance.
        Exception: If commit=True and the database commit fails.
    """
    if not isinstance(artwork, Artwork):
        logger.error(f"Invalid argument to update_artwork_timestamp: expected Artwork, got {type(artwork)}")
        raise ValueError("Argument must be an Artwork instance")
    
    artwork.updated_at = datetime.now()
    logger.debug(f"Updated timestamp for artwork '{artwork.title}' (ID: {artwork.id}) to {artwork.updated_at}")
    
    if commit:
        try:
            db.session.commit()
            logger.debug(f"Committed timestamp update for artwork '{artwork.title}'")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to commit timestamp update for artwork '{artwork.title}': {str(e)}")
            raise

# Define allowed file extensions for images
def allowed_image(filename):
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
