from flask import request, Blueprint,current_app, render_template, render_template_string, redirect, url_for, session, flash, current_app, send_file, jsonify
from datetime import datetime, timezone,timedelta
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import cast, String
from app.models import *
# this line needs modification
from app.extensions import db
import uuid
import uuid6
from sqlalchemy.dialects.postgresql import UUID
import pyotp
import json

# login page for the admins, which is different from the user login page (for customers and artists)


admin_interface = Blueprint('admin_interface', __name__)

@admin_interface.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Check if the email belongs to any admin role
        admin = (ArtworkApprovalAdmin.query.filter_by(email=email).first() or
           OrderManagementAdmin.query.filter_by(email=email).first() or
           ProductApprovalAdmin.query.filter_by(email=email).first() or
           WarehouseAdmin.query.filter_by(email=email).first() or 
           DeliveryAdmin.query.filter_by(email=email).first() or
           InfoAdmin.query.filter_by(email=email).first()
           )

        if admin and check_password_hash(admin.password_hash, password):
            session['user_id'] = str(admin.id)
            session['role'] = admin.role
            flash("Admin login successful!")

            # Redirect to the appropriate admin dashboard based on role
            if admin.role == 'artwork_approval_admin':
                return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))
            elif admin.role == 'order_management_admin':
                return redirect(url_for('admin_interface.order_management_admin_dashboard', category='active'))
            elif admin.role == 'product_approval_admin':
                return redirect(url_for('admin_interface.product_approval_admin_dashboard'))
            elif admin.role == 'warehouse_admin':
                return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
            elif admin.role == 'delivery_admin':
                return redirect(url_for('admin_interface.delivery_admin_dashboard'))
            elif admin.role == 'info_admin':
                return redirect(url_for('admin_interface.info_admin_dashboard'))
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
    return redirect(url_for('admin_interface.admin_login'))




# Artwork Approval Admin Dashboard
# search the artwork to be picked
# approve/disapprove artwork
# approve/disapprove artwork update


@admin_interface.route('/artwork_approval_admin_dashboard', methods=['GET', 'POST'])
def artwork_approval_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access this dashboard.")
        return redirect(url_for('admin_interface.admin_login'))

    search_query = request.args.get('search_query', '').strip()

    # Pending Artworks (not picked and pending approval)
    pending_artworks = Artwork.query.filter_by(approval_status='Pending', picked_by_admin_id=None).all()

    # Pending Updates (not picked and pending review)
    pending_updates = ArtworkUpdate.query.filter(
        ArtworkUpdate.status == 'Pending',
        ArtworkUpdate.picked_by_admin_id == None
    ).all()

    # Search functionality (applies to both artworks and updates)
    search_artworks = []
    search_updates = []
    if search_query:
        search_artworks = Artwork.query.filter(
            Artwork.approval_status == 'Pending',
            Artwork.picked_by_admin_id == None,
            Artwork.hard_tags.ilike(f"%{search_query}%")
        ).all()
        search_updates = ArtworkUpdate.query.filter(
            ArtworkUpdate.status == 'Pending',
            ArtworkUpdate.approval_admin_id == None,
            ArtworkUpdate.proposed_hard_tags.ilike(f"%{search_query}%")
        ).all()

    return render_template(
        'admin/artwork_approval_admin/artwork_approval_admin_dashboard.html',
        pending_artworks=pending_artworks,
        pending_updates=pending_updates,
        search_artworks=search_artworks,
        search_updates=search_updates,
        search_query=search_query
    )





# artwork_approval_admin can search artworks by hardtag (ip name) to get selected
# also can pick all the search result to workspace

@admin_interface.route('/search_artworks', methods=['GET', 'POST'])
def search_artworks():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

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
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    return render_template(
        'admin/artwork_approval_admin/artwork_search_results.html',
        search_results=search_results,
        search_query=search_query
    )



# admin picks the artwork from dashboard to personal workspace to approve or disapprove.
# The picked artwork is not going to be displayed on the dashboard.



@admin_interface.route('/artwork_approval_workspace', methods=['GET'])
def artwork_approval_workspace():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access your workspace.")
        return redirect(url_for('admin_interface.admin_login'))

    admin_id = uuid.UUID(session['user_id'])
    artworks = Artwork.query.filter_by(picked_by_admin_id=admin_id, approval_status='Pending').all()

    return render_template('admin/artwork_approval_admin/artwork_approval_workspace.html', artworks=artworks)



@admin_interface.route('/pick_artwork/<uuid6:artwork_id>', methods=['POST'])
def pick_artwork(artwork_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to pick artworks.")
        return redirect(url_for('admin_interface.admin_login'))

    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork.picked_by_admin_id:
        flash("This artwork has already been picked by another admin.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Assign the artwork to the current admin
    artwork.picked_by_admin_id = uuid.UUID(session['user_id'])
    db.session.commit()

    flash(f"Artwork '{artwork.title}' has been added to your workspace.")
    return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))


