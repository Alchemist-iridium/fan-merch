from flask import request, Blueprint,current_app, render_template, render_template_string, redirect, url_for, session, flash, current_app, send_file, jsonify
from datetime import datetime, timezone,timedelta
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from app.models import *
# this line needs modification
from app.extensions import db
import uuid
from sqlalchemy.dialects.postgresql import UUID
import pyotp
import json


admin_interface = Blueprint('admin', __name__)

# login page for the admins, which is different from the user login page (for customers and artists)

@admin_interface.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Check if the email belongs to any admin role
        admin = (ArtworkApprovalAdmin.query.filter_by(email=email).first() or
                 OrderManagementAdmin.query.filter_by(email=email).first() or
                 ProductApprovalAdmin.query.filter_by(email=email).first())

        if admin and check_password_hash(admin.password_hash, password):
            session['user_id'] = str(admin.id)
            session['role'] = admin.role
            flash("Admin login successful!")

            # Redirect to the appropriate admin dashboard based on role
            if admin.role == 'artwork_approval_admin':
                return redirect(url_for('admin.artwork_approval_admin_dashboard'))
            elif admin.role == 'order_management_admin':
                return redirect(url_for('admin.order_management_admin_dashboard'))
            elif admin.role == 'product_approval_admin':
                return redirect(url_for('admin.product_approval_admin_dashboard'))
        else:
            error = "Wrong email or password"
            return render_template('admin/account/admin_login.html', error=error)

    return render_template('admin/account/admin_login.html')


# need an admin homepage...? 
# I don't find it necessary right now... just go back to login page would be OK
@admin_interface.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash("You have been logged out.")
    return redirect(url_for('admin.admin_login'))




# Artwork Approval Admin Dashboard, disapprove artwork, approve artwork
@admin_interface.route('/artwork_approval_admin_dashboard', methods=['GET', 'POST'])
def artwork_approval_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access this dashboard.")
        return redirect(url_for('admin.admin_login'))

    search_query = request.args.get('search_query', '').strip()
    search_results = []

    # Fetch all pending artworks that are not picked by any admin
    artworks_info = Artwork.query.filter_by(approval_status='Pending', picked_by_admin_id=None).all()

    if search_query:
        # Filter artworks based on the search query and hard_tags
        search_results = Artwork.query.filter(
            Artwork.approval_status == 'Pending',
            Artwork.picked_by_admin_id == None,
            Artwork.hard_tags.ilike(f"%{search_query}%")
        ).all()

    return render_template(
        'admin/artwork_approval_admin/artwork_approval_admin_dashboard.html',
        artworks=artworks_info,
        search_results=search_results,
        search_query=search_query
    )

# artwork_approval_admin can search artworks by hardtag (ip name) to get selected
# also can pick all the search result to workspace

@admin_interface.route('/search_artworks', methods=['GET', 'POST'])
def search_artworks():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access this page.")
        return redirect(url_for('admin.admin_login'))

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin.artwork_approval_admin_dashboard'))

    # Fetch search results
    search_results = Artwork.query.filter(
        Artwork.approval_status == 'Pending',
        Artwork.picked_by_admin_id == None,
        Artwork.hard_tags.ilike(f"%{search_query}%")
    ).all()

    if request.method == 'POST':
        # Handle "Pick All Artwork"
        for artwork in search_results:
            if not artwork.picked_by_admin_id:
                artwork.picked_by_admin_id = uuid.UUID(session['user_id'])
        db.session.commit()
        flash("All artworks in the search results have been picked.")
        return redirect(url_for('admin.artwork_approval_admin_dashboard'))

    return render_template(
        'admin/artwork_approval_admin/search_results.html',
        search_results=search_results,
        search_query=search_query
    )



# admin picks the artwork from dashboard to personal workspace to approve or disapprove.
# The picked artwork is not going to be displayed on the dashboard.



@admin_interface.route('/artwork_approval_workspace', methods=['GET'])
def artwork_approval_workspace():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access your workspace.")
        return redirect(url_for('admin.admin_login'))

    admin_id = uuid.UUID(session['user_id'])
    artworks = Artwork.query.filter_by(picked_by_admin_id=admin_id, approval_status='Pending').all()

    return render_template('admin/artwork_approval_admin/artwork_approval_workspace.html', artworks=artworks)



