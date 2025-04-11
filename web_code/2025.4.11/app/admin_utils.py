# utils.py

from flask import flash, redirect, url_for
from functools import wraps
import logging
from uuid import UUID
from app.models import Artwork
from datetime import datetime
from app.extensions import db
from flask_login import current_user, login_required  # Add this import

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_ADMIN_ROLES = {
    'artwork_approval_admin',
    'product_approval_admin',
    'production_round_admin',
    'warehouse_admin',
    'delivery_admin',
    'info_admin',
    'finance_admin',
    'customer_service_admin'
}


def admin_required(role, login_endpoint='admin_interface.admin_login'):
    if role not in VALID_ADMIN_ROLES:
        raise ValueError(f"Invalid admin role: {role}. Must be one of {VALID_ADMIN_ROLES}")
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role != role:
                flash(f"You need to be logged in as a {role.replace('_', ' ').title()}.")
                logger.warning(f"Unauthorized access attempt to {f.__name__} with role {current_user.role}")
                return redirect(url_for(login_endpoint))
            kwargs['admin_id'] = current_user.id  # Pass admin_id if needed
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# for shared routes
def admin_role_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role not in VALID_ADMIN_ROLES:
            flash("You do not have permission to access this page.")
            return redirect(url_for('admin_interface.admin_login'))
        return f(*args, **kwargs)
    return decorated_function





def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'xls', 'xlsx'}

# into string
def process_file(file):
    """Read uploaded file into a dataframe."""
    import pandas as pd
    if file.filename.endswith('.csv'):
        df = pd.read_csv(file)
    elif file.filename.endswith('.xlsx'):
        df = pd.read_excel(file, engine='openpyxl')
    else:
        raise ValueError("Unsupported file type")
    df.columns = df.columns.str.strip()  # Good practice to handle potential whitespace
    return df

# into dict
def process_file_path(file_path):
    """Read a file from disk into a dataframe."""
    import pandas as pd
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    elif file_path.endswith('.xlsx'):
        df = pd.read_excel(file_path, engine='openpyxl')
    else:
        raise ValueError("Unsupported file type")
    df.columns = df.columns.str.strip()
    return df.to_dict('records')


    

def to_uuid(value, field_name="UUID"):
    """
    Convert a string to a UUID object, logging and raising an error if invalid.
    
    Args:
        value: The string to convert to a UUID.
        field_name: Name of the field for error reporting (default: "UUID").
    
    Returns:
        uuid.UUID: The UUID object for SQLAlchemy compatibility with as_uuid=True.
    
    Raises:
        ValueError: If the value is not a valid UUID.
    """
    try:
        uuid_obj = UUID(value)
        logger.debug(f"Converted {field_name}: {value} to UUID")
        return uuid_obj  # Return UUID object, not string
    except ValueError as e:
        logger.error(f"Invalid {field_name}: {value} - {str(e)}")
        raise ValueError(f"Invalid {field_name}: {value}")
    




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