@admin_interface.route('/unpick_artwork/<uuid6:artwork_id>', methods=['POST'])
def unpick_artwork(artwork_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to unpick artworks.")
        return redirect(url_for('admin_interface.admin_login'))

    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork.picked_by_admin_id != uuid.UUID(session['user_id']):
        flash("You can only unpick artworks from your own workspace.")
        return redirect(url_for('admin_interface.artwork_approval_workspace'))

    # Unassign the artwork
    artwork.picked_by_admin_id = None
    db.session.commit()

    flash(f"Artwork '{artwork.title}' has been removed from your workspace.")
    return redirect(url_for('admin_interface.artwork_approval_workspace'))



@admin_interface.route('/approve_artwork/<uuid6:artwork_id>', methods=['POST'])
def approve_artwork(artwork_id):
    # Ensure the user is logged in as an Artwork Approval Admin
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to approve artworks.")
        return redirect(url_for('admin_interface.admin_login'))

    # Retrieve the artwork
    artwork = Artwork.query.get(artwork_id)
    if not artwork or artwork.approval_status != 'Pending':
        flash("Invalid artwork or it is not pending approval.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Update artwork status to approved and record the approving admin's ID
    artwork.approval_status = 'Approved'
    artwork.approval_admin_id = uuid.UUID(session['user_id'])
    db.session.commit()
    
    # Send notification to the artist about approval
    artist_id = artwork.artist_id
    message = f"Your artwork '{artwork.title}' has been approved."
    Notification.send_notification(user_id=artist_id, message=message,type='artwork')

    flash(f"Artwork '{artwork.title}' has been approved.")
    return redirect(url_for('admin_interface.artwork_approval_workspace'))


@admin_interface.route('/disapprove_artwork/<uuid6:artwork_id>', methods=['GET', 'POST'])
def disapprove_artwork(artwork_id):
    # Ensure the user is logged in as an Artwork Approval Admin
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to disapprove artworks.")
        return redirect(url_for('admin_interface.admin_login'))

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
            return redirect(url_for('admin_interface.artwork_approval_workspace'))
        else:
            flash("Please provide a reason for disapproval.")
            return render_template('admin/artwork_approval_admin/disapprove_artwork.html', artwork=artwork)

    # GET request - render the form
    return render_template('admin/artwork_approval_admin/disapprove_artwork.html', artwork=artwork)




# artwork update


@admin_interface.route('/search_artwork_updates', methods=['GET', 'POST'])
def search_artwork_updates():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Fetch search results for artwork updates
    search_results = ArtworkUpdate.query.filter(
        ArtworkUpdate.status == 'Pending',
        ArtworkUpdate.picked_by_admin_id == None,
        ArtworkUpdate.proposed_hard_tags.ilike(f"%{search_query}%")
    ).all()

    if request.method == 'POST':
        # Handle "Pick All Updates"
        for update in search_results:
            if not update.picked_by_admin_id:
                update.picked_by_admin_id = uuid.UUID(session['user_id'])
        db.session.commit()
        flash("All artwork updates in the search results have been picked.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    return render_template(
        'admin/artwork_approval_admin/artwork_update_search_result.html',
        search_results=search_results,
        search_query=search_query
    )




@admin_interface.route('/artwork_update_workspace', methods=['GET'])
def artwork_update_workspace():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access your workspace.")
        return redirect(url_for('admin_interface.admin_login'))

    admin_id = uuid.UUID(session['user_id'])
    updates = ArtworkUpdate.query.filter_by(picked_by_admin_id=admin_id, status='Pending').all()

    return render_template('admin/artwork_approval_admin/artwork_update_workspace.html', updates=updates)


@admin_interface.route('/pick_artwork_update/<uuid6:update_id>', methods=['POST'])
def pick_artwork_update(update_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to pick updates.")
        return redirect(url_for('admin_interface.admin_login'))

    update = ArtworkUpdate.query.get_or_404(update_id)

    if update.picked_by_admin_id:
        flash("This update has already been picked by another admin.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Assign the update to the current admin
    update.picked_by_admin_id = uuid.UUID(session['user_id'])
    db.session.commit()

    flash(f"Update for artwork '{update.artwork.title}' has been added to your workspace.")
    return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))




@admin_interface.route('/unpick_artwork_update/<uuid6:update_id>', methods=['POST'])
def unpick_artwork_update(update_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to unpick updates.")
        return redirect(url_for('admin_interface.admin_login'))

    update = ArtworkUpdate.query.get_or_404(update_id)

    if update.picked_by_admin_id != uuid.UUID(session['user_id']):
        flash("You can only unpick updates from your own workspace.")
        return redirect(url_for('admin_interface.artwork_update_workspace'))

    # Unassign the update
    update.picked_by_admin_id = None
    db.session.commit()

    flash(f"Update for artwork '{update.artwork.title}' has been removed from your workspace.")
    return redirect(url_for('admin_interface.artwork_update_workspace'))



@admin_interface.route('/approve_artwork_update/<uuid6:update_id>', methods=['POST'])
def approve_artwork_update(update_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to approve updates.")
        return redirect(url_for('admin_interface.admin_login'))

    update = ArtworkUpdate.query.get_or_404(update_id)

    if update.status != 'Pending':
        flash("Invalid update or it is not pending approval.")
        return redirect(url_for('admin_interface.artwork_update_workspace'))

    # Apply the update to the artwork
    artwork = update.artwork
    if update.proposed_title:
        artwork.title = update.proposed_title
    if update.proposed_description:
        artwork.description = update.proposed_description
    if update.proposed_manufacturing_specs:
        artwork.manufacturing_specs = update.proposed_manufacturing_specs
    if update.proposed_hard_tags:
        artwork.hard_tags = update.proposed_hard_tags
    if update.proposed_soft_tags:
        artwork.soft_tags = update.proposed_soft_tags

    # Mark the update as approved
    update.status = 'Approved'
    update.approval_admin_id = uuid.UUID(session['user_id'])
    update.reviewed_at = datetime.now()
    db.session.commit()

    # Send notification to the artist about approval of the update
    artist_id = artwork.artist_id
    message = f"Your artwork '{artwork.title}' has been updated."
    Notification.send_notification(user_id=artist_id, message=message,type='artwork')


    flash(f"Update for artwork '{artwork.title}' has been approved.")
    return redirect(url_for('admin_interface.artwork_update_workspace'))



@admin_interface.route('/disapprove_artwork_update/<uuid6:update_id>', methods=['GET', 'POST'])
def disapprove_artwork_update(update_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to disapprove updates.")
        return redirect(url_for('admin_interface.admin_login'))

    # Retrieve the update
    update = ArtworkUpdate.query.get_or_404(update_id)

    if request.method == 'POST':
        reason = request.form.get('disapprove_reason', None)
        if reason:
            # Update the status and other details
            update.status = 'Disapproved'
            update.disapproval_reason = reason
            update.approval_admin_id = uuid.UUID(session['user_id'])
            update.reviewed_at = datetime.now()
            db.session.commit()

            # Send notification to the artist on the reason
            artist_id = update.artist_id
            message = f"Your artwork update for '{update.artwork.title}' has been disapproved. Reason: {reason}"
            Notification.send_notification(user_id=artist_id, message=message, type='artwork_update')

            flash(f"Update for artwork '{update.artwork.title}' has been disapproved.")
            return redirect(url_for('admin_interface.artwork_update_workspace'))
        else:
            flash("Please provide a reason for disapproval.")

    return render_template('admin/artwork_approval_admin/disapprove_artwork_update.html', update=update)




@admin_interface.route('/search_updates', methods=['GET', 'POST'])
def search_updates():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    # Fetch search results for updates
    search_results = ArtworkUpdate.query.filter(
        ArtworkUpdate.status == 'Pending',
        ArtworkUpdate.approval_admin_id == None,
        ArtworkUpdate.proposed_hard_tags.ilike(f"%{search_query}%")
    ).all()

    if request.method == 'POST':
        # Handle "Pick All Updates"
        for update in search_results:
            if not update.approval_admin_id:
                update.approval_admin_id = uuid.UUID(session['user_id'])
        db.session.commit()
        flash("All updates in the search results have been picked.")
        return redirect(url_for('admin_interface.artwork_approval_admin_dashboard'))

    return render_template(
        'admin/artwork_approval_admin/search_updates.html',
        search_results=search_results,
        search_query=search_query
    )




# order management admin dashboard, update product status


@admin_interface.route('/order_management_admin_dashboard/<category>', methods=['GET'])
def order_management_admin_dashboard(category):
    """Displays different categories of products based on the selected category."""
    
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dashboard.")
        return redirect(url_for('admin_interface.admin_login'))

    try:
        admin_id = uuid.UUID(session['user_id'])
        unread_notifications_count = Notification.get_unread_notifications_count(admin_id)
    except ValueError:
        flash("Invalid session user ID.")
        return redirect(url_for('admin_interface.admin_login'))

    # Fetch products assigned to the admin
    products = Product.query.filter_by(assigned_admin_id=admin_id).all()

    products_with_active_rounds = {}

    # Categorize products
    active_products = []
    platform_controlled_products = []
    customer_controlled_products = []

    for product in products:
        active_round = ProductionRound.query.filter_by(product_id=product.id, is_active=True).first()

        if active_round:
            active_products.append(product)
            products_with_active_rounds[product.id] = {
                "round": active_round,
                "is_published": active_round.is_published,
                "total_items_ordered": active_round.total_items_ordered,
                "artwork_image": product.artwork.image_path if product.artwork else None
            }
        else:
            if product.artist_controlled:
                customer_controlled_products.append(product)
            else:
                platform_controlled_products.append(product)

    # Determine which category to render
    if category == "active":
        products_to_display = active_products
    elif category == "platform":
        products_to_display = platform_controlled_products
    elif category == "customer":
        products_to_display = customer_controlled_products
    else:
        flash("Invalid category selected.")
        return redirect(url_for('admin_interface.order_management_admin_dashboard', category="active"))

    return render_template(
        'admin/order_management_admin/order_management_admin_dashboard.html',
        category=category,
        products=products_to_display,
        products_with_active_rounds=products_with_active_rounds,
        unread_notifications_count=unread_notifications_count
    )





# the product management: information (manage_product) and display status (toggle_product_display_status)


@admin_interface.route('/manage_product/<uuid6:product_id>', methods=['GET', 'POST'])
def manage_product(product_id):
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dashboard.")
        return redirect(url_for('admin_interface.admin_login'))

    # Fetch the product by ID
    product = Product.query.get(product_id)

    if not product:
        flash("Product not found.", 'error')
        return redirect(url_for('admin_interface.order_management_admin_dashboard', category= "active"))

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



@admin_interface.route('/toggle_product_display_status/<uuid6:product_id>', methods=['POST'])
def toggle_product_display_status(product_id):
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to change product display status.")
        return redirect(url_for('admin_interface.admin_login'))

    product = Product.query.get(product_id)

    # Ensure the product exists and is in an approved state
    if product and product.production_status == 'Approved':
        product.toggle_display_status()
        flash(f"Display status for '{product.name}' updated to '{product.display_status}'.")
    else:
        flash("Invalid product or product is not approved.", "error")

    return redirect(url_for('admin_interface.manage_product', product_id=product.id))



# the production management: initialize production round if the artist choose so (admin_manage_production_round)
# manage production round's information (manage_production_round), display status (publish_production_round)

@admin_interface.route('/admin_initialize_production_round/<uuid6:product_id>', methods=['POST'])
def admin_initialize_production_round(product_id):
    """Admin initializes a production round."""
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Admin to initialize production rounds.")
        return redirect(url_for('admin_interface.admin_login'))

    try:
        product = Product.query.get_or_404(product_id)
        if product.assigned_admin_id != uuid.UUID(session['user_id']):
            flash("Unauthorized access to this product.")
            return redirect(url_for('admin_interface.admin_dashboard'))

        if product.artist_controlled:
            flash("Production round initialization is controlled by the artist.")
            return redirect(url_for('admin_interface.admin_dashboard'))

        # Check if an active production round already exists
        existing_round = ProductionRound.query.filter_by(product_id=product.id, is_active=True).first()
        if existing_round:
            flash("An in-progress production round already exists. You cannot initialize a new one.")
            return redirect(url_for('admin_interface.admin_manage_production_round', product_id=product.id))

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
            created_at=datetime.now(),
            updated_at=datetime.now()   # Explicit initialization (optional)
        )
        db.session.add(new_round)
        db.session.commit()

        flash("Production round initialized successfully.")
        return redirect(url_for('admin_interface.admin_manage_production_round', product_id=product.id))

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('admin_interface.admin_dashboard'))


# the admin would manage the initialized production round
# there would be a confirmation page, after confirmation, it will be updated



@admin_interface.route('/admin_manage_production_round/<uuid6:product_id>', methods=['GET', 'POST'])
def admin_manage_production_round(product_id):

    try:
        # Check user authentication and role
        if 'user_id' not in session or session.get('role') != 'order_management_admin':
            flash("You need to be logged in as an admin to manage production rounds.")
            return redirect(url_for('admin_interface.admin_login'))

        # Fetch the active production round
        production_round = ProductionRound.query.filter_by(product_id=product_id, is_active=True).first()

        if not production_round:
            flash("No active production round found for this product.")
            return redirect(url_for('admin_interface.order_management_admin_dashboard', category= "active"))


        # Get stage goals
        stage_goals = production_round.stage_goals

        if request.method == 'POST':

            # Collect updated data
            updated_data = {
                'price': float(request.form.get('price', production_round.price)),
                'min_production_size': int(request.form.get('min_production_size', production_round.min_production_size)),
                'delivery_point': int(request.form.get('delivery_point', production_round.delivery_point)),
                'max_waiting_time': datetime.strptime(request.form.get('max_waiting_time'), '%Y-%m-%d'),
                'stage': request.form.get('stage', production_round.stage),
                'is_published': 'is_published' in request.form,
                'stage_goals': request.form.get('stage_goals', '[]'),  # Leave raw JSON string
            }

            # Check if the stage is "sample" and allow partial_refund input
            if updated_data['stage'] == 'sample':
                updated_data['partial_refund'] = float(request.form.get('partial_refund', production_round.partial_refund or 0))
                        

            # Serialize stage goals and store in session
            try:
                updated_data['stage_goals'] = json.loads(updated_data['stage_goals'])
            except Exception as e:
                updated_data['stage_goals'] = []

            session['pending_updates'] = updated_data
            session['round_id'] = str(production_round.id)
            return redirect(url_for('admin_interface.confirm_production_round_update'))

        # Render the management page
        return render_template(
            'admin/order_management_admin/admin_manage_production_round.html',
            production_round=production_round,
            stage_goals=stage_goals,
        )

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('admin_interface.admin_login'))





from flask import url_for, flash, redirect, request, session, render_template
from datetime import datetime
from collections import defaultdict
import logging

@admin_interface.route('/confirm_production_round_update', methods=['GET', 'POST'])
def confirm_production_round_update():
    try:
        # Fetch data from session
        round_id = session.get('round_id')
        updated_data = session.get('pending_updates')

        if not round_id or not updated_data:
            flash("No updates to confirm.")
            return redirect(url_for('admin_interface.order_management_admin_dashboard', category="active"))

        production_round = ProductionRound.query.get(uuid.UUID(round_id))
        if not production_round:
            flash("Production round not found.")
            return redirect(url_for('admin_interface.order_management_admin_dashboard', category="active"))

        # Normalize and validate stage goals
        raw_stage_goals = updated_data.get('stage_goals', [])
        normalized_stage_goals = [
            {
                'quantity': goal.get('quantity') or goal.get('target_quantity'),
                'gift': goal.get('gift')
            }
            for goal in raw_stage_goals
        ]
        for goal in normalized_stage_goals:
            if 'quantity' not in goal or 'gift' not in goal:
                raise ValueError("Each goal must include 'quantity' and 'gift' keys.")
            if not isinstance(goal['quantity'], int) or goal['quantity'] <= 0:
                raise ValueError(f"Invalid quantity in stage goal: {goal}")

        if request.method == 'POST':
            # Update production round fields
            production_round.price = updated_data['price']
            production_round.min_production_size = updated_data['min_production_size']
            production_round.delivery_point = updated_data['delivery_point']
            production_round.max_waiting_time = updated_data['max_waiting_time']
            production_round.stage = updated_data['stage']
            production_round.is_published = updated_data['is_published']
            production_round.is_active = updated_data['stage'] in ["initialize", "waiting", "sample", "production", "examination"]
            production_round.stage_goals = normalized_stage_goals

            if updated_data['stage'] == 'sample':
                if 'partial_refund' not in updated_data or updated_data['partial_refund'] < 0:
                    flash("Partial refund amount must be a positive value.")
                    return redirect(url_for('admin_interface.confirm_production_round_update'))
                production_round.partial_refund = updated_data['partial_refund']

            db.session.commit()
            logging.info(f"Production round {round_id} updated to stage: {production_round.stage}, is_active: {production_round.is_active}")

            # Inline refund logic for "abandon" stage
            if updated_data['stage'] == "abandon":
                logging.info(f"Detected 'abandon' stage for round {round_id}. Starting refund process.")

                if production_round.price is None:
                    logging.warning(f"No price set for round {round_id}. Skipping refunds.")
                    flash("Cannot process refunds: No price set.", "warning")
                else:
                    # Find items to refund
                    items_to_refund = ItemOrderItem.query.filter_by(
                        production_round_id=production_round.id,
                        item_status="item"
                    ).all()
                    logging.info(f"Found {len(items_to_refund)} items with status 'item' for refund.")

                    if not items_to_refund:
                        logging.info("No items to refund.")
                        flash("No eligible items to refund.", "info")
                    else:
                        refund_records = []
                        for item in items_to_refund:
                            if not item.item_order or not item.item_order.customer_id:
                                logging.error(f"Item {item.id} has no valid order or customer.")
                                continue
                            if not item.region or item.region.tax_rate is None:
                                logging.error(f"Item {item.id} has no valid region or tax rate.")
                                continue

                            customer_id = item.item_order.customer_id
                            refund_amount = production_round.price * (item.region.tax_rate + 1)
                            logging.debug(f"Refunding item {item.id} for customer {customer_id}: {refund_amount}")

                            refund_order = RefundItemOrder(
                                customer_id=customer_id,
                                item_order_item_id=item.id,
                                refund_amount=refund_amount,
                                is_auto=True,
                                reason="Production round abandoned",
                                refund_method="wallet",
                                refund_status="processed",
                                refund_timestamp=datetime.now()
                            )
                            refund_records.append(refund_order)
                            item.item_status = "refunded"

                        if refund_records:
                            db.session.add_all(refund_records)
                            db.session.commit()
                            logging.info(f"Created {len(refund_records)} refund records.")

                            # Update customer wallets
                            refunds_by_customer = defaultdict(float)
                            for refund in refund_records:
                                refunds_by_customer[refund.customer_id] += refund.refund_amount

                            for customer_id, total_refund in refunds_by_customer.items():
                                customer = Customer.query.get(customer_id)
                                if not customer:
                                    logging.error(f"Customer {customer_id} not found.")
                                    continue
                                old_balance = customer.wallet_balance
                                customer.wallet_balance += total_refund
                                logging.info(f"Updated wallet for {customer_id}: {old_balance} -> {customer.wallet_balance}")

                                message = f"Refund of {total_refund:.2f} issued for {production_round.product.name} due to abandonment."
                                Notification.send_notification(
                                    user_id=customer_id,
                                    message=message,
                                    type="refund"
                                )
                            db.session.commit()
                            logging.info("Refund process completed successfully.")
                            flash(f"Refunded {len(refund_records)} items successfully.", "success")
                        else:
                            logging.warning("No valid refunds processed.")
                            flash("No valid items refunded due to data issues.", "warning")

            # Notify customers of stage update
            notifications = ProductionRoundNotification.query.filter_by(production_round_id=production_round.id).all()
            for notification in notifications:
                Notification.send_notification(
                    user_id=notification.customer_id,
                    message=f"The production round of {production_round.product.name} has been updated to {production_round.stage}.",
                    type="production_round_update"
                )

            # Clear session data
            session.pop('pending_updates', None)
            session.pop('round_id', None)
            flash("Production round updates confirmed and notifications sent.")
            return redirect(url_for('admin_interface.order_management_admin_dashboard', category="active"))

        # Render confirmation page
        return render_template(
            'admin/order_management_admin/confirm_production_round_update.html',
            production_round=production_round,
            updated_data=updated_data,
        )
    except Exception as e:
        logging.error(f"Error in confirm_production_round_update: {str(e)}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('admin_interface.admin_login'))




@admin_interface.route('/publish_production_round/<uuid6:round_id>', methods=['POST'])
def publish_production_round(round_id):
    """Toggle display status for the production round."""
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to publish this production round.")
        return redirect(url_for('admin_interface.admin_login'))

    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access or invalid production round.")
        return redirect(url_for('admin_interface.order_management_admin_dashboard', category= "active"))

    production_round.is_published = not production_round.is_published
    db.session.commit()

    flash(f"Production round for product '{production_round.product.name}' display status updated.")
    return redirect(url_for('admin_interface.order_management_admin_dashboard', category= "active"))



@admin_interface.route('/send_custom_message/<uuid6:round_id>', methods=['GET', 'POST'])
def send_custom_message(round_id):
    try:
        # Query directly with round_id (UUID object)
        production_round = ProductionRound.query.get(round_id)
        if not production_round:
            flash("Production round not found.")
            return redirect(url_for('admin_interface.order_management_admin_dashboard', category= "active"))

        if request.method == 'POST':
            custom_message = request.form.get('custom_message', '').strip()
            if not custom_message:
                flash("Message cannot be empty.", "error")
                return redirect(url_for('admin_interface.send_custom_message', round_id=round_id))

            # Send notification to all customers in the notification list
            notifications = ProductionRoundNotification.query.filter_by(production_round_id=round_id).all()
            for notification in notifications:
                Notification.send_notification(
                    user_id=notification.customer_id,
                    message=custom_message,
                    type="admin_message"
                )

            flash("Custom message has been sent to all customers in the notification list.", "success")
            return redirect(url_for('admin_interface.order_management_admin_dashboard', category= "active"))

        return render_template(
            'admin/order_management_admin/send_custom_message.html',
            production_round=production_round
        )
    except Exception as e:
        logging.error(f"An error occurred in send_custom_message: {e}")
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('admin_interface.admin_login'))



# archived information for a production round: information and dialog

@admin_interface.route('/archived_production_rounds/<uuid6:product_id>', methods=['GET'])
def archived_production_rounds(product_id):
    """List all inactive production rounds for a specific product."""
    product = Product.query.get(product_id)
    if not product:
        flash("Product not found.")
        return redirect(url_for('admin_interface.order_management_admin_dashboard', category= "active"))

    # Fetch all inactive production rounds for the product
    inactive_rounds = (
        ProductionRound.query.filter_by(product_id=product_id, is_active=False)
        .order_by(ProductionRound.created_at.desc())
        .all()
    )

    return render_template(
        'admin/order_management_admin/archived_production_rounds.html',
        product=product,
        inactive_rounds=inactive_rounds,
    )





@admin_interface.route('/archived_production_round_dialogs/<uuid6:round_id>', methods=['GET'])
def archived_production_round_dialogs(round_id):
    """View archived dialogs of a specific production round."""
    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.is_active:
        flash("Invalid or active production round.")
        return redirect(url_for('admin_interface.order_management_admin_dashboard', category= "active"))

    dialogs = production_round.dialogs  # Retrieve all dialogs for the production round

    # Attach files to each dialog for display
    for dialog in dialogs:
        dialog.files_list = dialog.files  # Collect related files

    return render_template(
        'admin/order_management_admin/archived_production_round_dialogs.html',
        production_round=production_round,
        dialogs=dialogs,
    )




@admin_interface.route('/archived_production_round_details/<uuid6:round_id>', methods=['GET'])
def archived_production_round_details(round_id):
    """View detailed information about an archived production round."""
    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.is_active:
        flash("Invalid or active production round.")
        return redirect(url_for('admin_interface.order_management_admin_dashboard', category= "active"))

    # Extract stage goals (assuming JSON format)
    stage_goals = json.loads(production_round.production_goals or "[]")

    return render_template(
        'admin/order_management_admin/archived_production_round_details.html',
        production_round=production_round,
        stage_goals=stage_goals,
    )




# initialize a request to trasfer the management control to other order_management_admin
# the request would be pick and approved by product_approval_admin
# the ProductManageTransferRequest is going to record the information for operation and history


@admin_interface.route('/initiate_product_transfer', methods=['GET', 'POST'])
def initiate_product_transfer():
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to initiate a transfer.")
        return redirect(url_for('admin_interface.admin_login'))

    admin_id = uuid.UUID(session['user_id'])

    # Get search query from request arguments
    search_query = request.args.get('search_query', '').strip()

    # Subquery to filter out products with a "Pending" ProductManageTransferRequest
    excluded_products = db.session.query(ProductManageTransferRequest.product_id).filter_by(status='Pending')

    # Base query to filter products managed by the current admin and not in excluded_products
    query = Product.query.filter(
        Product.assigned_admin_id == admin_id,
        ~Product.id.in_(excluded_products)
    )

    # Apply search query if provided
    if search_query:
        query = query.filter(
            db.or_(
                cast(Product.id, String).ilike(f"%{search_query}%"),
                Product.name.ilike(f"%{search_query}%"),
                cast(Product.artist_id, String).ilike(f"%{search_query}%"),
                Product.production_specs.ilike(f"%{search_query}%")
            )
        )
    products = query.all()

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        reason = request.form.get('reason')
        if product_id and reason:
            transfer_request = ProductManageTransferRequest(
                product_id=uuid.UUID(product_id),
                current_admin_id=admin_id,
                reason=reason,
                status='Pending',
                submitted_at=datetime.now()
            )
            db.session.add(transfer_request)
            db.session.commit()
            flash("Transfer request has been submitted.")
            return redirect(url_for('admin_interface.initiate_product_transfer'))
        else:
            flash("Please select a product and provide a reason.")

    return render_template(
        'admin/order_management_admin/initiate_product_transfer.html',
        products=products,
        search_query=search_query
    )




# Product Approval Admin Dashboard: approve product; approve product management transfer
# download design file, approve product, disapprove product, assign product to order management admin
# product management transfer from order_management_admin

@admin_interface.route('/product_approval_admin_dashboard', methods=['GET', 'POST'])
def product_approval_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to access this dashboard.")
        return redirect(url_for('admin_interface.admin_login'))

    search_query = request.args.get('search_query', '').strip()

    # Fetch all pending products that are not picked by any admin
    pending_products = Product.query.filter_by(production_status='Pending', picked_by_admin_id=None).all()

    # Fetch all pending product transfer requests not picked by any admin
    pending_transfer_requests = ProductManageTransferRequest.query.filter_by(
        status='Pending', picked_by_admin_id=None
    ).all()

    # Filter products based on the search query
    search_results = []
    if search_query:
        search_results = Product.query.filter(
            Product.production_status == 'Pending',
            Product.picked_by_admin_id == None,
            Product.production_specs.ilike(f"%{search_query}%")
        ).all()

    return render_template(
        'admin/product_approval_admin/product_approval_admin_dashboard.html',
        pending_products=pending_products,
        pending_transfer_requests=pending_transfer_requests,
        search_query=search_query,
        search_results=search_results
    )




# approve product and assign order_management_admin

# search function for the manufactual_type, individual pick and pick-all
# product are first picked to the workspace for approval/disapproval
# The picked product is not going to be displayed on the dashboard.


@admin_interface.route('/search_products', methods=['GET', 'POST'])
def search_products():
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    search_query = request.args.get('search_query', '').strip()

    if not search_query:
        flash("Please enter a search query.")
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

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
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

    return render_template(
        'admin/product_approval_admin/search_results.html',
        search_results=search_results,
        search_query=search_query
    )





@admin_interface.route('/pick_product/<uuid6:product_id>', methods=['POST'])
def pick_product(product_id):
    """Allow the product approval admin to pick a product."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to pick products.")
        return redirect(url_for('admin_interface.admin_login'))

    admin_id = uuid.UUID(session['user_id'])
    product = Product.query.get_or_404(product_id)

    if product.picked_by_admin_id:
        flash("This product has already been picked by another admin.")
    else:
        admin = ProductApprovalAdmin.query.get(admin_id)
        admin.pick_product(product)
        flash(f"Product '{product.name}' has been added to your workspace.")

    return redirect(url_for('admin_interface.product_approval_admin_dashboard'))


@admin_interface.route('/unpick_product/<uuid6:product_id>', methods=['POST'])
def unpick_product(product_id):
    """Allow the product approval admin to unpick a product."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to unpick products.")
        return redirect(url_for('admin_interface.admin_login'))

    admin_id = uuid.UUID(session['user_id'])
    product = Product.query.get_or_404(product_id)

    if product.picked_by_admin_id != admin_id:
        flash("You cannot unpick a product that is not in your workspace.")
    else:
        admin = ProductApprovalAdmin.query.get(admin_id)
        admin.unpick_product(product)
        flash(f"Product '{product.name}' has been removed from your workspace.")

    return redirect(url_for('admin_interface.product_approval_workspace'))


@admin_interface.route('/product_approval_workspace', methods=['GET'])
def product_approval_workspace():
    """Display the workspace of the product approval admin."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to access your workspace.")
        return redirect(url_for('admin_interface.admin_login'))

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


@admin_interface.route('/approve_product/<uuid6:product_id>', methods=['POST'])
def approve_product(product_id):
    """Redirect to assign an Order Management Admin upon approval initiation."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to approve products.")
        return redirect(url_for('admin_interface.admin_login'))

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
        return redirect(url_for('admin_interface.assign_order_management_admin', product_id=product.id))
    else:
        flash("Invalid product or it is not pending approval.")

    return redirect(url_for('admin_interface.product_approval_workspace'))