@admin_interface.route('/pick_artwork/<uuid:artwork_id>', methods=['POST'])
def pick_artwork(artwork_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to pick artworks.")
        return redirect(url_for('admin.admin_login'))

    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork.picked_by_admin_id:
        flash("This artwork has already been picked by another admin.")
        return redirect(url_for('admin.artwork_approval_admin_dashboard'))

    # Assign the artwork to the current admin
    artwork.picked_by_admin_id = uuid.UUID(session['user_id'])
    db.session.commit()

    flash(f"Artwork '{artwork.title}' has been added to your workspace.")
    return redirect(url_for('admin.artwork_approval_admin_dashboard'))


@admin_interface.route('/unpick_artwork/<uuid:artwork_id>', methods=['POST'])
def unpick_artwork(artwork_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to unpick artworks.")
        return redirect(url_for('admin.admin_login'))

    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork.picked_by_admin_id != uuid.UUID(session['user_id']):
        flash("You can only unpick artworks from your own workspace.")
        return redirect(url_for('admin.artwork_approval_workspace'))

    # Unassign the artwork
    artwork.picked_by_admin_id = None
    db.session.commit()

    flash(f"Artwork '{artwork.title}' has been removed from your workspace.")
    return redirect(url_for('admin.artwork_approval_workspace'))




@admin_interface.route('/approve_artwork/<uuid:artwork_id>', methods=['POST'])
def approve_artwork(artwork_id):
    # Ensure the user is logged in as an Artwork Approval Admin
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to approve artworks.")
        return redirect(url_for('admin.admin_login'))

    # Retrieve the artwork
    artwork = Artwork.query.get(artwork_id)
    if not artwork or artwork.approval_status != 'Pending':
        flash("Invalid artwork or it is not pending approval.")
        return redirect(url_for('admin.artwork_approval_admin_dashboard'))

    # Update artwork status to approved and record the approving admin's ID
    artwork.approval_status = 'Approved'
    artwork.approval_admin_id = uuid.UUID(session['user_id'])
    db.session.commit()
    
    # Send notification to the artist about approval
    artist_id = artwork.artist_id
    message = f"Your artwork '{artwork.title}' has been approved."
    Notification.send_notification(user_id=artist_id, message=message,type='artwork')

    flash(f"Artwork '{artwork.title}' has been approved.")
    return redirect(url_for('admin.artwork_approval_workspace'))


@admin_interface.route('/disapprove_artwork/<uuid:artwork_id>', methods=['GET', 'POST'])
def disapprove_artwork(artwork_id):
    # Ensure the user is logged in as an Artwork Approval Admin
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to disapprove artworks.")
        return redirect(url_for('admin.admin_login'))

    # Retrieve the artwork
    artwork = Artwork.query.get_or_404(artwork_id)

    # Handle POST request
    if request.method == 'POST':
        # Retrieve the disapproval reason from the form
        reason = request.form.get('disapprove_reason', None)
        if reason:
            # Update artwork status to disapproved, add the reason, and record the admin's ID
            artwork.approval_status = 'Disapproved'
            artwork.disapproval_reason = reason
            artwork.approval_admin_id = uuid.UUID(session['user_id'])
            db.session.commit()

            # Send notification to the artist about disapproval
            artist_id = artwork.artist_id
            message = f"Your artwork '{artwork.title}' has been disapproved. Reason: {reason}"
            link = url_for('user_interface.view_artwork_disapproval_reason', artwork_id=artwork.id, _external=True)  # Link to view disapproval reason
            Notification.send_notification(user_id=artist_id, message=message, link=link,type='artwork')

            flash(f"Artwork '{artwork.title}' has been disapproved.")
            return redirect(url_for('admin.artwork_approval_workspace'))
        else:
            flash("Please provide a reason for disapproval.")
            return render_template('admin/artwork_approval_admin/disapprove_artwork.html', artwork=artwork)

    # GET request - render the form
    return render_template('admin/artwork_approval_admin/disapprove_artwork.html', artwork=artwork)


# order management admin dashboard, update product status


@admin_interface.route('/order_management_admin_dashboard', methods=['GET'])
def order_management_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dashboard.")
        return redirect(url_for('admin.admin_login'))

    try:
        admin_id = uuid.UUID(session['user_id'])
        unread_notifications_count = Notification.get_unread_notifications_count(admin_id)
    except ValueError:
        flash("Invalid session user ID.")
        return redirect(url_for('admin.admin_login'))

    # Get products assigned to the logged-in admin
    products = Product.query.filter_by(assigned_admin_id=admin_id).all()

    # Fetch only active production rounds for this admin
    production_rounds = ProductionRound.query.filter_by(admin_id=admin_id, is_active=True).all()

    return render_template(
        'admin/order_management_admin/order_management_admin_dashboard.html',
        products=products,
        production_rounds=production_rounds,
        unread_notifications_count=unread_notifications_count
    )



# the product management: information (manage_product) and display status (toggle_product_display_status)


@admin_interface.route('/manage_product/<uuid:product_id>', methods=['GET', 'POST'])
def manage_product(product_id):
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dashboard.")
        return redirect(url_for('admin.admin_login'))

    # Fetch the product by ID
    product = Product.query.get(product_id)

    if not product:
        flash("Product not found.", 'error')
        return redirect(url_for('admin.order_management_admin_dashboard'))

    flash_message = None  # Initialize as None, used to pass context to the HTML

    if request.method == 'POST':
        if 'toggle_display_status' in request.form:
            # Toggle display status
            product.toggle_display_status()
            flash_message = f"Display status for '{product.name}' updated to '{product.display_status}'."
        elif 'update_introduction' in request.form:
            # Update product introduction
            introduction = request.form.get('introduction', '').strip()
            if introduction:
                product.introduction = introduction
                db.session.commit()
                flash_message = "Introduction successfully uploaded."
            else:
                flash_message = "Introduction cannot be empty."

    return render_template('admin/order_management_admin/manage_product.html', product=product, flash_message=flash_message)



@admin_interface.route('/toggle_product_display_status/<uuid:product_id>', methods=['POST'])
def toggle_product_display_status(product_id):
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to change product display status.")
        return redirect(url_for('admin.admin_login'))

    product = Product.query.get(product_id)

    # Ensure the product exists and is in an approved state
    if product and product.production_status == 'Approved':
        product.toggle_display_status()
        flash(f"Display status for '{product.name}' updated to '{product.display_status}'.")
    else:
        flash("Invalid product or product is not approved.", "error")

    return redirect(url_for('admin.manage_product', product_id=product.id))



# the production management: initialize production round if the artist choose so (admin_manage_production_round)
# manage production round's information (manage_production_round), display status (publish_production_round)

@admin_interface.route('/admin_initialize_production_round/<uuid:product_id>', methods=['POST'])
def admin_initialize_production_round(product_id):
    """Admin initializes a production round."""
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Admin to initialize production rounds.")
        return redirect(url_for('admin.admin_login'))

    try:
        product = Product.query.get_or_404(product_id)
        if product.assigned_admin_id != uuid.UUID(session['user_id']):
            flash("Unauthorized access to this product.")
            return redirect(url_for('admin.admin_dashboard'))

        if product.artist_controlled:
            flash("Production round initialization is controlled by the artist.")
            return redirect(url_for('admin.admin_dashboard'))

        # Check if an active production round already exists
        existing_round = ProductionRound.query.filter_by(product_id=product.id, is_active=True).first()
        if existing_round:
            flash("An in-progress production round already exists. You cannot initialize a new one.")
            return redirect(url_for('admin.admin_manage_production_round', product_id=product.id))

        # Create a new production round
        max_waiting_time_days = 60  # Default waiting period in days
        max_waiting_time = datetime.now() + timedelta(days=max_waiting_time_days)

        new_round = ProductionRound(
            product_id=product.id,
            artist_id=product.artist_id,
            admin_id=uuid.UUID(session['user_id']),
            max_waiting_time=max_waiting_time,
            stage="initialize",
            is_published=False,
            is_active=True,  # Set the new round as active
            created_at=datetime.now(),  # Explicit initialization (optional)
            updated_at=datetime.now()   # Explicit initialization (optional)
        )
        db.session.add(new_round)
        db.session.commit()

        flash("Production round initialized successfully.")
        return redirect(url_for('admin.admin_manage_production_round', product_id=product.id))

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('admin.admin_dashboard'))


# the admin would manage the initialized production round
# there would be a confirmation page, after confirmation, it will be updated



@admin_interface.route('/admin_manage_production_round/<uuid:product_id>', methods=['GET', 'POST'])
def admin_manage_production_round(product_id):
    logging.basicConfig(level=logging.DEBUG)

    try:
        logging.debug("Entering admin_manage_production_round route.")
        logging.debug(f"Received product_id: {product_id}")

        # Check user authentication and role
        if 'user_id' not in session or session.get('role') != 'order_management_admin':
            logging.debug(f"User not authenticated or incorrect role. Session: {session}")
            flash("You need to be logged in as an admin to manage production rounds.")
            return redirect(url_for('admin.admin_login'))

        # Fetch the active production round
        logging.debug("Fetching the active production round.")
        production_round = ProductionRound.query.filter_by(product_id=product_id, is_active=True).first()

        if not production_round:
            logging.debug(f"No active production round found for product_id: {product_id}")
            flash("No active production round found for this product.")
            return redirect(url_for('admin.order_management_admin_dashboard'))

        logging.debug(f"Production round found: {production_round.id}")

        # Get stage goals
        logging.debug("Fetching stage goals from production_round.")
        stage_goals = production_round.stage_goals
        logging.debug(f"Stage goals: {stage_goals}")

        if request.method == 'POST':
            logging.debug("Processing POST request.")

            # Collect updated data
            updated_data = {
                'price': float(request.form.get('price', production_round.price)),
                'min_production_size': int(request.form.get('min_production_size', production_round.min_production_size)),
                'max_waiting_time': datetime.strptime(request.form.get('max_waiting_time'), '%Y-%m-%d'),
                'stage': request.form.get('stage', production_round.stage),
                'is_published': 'is_published' in request.form,
                'stage_goals': request.form.get('stage_goals', '[]'),  # Leave raw JSON string
            }
            logging.debug(f"Collected updated data: {updated_data}")

            # Serialize stage goals and store in session
            try:
                updated_data['stage_goals'] = json.loads(updated_data['stage_goals'])
                logging.debug(f"Serialized stage_goals for session storage: {updated_data['stage_goals']}")
            except Exception as e:
                logging.error(f"Error serializing stage goals: {e}")
                updated_data['stage_goals'] = []

            session['pending_updates'] = updated_data
            session['round_id'] = str(production_round.id)
            logging.debug("Updated data saved to session.")
            return redirect(url_for('admin.confirm_production_round_update'))

        # Render the management page
        logging.debug("Rendering admin_manage_production_round template.")
        return render_template(
            'admin/order_management_admin/admin_manage_production_round.html',
            production_round=production_round,
            stage_goals=stage_goals,
        )

    except Exception as e:
        logging.error(f"An error occurred in admin_manage_production_round: {e}")
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('admin.admin_login'))





@admin_interface.route('/confirm_production_round_update', methods=['GET', 'POST'])
def confirm_production_round_update():
    try:
        # Fetch data from session
        round_id = session.get('round_id')
        updated_data = session.get('pending_updates')

        if not round_id or not updated_data:
            flash("No updates to confirm.")
            return redirect(url_for('admin.order_management_admin_dashboard'))

        production_round = ProductionRound.query.get(uuid.UUID(round_id))
        if not production_round:
            flash("Production round not found.")
            return redirect(url_for('admin.order_management_admin_dashboard'))

        # Normalize and validate stage goals
        raw_stage_goals = updated_data.get('stage_goals', [])
        logging.debug(f"Stage goals before normalization: {raw_stage_goals}")

        normalized_stage_goals = [
            {
                'quantity': goal.get('quantity') or goal.get('target_quantity'),
                'gift': goal.get('gift')
            }
            for goal in raw_stage_goals
        ]

        # Ensure all keys are present and valid
        for goal in normalized_stage_goals:
            if 'quantity' not in goal or 'gift' not in goal:
                raise ValueError("Each goal must include 'quantity' and 'gift' keys.")
            if not isinstance(goal['quantity'], int) or goal['quantity'] <= 0:
                raise ValueError(f"Invalid quantity in stage goal: {goal}")

        if request.method == 'POST':
            # Update production round fields
            production_round.price = updated_data['price']
            production_round.min_production_size = updated_data['min_production_size']
            production_round.max_waiting_time = updated_data['max_waiting_time']
            production_round.stage = updated_data['stage']
            production_round.is_published = updated_data['is_published']
            production_round.is_active = updated_data['stage'] in ["initialize", "waiting", "sample", "production"]

            # Set validated and normalized stage goals
            production_round.stage_goals = normalized_stage_goals

            # Commit changes
            db.session.commit()

            # Clear session data
            session.pop('pending_updates', None)
            session.pop('round_id', None)

            flash("Production round updates have been confirmed and saved.")
            return redirect(url_for('admin.order_management_admin_dashboard'))

        # Render confirmation page
        return render_template(
            'admin/order_management_admin/confirm_production_round_update.html',
            production_round=production_round,
            updated_data=updated_data,
        )
    except Exception as e:
        logging.error(f"An error occurred in confirm_production_round_update: {e}")
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('admin.admin_login'))