@admin_interface.route('/disapprove_product/<uuid6:product_id>', methods=['GET', 'POST'])
def disapprove_product(product_id):
    """Disapprove a product with a reason."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to disapprove a product.")
        return redirect(url_for('admin_interface.admin_login'))

    # Fetch the product
    product = Product.query.get_or_404(product_id)

    # Ensure the product is pending
    if product.production_status != 'Pending':
        flash("Invalid product or product is not pending.")
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

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
            return redirect(url_for('admin_interface.product_approval_workspace'))
        else:
            flash("Disapproval reason is required.")

    # Render the disapproval form on GET requests
    return render_template('admin/product_approval_admin/disapprove_product.html', product=product)



@admin_interface.route('/assign_order_management_admin/<uuid6:product_id>', methods=['GET', 'POST'])
def assign_order_management_admin(product_id):
    """Assign an Order Management Admin to an approved product."""
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to assign an Order Management Admin.")
        return redirect(url_for('admin_interface.admin_login'))

    # Fetch the product
    product = Product.query.get_or_404(product_id)
    if product.production_status != 'Pending':
        flash("Invalid product or product is not ready for admin assignment.")
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

    search_criteria = {
        "admin_id": request.form.get("admin_id", "").strip(),
        "name": request.form.get("name", "").strip(),
        "main_production_species": request.form.get("main_production_species", "").strip(),
    }

    # Base query
    query = OrderManagementAdmin.query

    # Fix: Convert admin_id string to UUID for searching
    if search_criteria["admin_id"]:
        try:
            admin_uuid = uuid.UUID(search_criteria["admin_id"])  # Convert string to UUID
            query = query.filter(OrderManagementAdmin.id == admin_uuid)
        except ValueError:
            flash("Invalid UUID format for Admin ID.", "danger")

    if search_criteria["name"]:
        query = query.filter(OrderManagementAdmin.name.ilike(f"%{search_criteria['name']}%"))

    if search_criteria["main_production_species"]:
        query = query.filter(OrderManagementAdmin.main_production_species.ilike(f"%{search_criteria['main_production_species']}%"))

    order_management_admins = query.all()



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
                    return redirect(url_for('admin_interface.product_approval_workspace'))
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





@admin_interface.route('/download_file/<uuid6:file_id>')
def download_file(file_id):
    if 'user_id' not in session:
        flash("You need to be logged in to download files.")
        return redirect(url_for('admin_interface.admin_login'))

    design_file = DesignFile.query.get(file_id)
    if not design_file:
        flash("File not found.")
        return redirect(request.referrer or url_for('admin_interface.home'))

    # Construct the full file path
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], design_file.filename)

    # Return the file as an attachment
    return send_file(file_path, as_attachment=True)



# product management trasfer, request sent from order management admin


@admin_interface.route('/pick_transfer_request/<uuid6:request_id>', methods=['POST'])
def pick_transfer_request(request_id):
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to pick requests.")
        return redirect(url_for('admin_interface.admin_login'))

    transfer_request = ProductManageTransferRequest.query.get_or_404(request_id)
    if transfer_request.picked_by_admin_id:
        flash("This request has already been picked by another admin.")
        return redirect(url_for('admin_interface.product_approval_admin_dashboard'))

    transfer_request.picked_by_admin_id = uuid.UUID(session['user_id'])
    db.session.commit()
    flash("Request has been added to your workspace.")
    return redirect(url_for('admin_interface.product_management_transfer_workspace'))





@admin_interface.route('/product_management_transfer_workspace', methods=['GET'])
def product_management_transfer_workspace():
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to access your workspace.")
        return redirect(url_for('admin_interface.admin_login'))

    admin_id = uuid.UUID(session['user_id'])
    picked_requests = ProductManageTransferRequest.query.filter_by(
        picked_by_admin_id=admin_id, status='Pending'
    ).all()

    return render_template(
        'admin/product_approval_admin/product_management_transfer_workspace.html',
        picked_requests=picked_requests
    )




@admin_interface.route('/approve_transfer_request/<uuid6:request_id>', methods=['GET', 'POST'])
def approve_transfer_request(request_id):
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to approve transfer requests.")
        return redirect(url_for('admin_interface.admin_login'))

    # Retrieve the transfer request
    transfer_request = ProductManageTransferRequest.query.get_or_404(request_id)
    if transfer_request.status != 'Pending':
        flash("This transfer request is not pending approval.")
        return redirect(url_for('admin_interface.product_management_transfer_workspace'))

    search_query = {
        "admin_id": request.args.get("admin_id", "").strip(),
        "name": request.args.get("name", "").strip(),
        "main_production_species": request.args.get("main_production_species", "").strip(),
    }

    # Base query for filtering OrderManagementAdmins
    query = OrderManagementAdmin.query
    if search_query["name"]:
        query = query.filter(OrderManagementAdmin.name.ilike(f"%{search_query['name']}%"))
    if search_query["main_production_species"]:
        query = query.filter(OrderManagementAdmin.main_production_species.ilike(f"%{search_query['main_production_species']}%"))

    # Fetch results
    order_management_admins = query.all()

    if request.method == 'POST':
        selected_admin_id = request.form.get("selected_admin")
        if selected_admin_id:
            try:
                selected_admin = OrderManagementAdmin.query.get(uuid.UUID(selected_admin_id))
                if selected_admin:
                    # Update the product's assigned admin
                    transfer_request.product.assigned_admin_id = selected_admin.id

                    # Mark the transfer request as approved
                    transfer_request.status = 'Approved'
                    transfer_request.reviewed_by = uuid.UUID(session['user_id'])
                    transfer_request.reviewed_at = datetime.now()

                    db.session.commit()

                    # Notify the current and new admins
                    Notification.send_notification(
                        user_id=transfer_request.current_admin_id,
                        message=f"The transfer request for product '{transfer_request.product.name}' has been approved.",
                        type="product_transfer"
                    )
                    Notification.send_notification(
                        user_id=selected_admin.id,
                        message=f"You have been assigned to manage the product '{transfer_request.product.name}'.",
                        type="product_transfer"
                    )

                    flash(f"Product '{transfer_request.product.name}' has been successfully transferred to '{selected_admin.name}'.")
                    return redirect(url_for('admin_interface.product_management_transfer_workspace'))
                else:
                    flash("Selected admin not found.")
            except ValueError:
                flash("Invalid admin ID format.")

    return render_template(
        'admin/product_approval_admin/approve_transfer_request.html',
        transfer_request=transfer_request,
        order_management_admins=order_management_admins,
        search_query=search_query
    )


@admin_interface.route('/disapprove_transfer_request/<uuid6:request_id>', methods=['GET', 'POST'])
def disapprove_transfer_request(request_id):
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to disapprove transfer requests.")
        return redirect(url_for('admin_interface.admin_login'))

    transfer_request = ProductManageTransferRequest.query.get_or_404(request_id)

    if request.method == 'POST':
        reason = request.form.get('disapproval_reason')
        if not reason:
            flash("Please provide a reason for disapproval.")
            return render_template(
                'admin/product_approval_admin/disapprove_transfer_request.html',
                transfer_request=transfer_request
            )

        # Disapprove the transfer request
        transfer_request.status = 'Disapproved'
        transfer_request.disapproval_reason = reason
        transfer_request.reviewed_by = uuid.UUID(session['user_id'])
        transfer_request.reviewed_at = datetime.now()
        db.session.commit()

        # Notify the current admin about disapproval
        Notification.send_notification(
            user_id=transfer_request.current_admin_id,
            message=f"Your transfer request for product '{transfer_request.product.name}' has been disapproved. Reason: {reason}",
            type="product_transfer"
        )

        flash(f"Transfer request for product '{transfer_request.product.name}' has been disapproved.")
        return redirect(url_for('admin_interface.product_management_transfer_workspace'))

    return render_template(
        'admin/product_approval_admin/disapprove_transfer_request.html',
        transfer_request=transfer_request
    )


# warehouse admin section

# warehouse admin dashboard
# choose the production round 

@admin_interface.route('/warehouse_admin/dashboard', methods=['GET', 'POST'])
def warehouse_admin_dashboard():
    """WarehouseAdmin dashboard for managing production rounds."""
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        flash("You must log in as a Warehouse Admin to access this page.", "error")
        return redirect(url_for('admin_interface.admin_login'))

    production_rounds = []
    search_query = None

    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()
        uuid_query = None

        try:
            uuid_query = uuid.UUID(search_query)
        except ValueError:
            uuid_query = None

        if search_query:
            production_rounds = ProductionRound.query.join(Product).filter(
                (ProductionRound.id == uuid_query) |
                (ProductionRound.product_id == uuid_query) |
                (Product.name.ilike(f"%{search_query}%")),
                ProductionRound.stage.in_(["production", "examination", "stocking"])
            ).all()
        else:
            production_rounds = []
    else:
        production_rounds = []

    for round in production_rounds:
        try:
            round.stage_goals = json.loads(round.production_goals) if round.production_goals else []
        except ValueError:
            round.stage_goals = []

    return render_template(
        'admin/warehouse_admin/warehouse_admin_dashboard.html',
        production_rounds=production_rounds,
        search_query=search_query
    )


# Warehouse Storage management: create, search & delete empty Storage


@admin_interface.route('/warehouse_admin/storage', methods=['GET', 'POST'])
def warehouse_storage():
    """Manage warehouse storage: create new locations and search."""
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        flash("You must log in as a Warehouse Admin to access this page.", "danger")
        return redirect(url_for('admin_interface.admin_login'))

    warehouses = Warehouse.query.order_by(Warehouse.name).all()

    if request.method == 'POST':
        location_name = request.form.get('location_name')
        size = request.form.get('size')
        warehouse_id = request.form.get('warehouse_id')

        if not location_name or not size or not warehouse_id:
            flash("Location name, size, and warehouse are required.", "danger")
            return redirect(url_for('admin_interface.warehouse_storage'))

        try:
            size = int(size)
            warehouse_id = int(warehouse_id)

            warehouse = Warehouse.query.get(warehouse_id)
            if not warehouse:
                flash(f"Warehouse ID {warehouse_id} not found.", "danger")
                return redirect(url_for('admin_interface.warehouse_storage'))

            if WarehouseStorage.query.get(location_name):
                flash(f"Storage location '{location_name}' already exists.", "danger")
                return redirect(url_for('admin_interface.warehouse_storage'))

            new_storage = WarehouseStorage(
                location_name=location_name,
                size=size,
                warehouse_id=warehouse_id,
                is_available=True
            )
            db.session.add(new_storage)
            db.session.commit()
            logging.debug(f"Created WarehouseStorage: {location_name} in Warehouse {warehouse.name}")
            flash(f"Storage location '{location_name}'created successfully!", "success")
        except Exception as e:
            db.session.rollback()
            logging.exception(f"Error creating WarehouseStorage: {e}")
            flash(f"An error occurred: {e}", "danger")

        return redirect(url_for('admin_interface.warehouse_storage'))

    return render_template('admin/warehouse_admin/warehouse_storage.html', warehouses=warehouses)




# search storage with location and size.
# for available (empty) storage
# for unavailable (with production round), view the corresponding production round
@admin_interface.route('/warehouse_admin/storage/search', methods=['GET'])
def search_warehouse_storage():
    """Search for storage locations and display results."""
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        flash("You must log in as a Warehouse Admin to access this page.", "danger")
        return redirect(url_for('admin_interface.admin_login'))

    # Fetch all warehouses for context (though not needed for results here)
    warehouses = Warehouse.query.order_by(Warehouse.name).all()

    location_name = request.args.get('location_name', '').strip()
    size = request.args.get('size', '')
    warehouse_id = request.args.get('warehouse_id', '')

    storages = WarehouseStorage.query
    if location_name:
        storages = storages.filter(WarehouseStorage.location_name.ilike(f"%{location_name}%"))
    if size:
        storages = storages.filter(WarehouseStorage.size == int(size))
    if warehouse_id:
        storages = storages.filter(WarehouseStorage.warehouse_id == int(warehouse_id))

    storages = storages.order_by(WarehouseStorage.location_name).all()
    logging.debug(f"Found {len(storages)} storage locations matching criteria")
    return render_template('admin/warehouse_admin/search_warehouse_storage.html', storages=storages, warehouses=warehouses)


# delete storage with is_available=True


@admin_interface.route('/warehouse_admin/storage/delete/<string:storage_name>', methods=['POST'])
def delete_warehouse_storage(storage_name):
    """Delete a storage location if it is available."""
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        flash("You must log in as a Warehouse Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    # Fetch the storage by location_name
    storage = WarehouseStorage.query.get(storage_name)
    if not storage:
        flash("Storage location not found.", "danger")
        return redirect(url_for('admin_interface.search_warehouse_storage'))

    if not storage.is_available:
        flash("Cannot delete storage location because it is currently in use.", "danger")
        return redirect(url_for('admin_interface.search_warehouse_storage'))

    try:
        db.session.delete(storage)
        db.session.commit()
        flash("Storage location deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {e}", "danger")

    return redirect(url_for('admin_interface.search_warehouse_storage'))


# view record with is_available=False

@admin_interface.route('/warehouse_admin/storage/view_record/<string:storage_location>', methods=['GET'])
def view_warehouse_record(storage_location):
    """View the WarehouseRecord associated with an unavailable storage location."""
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        flash("You must log in as a Warehouse Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    # Fetch the storage by location_name
    storage = WarehouseStorage.query.filter_by(location_name=storage_location).first()
    if not storage or storage.is_available:
        flash("No associated record found for this storage location.", "danger")
        return redirect(url_for('admin_interface.search_warehouse_storage'))

    # Fetch associated warehouse record
    warehouse_record = WarehouseRecord.query.filter_by(warehouse_storage_location=storage_location).first()
    if not warehouse_record:
        flash("No record found for this storage location.", "info")
        return redirect(url_for('admin_interface.search_warehouse_storage'))

    # Fetch related product, production round, and artwork
    production_round = warehouse_record.production_round
    product = production_round.product
    artwork = product.artwork  

    # Load production goals as JSON
    stage_goals = []
    if production_round and production_round.production_goals:
        try:
            stage_goals = json.loads(production_round.production_goals)
        except ValueError:
            flash("Error loading stage goals. Please contact support.")

    return render_template(
        'admin/warehouse_admin/view_warehouse_record.html',
        storage=storage,
        warehouse_record=warehouse_record,
        production_round=production_round,
        product=product,
        artwork=artwork,
        stage_goals=stage_goals
    )



@admin_interface.route('/assign_warehouse_to_production_round/<uuid:production_round_id>', methods=['POST'])
def assign_warehouse_to_production_round(production_round_id):
    """
    Assigns a warehouse to all ItemOrderItem records of a given ProductionRound.
    - If `is_accepted` is False:
      1. Updates all items' warehouse records.
      2. Changes `item_status` to "in_stock" if it was "item".
      3. Sets `is_accepted = True` for the production round.
    - If `is_accepted` is True:
      1. Only updates `warehouse_id` for items where `item_status` is "in_stock".
    """
    # Verify warehouse admin role
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        flash("You need to be a Warehouse Admin to perform this action.", "error")
        return redirect(url_for('admin_interface.login'))

    try:
        # Fetch production round
        production_round = ProductionRound.query.get(production_round_id)
        if not production_round:
            flash("Production Round not found.", "error")
            return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

        # Fetch warehouse mappings
        region_warehouse_map = {m.region_id: m.warehouse_id for m in WarehouseRegionMapping.query.all()}
        if not region_warehouse_map:
            flash("No warehouse-region mappings available.", "error")
            return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

        # Process based on acceptance status
        if not production_round.is_accepted:
            items = ItemOrderItem.query.filter_by(production_round_id=production_round_id).all()
            if not items:
                flash("No items found for this Production Round.", "error")
                return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

            for item in items:
                if item.region_id not in region_warehouse_map:
                    flash(f"No warehouse found for region {item.region_id}.", "error")
                    return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
                item.warehouse_id = region_warehouse_map[item.region_id]
                if item.item_status == "item":
                    item.item_status = "in_stock"
                    logging.debug(f"Updated ItemOrderItem {item.id}: status to 'in_stock', warehouse_id={item.warehouse_id}")
                db.session.add(item)
            
            production_round.is_accepted = True
            db.session.add(production_round)

            Notification.send_notification(
                    user_id=production_round.admin_id,
                    message= f"The production round of {production_round.product.name} has been accepted in the warehouse, Update stage to stocking.",
                    type="warehouse_message"
                )
            logging.debug(f"Marked ProductionRound {production_round_id} as accepted")
        else:
            items = ItemOrderItem.query.filter_by(production_round_id=production_round_id, item_status="in_stock").all()
            if not items:
                flash("No 'in_stock' items found to update.", "error")
                return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

            for item in items:
                if item.region_id not in region_warehouse_map:
                    flash(f"No warehouse found for region {item.region_id}.", "error")
                    return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
                item.warehouse_id = region_warehouse_map[item.region_id]
                db.session.add(item)
                logging.debug(f"Updated ItemOrderItem {item.id}: warehouse_id={item.warehouse_id}")

        db.session.commit()
        flash("Warehouse assignment successfully updated.", "success")
        return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))

    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error assigning warehouse to ProductionRound {production_round_id}: {e}")
        flash(f"Failed to assign warehouse: {str(e)}", "error")
        return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
    




# Warehouse Record management, management and report on how to allocate


@admin_interface.route('/warehouse_admin/record/<uuid6:production_round_id>/create', methods=['POST'])
def create_warehouse_record(production_round_id):
    """Create a new warehouse record for a production round."""
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        flash("You must log in as a Warehouse Admin to access this page.", "danger")
        return redirect(url_for('admin_interface.admin_login'))

    production_round = ProductionRound.query.get(production_round_id)
    if not production_round:
        flash("Production round not found.", "danger")
        return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

    try:
        size = int(request.form.get('size', 0))
        warehouse_id = int(request.form.get('warehouse_id', 0))
        quantity = int(request.form.get('quantity', 0))
        description = request.form.get('description', '')
        warehouse_admin_id = uuid.UUID(session['user_id'])

        # Validate warehouse_id against assigned warehouses
        assigned_warehouses = (
            db.session.query(ItemOrderItem.warehouse_id)
            .filter(ItemOrderItem.production_round_id == production_round_id)
            .distinct()
            .all()
        )
        assigned_warehouse_ids = {w.warehouse_id for w in assigned_warehouses if w.warehouse_id}
        if warehouse_id not in assigned_warehouse_ids:
            flash(f"Warehouse ID {warehouse_id} is not assigned to this Production Round.", "danger")
            return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))

        # Fetch warehouse name for error message
        warehouse = Warehouse.query.get(warehouse_id)
        if not warehouse:
            flash(f"Warehouse ID {warehouse_id} not found.", "danger")
            return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))

        # Select the first available storage location
        storage_location = WarehouseStorage.query.filter_by(
            size=size,
            warehouse_id=warehouse_id,
            is_available=True
        ).first()

        if not storage_location:
            flash(f"No available storage location found for Size {size} in Warehouse {warehouse.name}.", "danger")
            return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))

        # Create a new warehouse record
        warehouse_record = WarehouseRecord(
            production_round_id=production_round_id,
            warehouse_storage_location=storage_location.location_name,
            quantity=quantity,
            description=description,
            warehouse_admin_id=warehouse_admin_id
        )
        db.session.add(warehouse_record)
        storage_location.is_available = False
        db.session.add(storage_location)

        db.session.flush()
        logging.debug(f"Flushed WarehouseRecord: {warehouse_record.id}, Storage: {storage_location.location_name}")
        db.session.commit()
        logging.debug(f"Committed WarehouseRecord: {warehouse_record.id} for ProductionRound {production_round_id}")
        flash("Warehouse record created successfully!", "success")

    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error creating WarehouseRecord: {e}")
        flash(f"An error occurred: {e}", "danger")

    return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=production_round_id))



@admin_interface.route('/warehouse_admin/record/<uuid6:production_round_id>', methods=['GET'])
def manage_warehouse_record(production_round_id):
    """Display warehouse records for a production round."""
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        flash("You must log in as a Warehouse Admin to access this page.", "danger")
        return redirect(url_for('admin_interface.admin_login'))

    production_round = ProductionRound.query.get(production_round_id)
    if not production_round:
        flash("Production round not found.", "danger")
        return redirect(url_for('admin_interface.warehouse_admin_dashboard'))
    product = production_round.product
    artwork = product.artwork

    # Fetch existing warehouse records
    warehouse_records = WarehouseRecord.query.filter_by(production_round_id=production_round_id).all()
    logging.debug(f"Fetched {len(warehouse_records)} warehouse records for ProductionRound {production_round_id}")

    return render_template(
        'admin/warehouse_admin/manage_warehouse_record.html',
        artwork=artwork,
        production_round=production_round,
        warehouse_records=warehouse_records
    )







# delete record, free the storage


@admin_interface.route('/warehouse_admin/record/delete/<uuid6:record_id>', methods=['POST'])
def delete_warehouse_record(record_id):
    """Delete a specific warehouse record."""
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        flash("You must log in as a Warehouse Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    warehouse_record = WarehouseRecord.query.get(record_id)
    if not warehouse_record:
        flash("Warehouse record not found.")
        return redirect(url_for('admin_interface.warehouse_admin_dashboard'))

    try:
        # Mark the corresponding storage location as available
        storage_location = WarehouseStorage.query.get(warehouse_record.warehouse_storage_location)
        if storage_location:
            storage_location.is_available = True
            db.session.add(storage_location)

        # Delete the warehouse record
        db.session.delete(warehouse_record)
        db.session.commit()
        flash("Warehouse record deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {e}", "danger")

    return redirect(url_for('admin_interface.manage_warehouse_record', production_round_id=warehouse_record.production_round_id))




# report on how the item should be allocated among the warehouse (according to self-report region and list)


@admin_interface.route('/warehouse_admin/report_data/<uuid6:production_round_id>', methods=['GET'])
def warehouse_allocation_report_data(production_round_id):
    """Fetch warehouse allocation summary for a ProductionRound."""
    if 'user_id' not in session or session['role'] != 'warehouse_admin':
        return jsonify({"error": "Unauthorized access"}), 403

    production_round = ProductionRound.query.get(production_round_id)
    if not production_round:
        return jsonify({"error": "Production round not found"}), 404

    # Fetch warehouse allocation directly from ItemOrderItem with INNER JOIN
    warehouse_data = (
        db.session.query(
            Warehouse.id.label("warehouse_id"),
            Warehouse.name.label("warehouse_name"),
            db.func.count(ItemOrderItem.id).label("quantity")
        )
        .join(Warehouse, Warehouse.id == ItemOrderItem.warehouse_id)  # INNER JOIN
        .filter(ItemOrderItem.production_round_id == production_round_id)
        .group_by(Warehouse.id, Warehouse.name)
        .all()
    )

    # Optional: Include unassigned items
    unassigned_count = (
        db.session.query(db.func.count(ItemOrderItem.id))
        .filter(
            ItemOrderItem.production_round_id == production_round_id,
            ItemOrderItem.warehouse_id.is_(None)
        )
        .scalar()
    )

    # Format summary
    warehouse_summary = {
        str(warehouse_id): {"name": warehouse_name, "quantity": quantity}
        for warehouse_id, warehouse_name, quantity in warehouse_data
    }
    if unassigned_count > 0:
        warehouse_summary["unassigned"] = {"name": "Unassigned", "quantity": unassigned_count}

    return jsonify(warehouse_summary)



# delivery admin

# delivery dashboard
@admin_interface.route('/delivery_admin/dashboard', methods=['GET', 'POST'])
def delivery_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'delivery_admin':
        flash("You must log in as a Delivery Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    delivery_admin = DeliveryAdmin.query.get(session['user_id'])
    warehouse_id = delivery_admin.warehouse_id

    delivery_orders = DeliveryOrder.query.filter(
        DeliveryOrder.warehouse_id == warehouse_id,
        DeliveryOrder.status == "created",
        DeliveryOrder.payment_status == "paid"
    ).all()

    return render_template(
        'admin/delivery_admin/delivery_admin_dashboard.html',
        delivery_orders=delivery_orders,
        selected_warehouse=warehouse_id  # Still passed for display purposes
    )






@admin_interface.route('/delivery_admin/pick_order/<uuid6:order_id>', methods=['POST'])
def pick_delivery_order(order_id):
    """Pick a delivery order and set its status to 'in_process'."""
    delivery_order = DeliveryOrder.query.get_or_404(order_id)

    if delivery_order.status == "created":
        delivery_order.status = "in_process"
        db.session.commit()
    
    return redirect(url_for('admin_interface.delivery_admin_dashboard'))




# delivery admin workspace


@admin_interface.route('/delivery_admin/delivery_admin_workspace/<int:warehouse>', methods=['GET'])
def delivery_admin_workspace(warehouse):
    if 'user_id' not in session or session['role'] != 'delivery_admin':
        flash("You must log in as a Delivery Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    # Validate warehouse exists
    if not Warehouse.query.get(warehouse):
        flash("Invalid warehouse selected.")
        return redirect(url_for('admin_interface.delivery_admin_dashboard'))

    # Fetch "in_process" delivery orders for the selected warehouse
    delivery_orders = DeliveryOrder.query.filter(
        DeliveryOrder.warehouse_id == warehouse,
        DeliveryOrder.status == "in_process"
    ).all()

    if not delivery_orders:
        flash("No in-process orders for this warehouse.")

    grouped_items = {}
    production_round_ids = set()
    order_production_rounds = {}

    for order in delivery_orders:
        order_production_rounds[order.id] = []
        for item in order.delivery_item:
            production_round_id = uuid.UUID(item["production_round_id"])
            grouped_items[production_round_id] = grouped_items.get(production_round_id, 0) + item.get("quantity", 1)
            production_round_ids.add(production_round_id)
            order_production_rounds[order.id].append(production_round_id)

    production_round_details = {
        pr.id: {
            "product_name": pr.product.name,
            "artwork_image": pr.product.artwork.image_path,
            "stage_goals": pr.stage_goals
        }
        for pr in ProductionRound.query.filter(ProductionRound.id.in_(production_round_ids)).all()
    }

    # Corrected warehouse records query
    warehouse_records = WarehouseRecord.query.filter(
        WarehouseRecord.production_round_id.in_(production_round_ids),
        WarehouseRecord.storage_location.has(WarehouseStorage.warehouse_id == warehouse)
    ).all()

    return render_template(
        'admin/delivery_admin/delivery_admin_workspace.html',
        warehouse=warehouse,
        delivery_orders=delivery_orders,
        grouped_items=grouped_items,
        warehouse_records=warehouse_records,
        production_round_details=production_round_details,
        order_production_rounds=order_production_rounds
    )





@admin_interface.route('/delivery_admin/unpick_order/<uuid6:order_id>', methods=['POST'])
def unpick_delivery_order(order_id):
    delivery_order = DeliveryOrder.query.get_or_404(order_id)
    if delivery_order.status == "in_process":
        delivery_order.status = "created"
        db.session.commit()
    return redirect(url_for('admin_interface.delivery_admin_workspace', warehouse=delivery_order.warehouse_id))





# webpage to assign the package to the delivery order
@admin_interface.route('/delivery_admin/assign_delivery_package_view/<uuid:order_id>/<int:warehouse>', methods=['GET'])
def assign_delivery_package_view(order_id, warehouse):
    if 'user_id' not in session or session['role'] != 'delivery_admin':
        flash("You must log in as a Delivery Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    # Fetch and validate the DeliveryOrder
    delivery_order = DeliveryOrder.query.get_or_404(order_id)
    if delivery_order.warehouse_id != warehouse:
        flash("This order does not belong to the selected warehouse.")
        return redirect(url_for('admin_interface.delivery_admin_workspace', warehouse=warehouse))

    # Group items by production round
    grouped_items = {}
    for item_data in delivery_order.delivery_item:
        pr_id = uuid.UUID(item_data["production_round_id"])
        qty = item_data.get("quantity", 1)
        grouped_items[pr_id] = grouped_items.get(pr_id, 0) + qty

    production_round_ids = list(grouped_items.keys())

    # Fetch ProductionRounds for display
    production_rounds = ProductionRound.query.filter(
        ProductionRound.id.in_(production_round_ids)
    ).all()

    production_round_details = {
        pr.id: {
            "product_name": pr.product.name,
            "artwork_image": pr.product.artwork.image_path,
            "stage_goals": pr.stage_goals
        }
        for pr in production_rounds
    }

    # Fetch WarehouseRecords with corrected warehouse filter
    warehouse_records = WarehouseRecord.query.filter(
        WarehouseRecord.production_round_id.in_(production_round_ids),
        WarehouseRecord.storage_location.has(WarehouseStorage.warehouse_id == warehouse)
    ).all()

    return render_template(
        'admin/delivery_admin/assign_delivery_package_view.html',
        delivery_order=delivery_order,
        grouped_items=grouped_items,
        production_round_details=production_round_details,
        warehouse_records=warehouse_records,
        warehouse=warehouse
    )




@admin_interface.route('/delivery_admin/process_assign_delivery_package', methods=['POST'])
def process_assign_delivery_package():
    """
    A debug route that subtracts the entire needed quantity from *every* selected 
    warehouse record for each ProductionRound. 
    If a record has less than needed, we report insufficient stock.
    """
    if 'user_id' not in session or session['role'] != 'delivery_admin':
        flash("You must log in as a Delivery Admin to access this page.")
        print("DEBUG: Not logged in as delivery_admin. Redirecting to admin_login.")
        return redirect(url_for('admin_interface.admin_login'))

    print("\n\n===== DEBUG: Entered process_assign_delivery_package route =====")
    try:
        # 1. Extract form data
        order_id_str = request.form.get("order_id")
        warehouse_str = request.form.get("warehouse")
        selected_records_json = request.form.get("selected_warehouse_records_json")
        record_ids = json.loads(selected_records_json)  # List of record UUIDs in string form
        packages_data = request.form.get("packages")

        print(f"DEBUG: order_id_str={order_id_str}")
        print(f"DEBUG: warehouse_str={warehouse_str}")
        print(f"DEBUG: record_ids={record_ids}")
        print(f"DEBUG: packages_data (raw)={packages_data}")

        if not order_id_str or not warehouse_str:
            flash("Missing order or warehouse data.", "danger")
            print("DEBUG: Missing order_id or warehouse. Redirecting to dashboard.")
            return redirect(url_for('admin_interface.delivery_admin_dashboard'))

        order_id = uuid.UUID(order_id_str)
        warehouse_id = int(warehouse_str)

        # Check at least one record & one package
        if not record_ids or not packages_data:
            flash("Please select at least one warehouse record and add at least one package.", "danger")
            print("DEBUG: No records selected or no package data. Redirecting to view.")
            return redirect(url_for('admin_interface.assign_delivery_package_view',
                                    order_id=order_id, warehouse=warehouse_id))

        # Decode JSON packages
        try:
            package_numbers = json.loads(packages_data)
        except json.JSONDecodeError as e:
            flash("Invalid package data format.", "danger")
            print(f"DEBUG: JSONDecodeError => {e}")
            return redirect(url_for('admin_interface.assign_delivery_package_view',
                                    order_id=order_id, warehouse=warehouse_id))

        print(f"DEBUG: package_numbers={package_numbers}")

        # 2. Fetch the DeliveryOrder and validate warehouse
        delivery_order = DeliveryOrder.query.get_or_404(order_id)
        if delivery_order.warehouse_id != warehouse_id:
            flash("Order does not belong to the selected warehouse.", "danger")
            print("DEBUG: Warehouse mismatch.")
            return redirect(url_for('admin_interface.delivery_admin_workspace', warehouse=warehouse_id))
        old_status = delivery_order.status
        print(f"DEBUG: Fetched DeliveryOrder with ID={delivery_order.id}, status={old_status}")

        # 3. Create DeliveryPackage records for each package number
        for pkg_num in package_numbers:
            new_package = DeliveryPackage(
                package_number=pkg_num,
                delivery_order_id=delivery_order.id,
                status="created"
            )
            db.session.add(new_package)
            print(f"DEBUG: Created DeliveryPackage {pkg_num} for order={delivery_order.id}")

        # 4. Build grouped_items to know how much each ProductionRound needs
        grouped_items = {}
        for item_data in delivery_order.delivery_item:
            pr_id = uuid.UUID(item_data["production_round_id"])
            qty = item_data.get("quantity", 1)
            grouped_items[pr_id] = grouped_items.get(pr_id, 0) + qty

        print(f"DEBUG: grouped_items => {grouped_items}")

        # 5. Convert record IDs from string to UUID
        try:
            selected_uuid_list = [uuid.UUID(rid) for rid in record_ids]
        except ValueError as e:
            flash(f"Invalid warehouse record ID encountered: {e}", "danger")
            print(f"DEBUG: Invalid ID => {e}")
            db.session.rollback()
            return redirect(url_for('admin_interface.assign_delivery_package_view',
                                    order_id=order_id, warehouse=warehouse_id))

        # 6. Fetch all chosen records with warehouse filter
        chosen_records = WarehouseRecord.query.filter(
            WarehouseRecord.id.in_(selected_uuid_list),
            WarehouseRecord.storage_location.has(WarehouseStorage.warehouse_id == warehouse_id)
        ).all()

        if len(chosen_records) != len(selected_uuid_list):
            flash("Some selected records are not from this warehouse or do not exist.", "danger")
            print("DEBUG: Record count mismatch after warehouse filter.")
            db.session.rollback()
            return redirect(url_for('admin_interface.assign_delivery_package_view',
                                    order_id=order_id, warehouse=warehouse_id))

        print(f"DEBUG: chosen_records => {[str(r.id) for r in chosen_records]}")

        # 7. For each ProductionRound in the order, subtract its 'needed' from EVERY record
        for pr_id, needed_qty in grouped_items.items():
            print(f"\nDEBUG: Processing PR={pr_id}, needed={needed_qty}")
            
            # Filter chosen_records for this pr_id
            pr_records = [rec for rec in chosen_records if rec.production_round_id == pr_id]

            if not pr_records:
                print(f"DEBUG: No selected warehouse records for PR={pr_id}. Skipping.")
                continue

            # Deduct the entire 'needed_qty' from each record in that PR
            for rec in pr_records:
                print(f"DEBUG: Checking record {rec.id} with qty={rec.quantity}")
                if rec.quantity < needed_qty:
                    db.session.rollback()
                    flash(f"Insufficient stock in record {rec.id} for Production Round {pr_id}. "
                          f"Needed: {needed_qty}, available: {rec.quantity}", "danger")
                    print(f"DEBUG: => record {rec.id} has only {rec.quantity}, can't subtract {needed_qty}. Rolling back.")
                    return redirect(url_for('admin_interface.assign_delivery_package_view',
                                            order_id=order_id, warehouse=warehouse_id))

                old_qty = rec.quantity
                rec.quantity = rec.quantity - needed_qty
                db.session.add(rec)
                print(f"DEBUG: => Deducted {needed_qty} from record {rec.id}, old={old_qty}, new={rec.quantity}")

        # 8. Update the DeliveryOrder status
        delivery_order.status = "delivering"
        db.session.add(delivery_order)
        db.session.commit()

        print(f"DEBUG: Successfully set Order {order_id} status from {old_status} to {delivery_order.status}")
        flash("All selected records for each PR have been fully deducted by the needed amount!", "success")

        # 9. Redirect to workspace
        print("DEBUG: Redirecting to workspace after success.")
        return redirect(url_for('admin_interface.delivery_admin_workspace', warehouse=warehouse_id))

    except Exception as e:
        db.session.rollback()
        flash(f"Error assigning packages: {e}", "danger")
        print(f"DEBUG: Unhandled Exception => {e}")
        return redirect(url_for('admin_interface.delivery_admin_dashboard'))




# Info-admin, manage the warehouse,

@admin_interface.route('/info_admin/dashboard')
def info_admin_dashboard():

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    return render_template('admin/info_admin/info_admin_dashboard.html')



# Regions Management
@admin_interface.route('/info_admin/regions')
def list_regions():

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    regions = Region.query.all()
    return render_template('admin/info_admin/regions.html', regions=regions)



@admin_interface.route('/info_admin/regions/new', methods=['GET', 'POST'])
def new_region():

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    if request.method == 'POST':
        name = request.form['name']
        tax_rate = request.form['tax_rate']
        delivery_tax_rate = request.form['delivery_tax_rate']
        new_region = Region(name=name, tax_rate=tax_rate, delivery_tax_rate=delivery_tax_rate)
        db.session.add(new_region)
        db.session.commit()
        flash("Region added successfully!", "success")
        return redirect(url_for('admin_interface.list_regions'))
    return render_template('admin/info_admin/region_form.html')



@admin_interface.route('/info_admin/regions/edit/<int:id>', methods=['GET', 'POST'])
def edit_region(id):

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    region = Region.query.get_or_404(id)
    if request.method == 'POST':
        region.name = request.form['name']
        region.tax_rate = request.form['tax_rate']
        region.delivery_tax_rate = request.form['delivery_tax_rate']
        db.session.commit()
        flash("Region updated successfully!", "success")
        return redirect(url_for('admin_interface.list_regions'))
    return render_template('admin/info_admin/region_form.html', region=region)



@admin_interface.route('/info_admin/regions/delete/<int:id>', methods=['POST'])
def delete_region(id):

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    region = Region.query.get_or_404(id)
    db.session.delete(region)
    db.session.commit()
    flash("Region deleted successfully!", "success")
    return redirect(url_for('admin_interface.list_regions'))



# Warehouse Management
@admin_interface.route('/info_admin/warehouses')
def list_warehouses():
    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    warehouses = Warehouse.query.all()
    return render_template('admin/info_admin/warehouses.html', warehouses=warehouses)



@admin_interface.route('/info_admin/warehouses/new', methods=['GET', 'POST'])
def new_warehouse():

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        new_warehouse = Warehouse(name=name, location=location)
        db.session.add(new_warehouse)
        db.session.commit()
        flash("Warehouse added successfully!", "success")
        return redirect(url_for('admin_interface.list_warehouses'))
    return render_template('admin/info_admin/warehouse_form.html')



@admin_interface.route('/info_admin/warehouses/edit/<int:id>', methods=['GET', 'POST'])
def edit_warehouse(id):

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    warehouse = Warehouse.query.get_or_404(id)
    if request.method == 'POST':
        warehouse.name = request.form['name']
        warehouse.location = request.form['location']
        db.session.commit()
        flash("Warehouse updated successfully!", "success")
        return redirect(url_for('admin_interface.list_warehouses'))
    return render_template('admin/info_admin/warehouse_form.html', warehouse=warehouse)



@admin_interface.route('/info_admin/warehouses/delete/<int:id>', methods=['POST'])
def delete_warehouse(id):

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    

    warehouse = Warehouse.query.get_or_404(id)
    db.session.delete(warehouse)
    db.session.commit()
    flash("Warehouse deleted successfully!", "success")
    return redirect(url_for('admin_interface.list_warehouses'))




# Warehouse-Region Mapping Management
@admin_interface.route('/info_admin/warehouse_mappings')
def list_warehouse_mappings():

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    mappings = WarehouseRegionMapping.query.all()
    return render_template('admin/info_admin/warehouse_mappings.html', mappings=mappings)

# region-warehoue: many to one, unique relationship
# one region can only have one warehouse
# one warehouse can have many region

@admin_interface.route('/info_admin/warehouse_mappings/new', methods=['GET', 'POST'])
def new_warehouse_mapping():

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    # Get unmapped regions (i.e., regions NOT already in a mapping)
    mapped_region_ids = [mapping.region_id for mapping in WarehouseRegionMapping.query.all()]
    available_regions = Region.query.filter(Region.id.notin_(mapped_region_ids)).order_by(Region.name).all()

    # Warehouses do NOT have constraints since they can be assigned to multiple regions
    available_warehouses = Warehouse.query.order_by(Warehouse.name).all()

    if request.method == 'POST':
        region_id = request.form.get('region_id')
        warehouse_id = request.form.get('warehouse_id')

        # Ensure valid selection
        if not region_id or not warehouse_id:
            flash("Please select both a region and a warehouse.", "danger")
            return redirect(url_for('admin_interface.new_warehouse_mapping'))

        # Ensure selected region is not already mapped
        if int(region_id) in mapped_region_ids:
            flash("This region is already mapped to a warehouse.", "danger")
            return redirect(url_for('admin_interface.new_warehouse_mapping'))

        # Create new mapping
        new_mapping = WarehouseRegionMapping(region_id=region_id, warehouse_id=warehouse_id)
        db.session.add(new_mapping)
        db.session.commit()
        flash("Mapping added successfully!", "success")
        return redirect(url_for('admin_interface.list_warehouse_mappings'))

    return render_template('admin/info_admin/warehouse_mapping_form.html', available_regions=available_regions, available_warehouses=available_warehouses)


@admin_interface.route('/info_admin/warehouse_mappings/edit/<int:region_id>', methods=['GET', 'POST'])
def edit_warehouse_mapping(region_id):

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    mapping = WarehouseRegionMapping.query.get_or_404(region_id)

    # Get all warehouses since they can have multiple region mappings
    available_warehouses = Warehouse.query.order_by(Warehouse.name).all()

    if request.method == 'POST':
        warehouse_id = request.form['warehouse_id']

        # Update mapping
        mapping.warehouse_id = warehouse_id
        db.session.commit()
        flash("Mapping updated successfully!", "success")
        return redirect(url_for('admin_interface.list_warehouse_mappings'))

    return render_template('admin/info_admin/warehouse_mapping_form.html', mapping=mapping, available_warehouses=available_warehouses)




@admin_interface.route('/info_admin/warehouse_mappings/delete/<int:region_id>', methods=['POST'])
def delete_warehouse_mapping(region_id):

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))
    
    mapping = WarehouseRegionMapping.query.get_or_404(region_id)
    db.session.delete(mapping)
    db.session.commit()
    flash("Mapping deleted successfully!", "success")
    return redirect(url_for('admin_interface.list_warehouse_mappings'))



# delivery cost grid management

@admin_interface.route('/info_admin/delivery_cost_grids', methods=['GET'])
def list_delivery_cost_grids():

    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must log in as an Info Admin to access this page.", "error")
        return redirect(url_for('admin_interface.admin_login'))

    cost_grids = DeliveryCostGrid.query.all()
    return render_template('admin/info_admin/delivery_cost_grids.html', cost_grids=cost_grids)





@admin_interface.route('/info_admin/delivery_cost_grids/new', methods=['GET', 'POST'])
def new_delivery_cost_grid():
    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must log in as an Info Admin to access this page.", "error")
        return redirect(url_for('admin_interface.admin_login'))

    warehouses = Warehouse.query.order_by(Warehouse.name).all()
    regions = Region.query.order_by(Region.name).all()

    if request.method == 'POST':
        warehouse_id = request.form.get('warehouse_id', type=int)
        region_id = request.form.get('region_id', type=int)
        postal_code_prefix = request.form.get('postal_code_prefix', '')
        base_cost = float(request.form.get('base_cost', 0.0))
        per_delivery_point = float(request.form.get('per_delivery_point', 0.0))

        if not warehouse_id or not region_id or base_cost < 0 or per_delivery_point < 0:
            flash("Invalid input. All fields are required and costs must be non-negative.", "error")
            return redirect(url_for('admin_interface.new_delivery_cost_grid'))

        new_grid = DeliveryCostGrid(
            warehouse_id=warehouse_id,
            region_id=region_id,
            postal_code_prefix=postal_code_prefix or None,
            base_cost=base_cost,
            per_delivery_point=per_delivery_point
        )
        db.session.add(new_grid)
        db.session.commit()
        flash("Delivery cost grid added successfully!", "success")
        return redirect(url_for('admin_interface.list_delivery_cost_grids'))

    return render_template(
        'admin/info_admin/delivery_cost_grid_form.html',
        warehouses=warehouses,
        regions=regions
    )


@admin_interface.route('/info_admin/delivery_cost_grids/edit/<int:id>', methods=['GET', 'POST'])
def edit_delivery_cost_grid(id):
    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must log in as an Info Admin to access this page.", "error")
        return redirect(url_for('admin_interface.admin_login'))

    grid = DeliveryCostGrid.query.get_or_404(id)
    warehouses = Warehouse.query.order_by(Warehouse.name).all()
    regions = Region.query.order_by(Region.name).all()

    if request.method == 'POST':
        grid.warehouse_id = request.form.get('warehouse_id', type=int)
        grid.region_id = request.form.get('region_id', type=int)
        grid.postal_code_prefix = request.form.get('postal_code_prefix', '') or None
        grid.base_cost = float(request.form.get('base_cost', 0.0))
        grid.per_delivery_point = float(request.form.get('per_delivery_point', 0.0))

        if not grid.warehouse_id or not grid.region_id or grid.base_cost < 0 or grid.per_delivery_point < 0:
            flash("Invalid input. All fields are required and costs must be non-negative.", "error")
            return redirect(url_for('admin_interface.edit_delivery_cost_grid', id=id))

        db.session.commit()
        flash("Delivery cost grid updated successfully!", "success")
        return redirect(url_for('admin_interface.list_delivery_cost_grids'))

    return render_template(
        'admin/info_admin/delivery_cost_grid_form.html',
        grid=grid,
        warehouses=warehouses,
        regions=regions
    )


@admin_interface.route('/info_admin/delivery_cost_grids/delete/<int:id>', methods=['POST'])
def delete_delivery_cost_grid(id):
    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must log in as an Info Admin to access this page.", "error")
        return redirect(url_for('admin_interface.admin_login'))

    grid = DeliveryCostGrid.query.get_or_404(id)
    db.session.delete(grid)
    db.session.commit()
    flash("Delivery cost grid deleted successfully!", "success")
    return redirect(url_for('admin_interface.list_delivery_cost_grids'))



# Modifying the Main Production Species of the OrderManagementAdmin
@admin_interface.route('/info_admin/search_order_admin', methods=['GET', 'POST'])
def search_order_admin():
    """Search for OrderManagementAdmin by admin_id, name, or email."""
    search_criteria = {
        "admin_id": request.form.get("admin_id", "").strip(),
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip(),
    }

    # Base query
    query = OrderManagementAdmin.query

    # Fix: Convert admin_id string to UUID for searching
    if search_criteria["admin_id"]:
        try:
            admin_uuid = uuid.UUID(search_criteria["admin_id"])  # Convert string to UUID
            query = query.filter(OrderManagementAdmin.id == admin_uuid)
        except ValueError:
            flash("Invalid UUID format for Admin ID.", "danger")

    if search_criteria["name"]:
        query = query.filter(OrderManagementAdmin.name.ilike(f"%{search_criteria['name']}%"))

    if search_criteria["email"]:
        query = query.filter(OrderManagementAdmin.email.ilike(f"%{search_criteria['email']}%"))

    order_management_admins = query.all()

    return render_template(
        "admin/info_admin/search_order_admin.html",
        order_management_admins=order_management_admins,
        search_criteria=search_criteria
    )


@admin_interface.route('/info_admin/update_order_admin', methods=['GET', 'POST'])
def update_order_admin():
    """Display form and update the main_production_species of a selected OrderManagementAdmin."""
    
    admin_id_str = request.args.get("admin_id") if request.method == "GET" else request.form.get("selected_admin")

    if not admin_id_str:
        flash("No admin selected for update.", "danger")
        return redirect(url_for('admin_interface.search_order_admin'))

    # Convert admin_id from string to UUID
    try:
        admin_uuid = uuid.UUID(admin_id_str)
    except ValueError:
        flash("Invalid Admin ID format.", "danger")
        return redirect(url_for('admin_interface.search_order_admin'))

    admin = OrderManagementAdmin.query.get_or_404(admin_uuid)

    if request.method == "POST":
        new_species = request.form.get('main_production_species', '').strip()

        if not new_species:
            flash("Main production species cannot be empty.", "danger")
            return redirect(url_for('admin_interface.update_order_admin', admin_id=admin_id_str))

        # ✅ Fix: Ensure the new value is saved
        admin.main_production_species = new_species
        db.session.commit()

        flash("Main production species updated successfully!", "success")
        return redirect(url_for('admin_interface.search_order_admin'))

    return render_template("admin/info_admin/update_order_admin.html", admin=admin)

# change the warehouse_id of a delivery order admin


@admin_interface.route('/info_admin/list_delivery_admins')
def list_delivery_admins():
    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    delivery_admins = DeliveryAdmin.query.all()
    return render_template('admin/info_admin/list_delivery_admins.html', delivery_admins=delivery_admins)



@admin_interface.route('/info_admin/change_delivery_admin_warehouse/<uuid:admin_id>', methods=['GET', 'POST'])
def change_delivery_admin_warehouse(admin_id):
    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    delivery_admin = DeliveryAdmin.query.get_or_404(admin_id)
    if request.method == 'POST':
        new_warehouse_id = request.form.get('warehouse_id')
        if not new_warehouse_id or not Warehouse.query.get(int(new_warehouse_id)):
            flash("Invalid warehouse selected.", "danger")
            return redirect(url_for('admin_interface.change_delivery_admin_warehouse', admin_id=admin_id))

        delivery_admin.warehouse_id = int(new_warehouse_id)
        db.session.commit()
        flash(f"Warehouse for {delivery_admin.name} updated successfully!", "success")
        return redirect(url_for('admin_interface.info_admin_dashboard'))

    warehouses = Warehouse.query.all()
    return render_template(
        'admin/info_admin/change_delivery_admin_warehouse.html',
        delivery_admin=delivery_admin,
        warehouses=warehouses
    )


# add admin's function is also here

@admin_interface.route('/info_admin/add_admin', methods=['GET', 'POST'])
def info_admin_add_admin():
    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        warehouse_id = request.form.get('warehouse_id')  # Optional, only for delivery_admin

        # Check for existing email
        existing_admin = db.session.query(Admin).filter_by(email=email).first()
        if existing_admin:
            flash(f"An account with the email {email} already exists.", "danger")
            return redirect(url_for('admin_interface.info_admin_add_admin'))

        hashed_password = generate_password_hash(password)
        new_admin = None

        if role == 'artwork_approval_admin':
            new_admin = ArtworkApprovalAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'order_management_admin':
            new_admin = OrderManagementAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'product_approval_admin':
            new_admin = ProductApprovalAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'warehouse_admin':
            new_admin = WarehouseAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'delivery_admin':
            if not warehouse_id:
                flash("Warehouse ID is required for Delivery Admin.", "danger")
                return redirect(url_for('admin_interface.info_admin_add_admin'))
            new_admin = DeliveryAdmin(name=name, email=email, password_hash=hashed_password, role=role, warehouse_id=int(warehouse_id))
        elif role == 'info_admin':
            new_admin = InfoAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        elif role == 'customer_service_admin':
            new_admin = CustomerServiceAdmin(name=name, email=email, password_hash=hashed_password, role=role)
        else:
            flash(f"Invalid role '{role}' specified.", "danger")
            return redirect(url_for('admin_interface.info_admin_add_admin'))

        db.session.add(new_admin)
        db.session.commit()
        flash(f"{role.replace('_', ' ').title()} {name} added successfully!", "success")
        return redirect(url_for('admin_interface.info_admin_add_admin'))

    warehouses = Warehouse.query.all()  # For DeliveryAdmin warehouse selection
    return render_template('admin/info_admin/add_admin.html', warehouses=warehouses)



@admin_interface.route('/info_admin/list_admins_for_password')
def list_admins_for_password():
    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    admins = Admin.query.all()
    return render_template('admin/info_admin/list_admins_for_password.html', admins=admins)



@admin_interface.route('/info_admin/change_admin_password/<uuid:admin_id>', methods=['GET', 'POST'])
def change_admin_password(admin_id):
    if 'user_id' not in session or session['role'] != 'info_admin':
        flash("You must be an Info Admin to access this page.")
        return redirect(url_for('admin_interface.admin_login'))

    admin = Admin.query.get_or_404(admin_id)
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or new_password != confirm_password:
            flash("Passwords do not match or are empty.", "danger")
            return redirect(url_for('admin_interface.change_admin_password', admin_id=admin_id))

        admin.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash(f"Password for {admin.name} updated successfully!", "success")
        return redirect(url_for('admin_interface.info_admin_dashboard'))

    return render_template(
        'admin/info_admin/change_admin_password.html',
        admin=admin
    )

# View notifications for the logged-in user, unread ones in first page, the read ones are displayed in a separate page
# these are for the admins, which might need to be adjusted...? or just the webpage?
# hmm... but the notification page definitely need to be duplicated for the users (customers and artists) and admins...?
# maybe not, since the notifications are the same for all users, just the roles are different?

@admin_interface.route('/view_notifications', methods=['GET', 'POST'])
def view_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('admin_interface.admin_login'))

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


@admin_interface.route('/mark_notification_read/<uuid6:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    # Ensure the user is logged in
    if 'user_id' not in session:
        flash("You need to be logged in to mark a notification as read.")
        return redirect(url_for('admin_interface.admin_login'))

    try:
        # Find the notification by ID
        notification = Notification.query.get(notification_id)

        # Ensure the notification belongs to the logged-in user
        user_id = uuid.UUID(session['user_id'])
        if notification.user_id != user_id:
            flash("You are not authorized to mark this notification as read.")
            return redirect(url_for('admin_interface.view_notifications'))

        # Mark the notification as read
        notification.is_read = True
        db.session.commit()
        flash("Notification has been marked as read.")

    except Exception as e:
        flash("An error occurred while trying to mark the notification as read.")

    return redirect(url_for('admin_interface.view_notifications'))




@admin_interface.route('/view_read_notifications', methods=['GET', 'POST'])
def view_read_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('admin_interface.admin_login'))

    user_id = uuid.UUID(session['user_id'])
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=True).order_by(Notification.timestamp.desc()).all()

    # Categorize notifications
    categorized_notifications = {}
    for notification in unread_notifications:
        if notification.type not in categorized_notifications:
            categorized_notifications[notification.type] = []
        categorized_notifications[notification.type].append(notification)

    return render_template('admin/account/read_notifications.html', categorized_notifications=categorized_notifications)



@admin_interface.route('/product_dialog/<uuid6:product_id>', methods=['GET', 'POST'])
def admin_active_product_dialog(product_id):
    """Dialog for the current active production round."""
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dialog.")
        return redirect(url_for('admin_interface.admin_login'))

    # Fetch the active production round
    production_round = ProductionRound.query.filter_by(product_id=product_id, is_active=True).first()
    if not production_round:
        flash("No active production round found for this product.")
        return redirect(url_for('admin_interface.admin_dashboard'))

    # Check if the admin is authorized
    if production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access to this dialog.")
        return redirect(url_for('admin_interface.admin_dashboard'))

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