@admin_interface.route('/publish_production_round/<uuid:round_id>', methods=['POST'])
def publish_production_round(round_id):
    """Toggle display status for the production round."""
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to publish this production round.")
        return redirect(url_for('admin.admin_login'))

    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access or invalid production round.")
        return redirect(url_for('admin.order_management_admin_dashboard'))

    production_round.is_published = not production_round.is_published
    db.session.commit()

    flash(f"Production round for product '{production_round.product.name}' display status updated.")
    return redirect(url_for('admin.order_management_admin_dashboard'))



# Product Approval Admin Dashboard, download design file, approve product, disapprove product, assign product to order management admin

@admin_interface.route('/product_approval_admin_dashboard', methods=['GET', 'POST'])
def product_approval_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to access this dashboard.")
        return redirect(url_for('admin.admin_login'))

    search_query = request.args.get('search_query', '').strip()
    search_results = []

    # Fetch all pending products that are not picked by any admin
    pending_products = Product.query.filter_by(production_status='Pending', picked_by_admin_id=None).all()

    if search_query:
        # Filter products based on the search query and manufacture_type
        search_results = Product.query.filter(
            Product.production_status == 'Pending',
            Product.picked_by_admin_id == None,
            Product.manufacture_type.ilike(f"%{search_query}%")
        ).all()

    return render_template(
        'admin/product_approval_admin/product_approval_admin_dashboard.html',
        pending_products=pending_products,
        search_results=search_results,
        search_query=search_query
    )



# search function for the manufactual_type, individual pick and pick-all
# product are first picked to the workspace for approval/disapproval
# The picked product is not going to be displayed on the dashboard.


@admin_interface.route('/search_products', methods=['GET', 'POST'])
def search_products():
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to access this page.")
        return redirect(url_for('admin.admin_login'))

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin.product_approval_admin_dashboard'))

    # Fetch search results
    search_results = Product.query.filter(
        Product.production_status == 'Pending',
        Product.picked_by_admin_id == None,
        Product.production_specs.ilike(f"%{search_query}%")
    ).all()

    if request.method == 'POST':
        # Handle "Pick All Products"
        for product in search_results:
            if not product.picked_by_admin_id:
                product.picked_by_admin_id = uuid.UUID(session['user_id'])
        db.session.commit()
        flash("All products in the search results have been picked.")
        return redirect(url_for('admin.product_approval_admin_dashboard'))

    return render_template(
        'admin/product_approval_admin/search_results.html',
        search_results=search_results,
        search_query=search_query
    )





@admin_interface.route('/pick_product/<uuid:product_id>', methods=['POST'])
def pick_product(product_id):
    """Allow the product approval admin to pick a product."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to pick products.")
        return redirect(url_for('admin.admin_login'))

    admin_id = uuid.UUID(session['user_id'])
    product = Product.query.get_or_404(product_id)

    if product.picked_by_admin_id:
        flash("This product has already been picked by another admin.")
    else:
        admin = ProductApprovalAdmin.query.get(admin_id)
        admin.pick_product(product)
        flash(f"Product '{product.name}' has been added to your workspace.")

    return redirect(url_for('admin.product_approval_admin_dashboard'))


@admin_interface.route('/unpick_product/<uuid:product_id>', methods=['POST'])
def unpick_product(product_id):
    """Allow the product approval admin to unpick a product."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to unpick products.")
        return redirect(url_for('admin.admin_login'))

    admin_id = uuid.UUID(session['user_id'])
    product = Product.query.get_or_404(product_id)

    if product.picked_by_admin_id != admin_id:
        flash("You cannot unpick a product that is not in your workspace.")
    else:
        admin = ProductApprovalAdmin.query.get(admin_id)
        admin.unpick_product(product)
        flash(f"Product '{product.name}' has been removed from your workspace.")

    return redirect(url_for('admin.product_approval_workspace'))


@admin_interface.route('/product_approval_workspace', methods=['GET'])
def product_approval_workspace():
    """Display the workspace of the product approval admin."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to access your workspace.")
        return redirect(url_for('admin.admin_login'))

    admin_id = uuid.UUID(session['user_id'])

    # Fetch picked products with associated artwork details
    picked_products = Product.query.filter_by(
        picked_by_admin_id=admin_id,
        production_status='Pending'  # Exclude products that are already approved or disapproved
    ).all()

    # Build detailed product information for rendering
    product_details = []
    for product in picked_products:
        artwork = product.artwork  # Fetch related artwork
        details = {
            "id": product.id,
            "name": product.name,
            "manufacture_type": product.manufacture_type,
            "production_specs": product.production_specs,
            "artist_name": product.artist.name if product.artist else "Unknown",
            "artwork_title": artwork.title if artwork else "No Artwork",
            "artwork_description": artwork.description if artwork else "No Description",
            "artwork_image_path": artwork.image_path if artwork else "No Image",
            "artwork_manufacturing_specs": artwork.manufacturing_specs if artwork else "No Specs",
            "design_files": product.design_files  # Assuming a list of design files
        }
        product_details.append(details)

    return render_template(
        'admin/product_approval_admin/product_approval_workspace.html',
        picked_products=product_details
    )


@admin_interface.route('/approve_product/<uuid:product_id>', methods=['POST'])
def approve_product(product_id):
    """Redirect to assign an Order Management Admin upon approval initiation."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to approve products.")
        return redirect(url_for('admin.admin_login'))

    # Fetch the product from the database
    product = Product.query.get_or_404(product_id)

    # Ensure the product is in the pending state
    if product.production_status == 'Pending':
        flash(f"Product '{product.name}' approval initiated. Please assign an Order Management Admin.")

        # Notify the artist about the approval initiation
        artist = product.artist
        if artist:
            message = f"Your product '{product.name}' has been marked for approval."
            Notification.send_notification(user_id=artist.id, message=message, type='product')

        # Redirect to the Order Management Admin assignment page
        return redirect(url_for('admin.assign_order_management_admin', product_id=product.id))
    else:
        flash("Invalid product or it is not pending approval.")

    return redirect(url_for('admin.product_approval_workspace'))




@admin_interface.route('/disapprove_product/<uuid:product_id>', methods=['GET', 'POST'])
def disapprove_product(product_id):
    """Disapprove a product with a reason."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to disapprove a product.")
        return redirect(url_for('admin.admin_login'))

    # Fetch the product
    product = Product.query.get_or_404(product_id)

    # Ensure the product is pending
    if product.production_status != 'Pending':
        flash("Invalid product or product is not pending.")
        return redirect(url_for('admin.product_approval_admin_dashboard'))

    if request.method == 'POST':
        # Get the disapproval reason
        reason = request.form.get('disapprove_reason')
        if reason:
            # Update product status
            product.production_status = 'Disapproved'
            product.disapproval_reason = reason
            db.session.commit()

            # Notify the artist
            artist = product.artist
            if artist:
                message = f"Your product '{product.name}' has been disapproved. Reason: {reason}"
                Notification.send_notification(user_id=artist.id, message=message, type='product')

            flash(f"Product '{product.name}' has been disapproved with reason: {reason}")
            return redirect(url_for('admin.product_approval_workspace'))
        else:
            flash("Disapproval reason is required.")

    # Render the disapproval form on GET requests
    return render_template('admin/product_approval_admin/disapprove_product.html', product=product)




@admin_interface.route('/assign_order_management_admin/<uuid:product_id>', methods=['GET', 'POST'])
def assign_order_management_admin(product_id):
    """Assign an Order Management Admin to an approved product."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to assign an Order Management Admin.")
        return redirect(url_for('admin.admin_login'))

    # Fetch the product
    product = Product.query.get_or_404(product_id)
    if product.production_status != 'Pending':
        flash("Invalid product or product is not ready for admin assignment.")
        return redirect(url_for('admin.product_approval_admin_dashboard'))

    search_criteria = {}
    if request.method == 'POST' and 'search' in request.form:
        search_criteria = {
            "admin_id": request.form.get('admin_id'),
            "name": request.form.get('name'),
            "main_production_species": request.form.get('main_production_species'),
        }

    # Filter Order Management Admins based on search criteria
    query = OrderManagementAdmin.query
    if search_criteria.get("admin_id"):
        query = query.filter(OrderManagementAdmin.id == uuid.UUID(search_criteria["admin_id"]))
    if search_criteria.get("name"):
        query = query.filter(OrderManagementAdmin.name.ilike(f"%{search_criteria['name']}%"))
    if search_criteria.get("main_production_species"):
        query = query.filter(OrderManagementAdmin.main_production_species.ilike(f"%{search_criteria['main_production_species']}%"))

    # Sort by the number of products managed
    order_management_admins = query.outerjoin(Product, Product.assigned_admin_id == OrderManagementAdmin.id) \
                                    .group_by(OrderManagementAdmin.id) \
                                    .order_by(db.func.count(Product.id).asc()) \
                                    .all()

    if request.method == 'POST' and 'assign' in request.form:
        admin_id = request.form.get('selected_admin')
        if admin_id:
            try:
                admin = OrderManagementAdmin.query.get(uuid.UUID(admin_id))
                if admin:
                    product.assigned_admin_id = admin.id
                    product.production_status = 'Approved'
                    db.session.commit()

                    flash(f"Product '{product.name}' has been assigned to '{admin.name}' and is now fully approved.")
                    return redirect(url_for('admin.product_approval_workspace'))
                else:
                    flash("Selected Order Management Admin does not exist.")
            except ValueError:
                flash("Invalid Order Management Admin ID format.")

    return render_template(
        'admin/product_approval_admin/assign_order_management_admin.html',
        product=product,
        order_management_admins=order_management_admins,
        search_criteria=search_criteria
    )





@admin_interface.route('/download_file/<uuid:file_id>')
def download_file(file_id):
    if 'user_id' not in session:
        flash("You need to be logged in to download files.")
        return redirect(url_for('admin.admin_login'))

    design_file = DesignFile.query.get(file_id)
    if not design_file:
        flash("File not found.")
        return redirect(request.referrer or url_for('admin.home'))

    # Construct the full file path
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], design_file.filename)

    # Return the file as an attachment
    return send_file(file_path, as_attachment=True)


# View notifications for the logged-in user, unread ones in first page, the read ones are displayed in a separate page
# these are for the admins, which might need to be adjusted...? or just the webpage?
# hmm... but the notification page definitely need to be duplicated for the users (customers and artists) and admins...?
# maybe not, since the notifications are the same for all users, just the roles are different?

@admin_interface.route('/view_notifications', methods=['GET', 'POST'])
def view_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('admin.admin_login'))

    user_id = uuid.UUID(session['user_id'])
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.timestamp.desc()).all()

    # Categorize notifications
    categorized_notifications = {}
    for notification in unread_notifications:
        if notification.type not in categorized_notifications:
            categorized_notifications[notification.type] = []
        categorized_notifications[notification.type].append(notification)

    # Mark notifications as read if requested
    if request.method == 'POST':
        for notification in unread_notifications:
            notification.is_read = True
        db.session.commit()
        flash("All notifications marked as read.")

    return render_template('admin/account/unread_notifications.html', categorized_notifications=categorized_notifications)


@admin_interface.route('/mark_notification_read/<uuid:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    # Ensure the user is logged in
    if 'user_id' not in session:
        flash("You need to be logged in to mark a notification as read.")
        return redirect(url_for('admin.admin_login'))

    try:
        # Find the notification by ID
        notification = Notification.query.get(notification_id)

        # Ensure the notification belongs to the logged-in user
        user_id = uuid.UUID(session['user_id'])
        if notification.user_id != user_id:
            flash("You are not authorized to mark this notification as read.")
            return redirect(url_for('admin.view_notifications'))

        # Mark the notification as read
        notification.is_read = True
        db.session.commit()
        flash("Notification has been marked as read.")

    except Exception as e:
        flash("An error occurred while trying to mark the notification as read.")

    return redirect(url_for('admin.account/view_notifications'))




@admin_interface.route('/view_read_notifications', methods=['GET', 'POST'])
def view_read_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('admin.admin_login'))

    user_id = uuid.UUID(session['user_id'])
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=True).order_by(Notification.timestamp.desc()).all()

    # Categorize notifications
    categorized_notifications = {}
    for notification in unread_notifications:
        if notification.type not in categorized_notifications:
            categorized_notifications[notification.type] = []
        categorized_notifications[notification.type].append(notification)

    return render_template('admin/account/read_notifications.html', categorized_notifications=categorized_notifications)



@admin_interface.route('/product_dialog/<uuid:product_id>', methods=['GET', 'POST'])
def admin_active_product_dialog(product_id):
    """Dialog for the current active production round."""
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dialog.")
        return redirect(url_for('admin.admin_login'))

    # Fetch the active production round
    production_round = ProductionRound.query.filter_by(product_id=product_id, is_active=True).first()
    if not production_round:
        flash("No active production round found for this product.")
        return redirect(url_for('admin.admin_dashboard'))

    # Check if the admin is authorized
    if production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access to this dialog.")
        return redirect(url_for('admin.admin_dashboard'))

    if request.method == 'POST':
        message = request.form.get('message')
        uploaded_files = request.files.getlist('files')

        # Create and save a new message
        new_message = Dialog(
            production_round_id=production_round.id,
            sender_id=uuid.UUID(session['user_id']),
            message=message or '[File Attached]',
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(new_message)
        db.session.commit()

        # Handle file uploads
        upload_folder = current_app.config['UPLOAD_FOLDER']
        for file in uploaded_files:
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file_path = os.path.join(upload_folder, filename)

                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)

                file.save(file_path)

                new_file = DialogFile(
                    dialog_id=new_message.id,
                    file_path=f'uploads/{filename}',
                    file_name=filename,
                    upload_date=datetime.now(timezone.utc)
                )
                db.session.add(new_file)

        db.session.commit()
        flash("Message and files sent.")

        # Notify the artist
        recipient_id = production_round.artist_id
        Notification.send_notification(
            user_id=recipient_id,
            message=f"You have a new message in the production round for '{production_round.product.name}'.",
            link=url_for('user_interface.artist_active_product_dialog', product_id=production_round.product_id, _external=True),
            type='dialog'
        )

    # Fetch all messages in this dialog
    messages = Dialog.query.filter_by(production_round_id=production_round.id).order_by(Dialog.timestamp).all()

    return render_template('admin/order_management_admin/product_dialog.html', production_round=production_round, messages=messages)





@admin_interface.route('/historical_dialog_collection/<uuid:product_id>', methods=['GET'])
def admin_historical_dialog_collection(product_id):
    """List historical dialogs for a product."""
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to view historical dialogs.")
        return redirect(url_for('admin.admin_login'))

    # Fetch all historical production rounds for the given product
    historical_rounds = ProductionRound.query.filter_by(product_id=product_id, is_active=False).all()

    if not historical_rounds:
        flash("No historical production rounds found for this product.")
        return redirect(url_for('admin.admin_dashboard'))

    product = Product.query.get(product_id)

    return render_template(
        'admin/order_management_admin/historical_dialog_collection.html',
        product=product,
        historical_rounds=historical_rounds
    )


@admin_interface.route('/historical_dialog/<uuid:round_id>', methods=['GET'])
def admin_historical_product_dialog(round_id):
    """Read-only dialog for a historical production round."""
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dialog.")
        return redirect(url_for('admin.admin_login'))

    # Fetch the historical production round
    production_round = ProductionRound.query.filter_by(id=round_id, is_active=False).first()
    if not production_round:
        flash("No historical production round found.")
        return redirect(url_for('admin.admin_dashboard'))

    # Check if the admin is authorized
    if production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access to this dialog.")
        return redirect(url_for('admin.admin_dashboard'))

    # Fetch all messages in this dialog
    messages = Dialog.query.filter_by(production_round_id=production_round.id).order_by(Dialog.timestamp).all()

    return render_template('admin/order_management_admin/historical_dialog.html', production_round=production_round, messages=messages)
