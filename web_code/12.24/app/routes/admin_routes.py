from flask import request, Blueprint,current_app, render_template, render_template_string, redirect, url_for, session, flash, current_app, send_file, jsonify
from datetime import datetime, timezone
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

    search_results = []

    # Fetch all pending artworks that are not picked by any admin
    artworks_info = Artwork.query.filter_by(approval_status='Pending', picked_by_admin_id=None).all()

    return render_template('admin/artwork_approval_admin/artwork_approval_admin_dashboard.html', artworks=artworks_info, search_results=search_results)



# admin picks the artwork to personal workspace to approve or disapprove.
# The picked artwork is not going to be displayed on the dashboard.

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
    return redirect(url_for('admin.personal_workspace'))


@admin_interface.route('/unpick_artwork/<uuid:artwork_id>', methods=['POST'])
def unpick_artwork(artwork_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to unpick artworks.")
        return redirect(url_for('admin.admin_login'))

    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork.picked_by_admin_id != uuid.UUID(session['user_id']):
        flash("You can only unpick artworks from your own workspace.")
        return redirect(url_for('admin.personal_workspace'))

    # Unassign the artwork
    artwork.picked_by_admin_id = None
    db.session.commit()

    flash(f"Artwork '{artwork.title}' has been removed from your workspace.")
    return redirect(url_for('admin.personal_workspace'))


@admin_interface.route('/personal_workspace', methods=['GET'])
def personal_workspace():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access your workspace.")
        return redirect(url_for('admin.admin_login'))

    admin_id = uuid.UUID(session['user_id'])
    artworks = Artwork.query.filter_by(picked_by_admin_id=admin_id, approval_status='Pending').all()

    return render_template('admin/artwork_approval_admin/personal_workspace.html', artworks=artworks)



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
    return redirect(url_for('admin.artwork_approval_admin_dashboard'))


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
            link = url_for('user.view_artwork_disapproval_reason', artwork_id=artwork.id, _external=True)  # Link to view disapproval reason
            Notification.send_notification(user_id=artist_id, message=message, link=link,type='artwork')

            flash(f"Artwork '{artwork.title}' has been disapproved.")
            return redirect(url_for('admin.artwork_approval_admin_dashboard'))
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

    # Convert session user ID to UUID
    try:
        admin_id = uuid.UUID(session['user_id'])
        unread_notifications_count = Notification.get_unread_notifications_count(admin_id)
    except ValueError:
        flash("Invalid session user ID.")
        return redirect(url_for('admin.admin_login'))

    # Get products assigned to the logged-in admin
    products = Product.query.filter_by(assigned_admin_id=admin_id).all()

    # Get all production rounds requested but not finalized yet
    production_rounds = ProductionRound.query.filter_by(admin_id=admin_id, status='requested').all()

    return render_template(
        'admin/order_management_admin/order_management_admin_dashboard.html',
        products=products,
        production_rounds=production_rounds,
        unread_notifications_count=unread_notifications_count
    )

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



@admin_interface.route('/manage_production_round/<uuid:round_id>', methods=['GET', 'POST'])
def manage_production_round(round_id):
    production_round = ProductionRound.query.get_or_404(round_id)

    if request.method == 'POST':
        try:
            # Parse and validate form inputs
            price = request.form.get('price')
            min_production_size = request.form.get('min_production_size')
            max_waiting_time = request.form.get('max_waiting_time')
            is_published = request.form.get('is_published') == 'on'

            if not price or not min_production_size or not max_waiting_time:
                raise ValueError("Missing required fields.")

            # Update production round details
            production_round.price = float(price)
            production_round.min_production_size = int(min_production_size)
            production_round.max_waiting_time = datetime.strptime(max_waiting_time, '%Y-%m-%d')
            production_round.is_published = is_published

            # Handle production stage goals
            stage_ids = request.form.getlist('stage_id')
            target_quantities = request.form.getlist('target_quantity')
            gifts = request.form.getlist('gift')

            for stage_id, target_quantity, gift in zip(stage_ids, target_quantities, gifts):
                if stage_id.startswith("new-"):  # New stage
                    new_stage = ProductionStageGoal(
                        production_round_id=production_round.id,
                        target_quantity=int(target_quantity),
                        gift=gift
                    )
                    db.session.add(new_stage)
                else:  # Update existing stage
                    stage = ProductionStageGoal.query.get(stage_id)
                    if stage:
                        stage.target_quantity = int(target_quantity)
                        stage.gift = gift

            db.session.commit()
            flash("Production round updated successfully.", "success")
            return redirect(url_for('admin.order_management_admin_dashboard'))

        except ValueError as ve:
            flash(f"Validation Error: {str(ve)}", "error")
        except Exception as e:
            flash(f"Unexpected Error: {str(e)}", "error")

    # Render form with existing data if GET
    return render_template(
        'admin/order_management_admin/manage_production_round.html',
        production_round=production_round,
        production_stages=sorted(production_round.stages, key=lambda s: s.target_quantity)
    )





@admin_interface.route('/publish_production_round/<uuid:round_id>', methods=['POST'])
def publish_production_round(round_id):
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to publish this production round.")
        return redirect(url_for('admin.admin_login'))

    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access or invalid production round.")
        return redirect(url_for('admin.order_management_admin_dashboard'))

    # Mark production round as published
    production_round.is_published = True
    db.session.commit()
    flash(f"Production round for product '{production_round.product.name}' has been published.")

    return redirect(url_for('admin.order_management_admin_dashboard'))



# Product Approval Admin Dashboard, download design file, approve product, disapprove product, assign product to order management admin

@admin_interface.route('/product_approval_admin_dashboard', methods=['GET', 'POST'])
def product_approval_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to access this dashboard.")
        return redirect(url_for('admin.admin_login'))

    if request.method == 'POST':
        # Approve Product
        if 'approve_id' in request.form:
            product_id_str = request.form['approve_id']
            try:
                product_id = UUID(product_id_str)
            except ValueError:
                flash("Invalid product ID.")
                return redirect(url_for('admin.product_approval_admin_dashboard'))

            product = Product.query.get(product_id)

            if product and product.production_status == 'Pending':
                # Product is still pending, but we now direct to assign an Order Management Admin
                flash(f"Product '{product.name}' is approved for assignment. Please assign an Order Management Admin.")
                return redirect(url_for('admin.assign_order_management_admin', product_id=product_id))

        # Handle disapproval request
        elif 'disapprove_id' in request.form:
            product_id_str = request.form['disapprove_id']
            try:
                product_id = UUID(product_id_str)
            except ValueError:
                flash("Invalid product ID.")
                return redirect(url_for('admin.product_approval_admin_dashboard'))

            return redirect(url_for('admin.disapprove_product', product_id=product_id))

    # Fetch all pending products and those that are not picked by other admins
    pending_products = Product.query.filter_by(production_status='Pending', picked_by_admin_id=None).all()

    return render_template('admin/product_approval_admin/product_approval_admin_dashboard.html', pending_products=pending_products)


# product are first picked to the workspace for approval/disapproval
# The picked product is not going to be displayed on the dashboard.


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

    # Only show picked products that are still pending approval
    picked_products = Product.query.filter_by(
        picked_by_admin_id=admin_id,
        production_status='Pending'  # Exclude products that are already approved or disapproved
    ).all()

    return render_template(
        'admin/product_approval_admin/product_approval_workspace.html',
        picked_products=picked_products
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

    # Fetch available Order Management Admins
    order_management_admins = OrderManagementAdmin.query.all()

    if request.method == 'POST':
        admin_id = request.form.get('admin_id')

        if admin_id:
            try:
                # Convert admin ID to UUID and fetch the admin
                admin_uuid = uuid.UUID(admin_id)
                admin = OrderManagementAdmin.query.get(admin_uuid)

                if admin:
                    # Assign the admin and update product status
                    product.assigned_admin_id = admin.id
                    product.production_status = 'Approved'
                    db.session.commit()

                    flash(f"Product '{product.name}' has been assigned to Order Management Admin '{admin.name}' and is now fully approved.")

                    # Notify the assigned admin
                    if admin:
                        message = f"A new product '{product.name}' has been assigned to you for management."
                        Notification.send_notification(user_id=admin.id, message=message, type='assign_product')

                    return redirect(url_for('admin.product_approval_workspace'))
                else:
                    flash("Selected Order Management Admin does not exist.")
            except ValueError:
                flash("Invalid Order Management Admin ID format.")

    # Render the assignment form on GET requests
    return render_template(
        'admin/product_approval_admin/assign_order_management_admin.html',
        product=product,
        order_management_admins=order_management_admins
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




@admin_interface.route('/product_dialog/<uuid:round_id>', methods=['GET', 'POST'])
def admin_product_dialog(round_id):
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dialog.")
        return redirect(url_for('admin.admin_login'))

    # Fetch the production round and check if the admin is authorized
    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access to this dialog.")
        return redirect(url_for('admin.admin_dashboard'))

    if request.method == 'POST':
        message = request.form.get('message')
        uploaded_files = request.files.getlist('files')  # Handle multiple file uploads

        # Create and save the new message
        new_message = Dialog(
            production_round_id=production_round.id,
            sender_id=uuid.UUID(session['user_id']),
            message=message if message else '[File Attached]',
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

                # Ensure the upload folder exists
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)

                file.save(file_path)

                # Create a DialogFile entry
                new_file = DialogFile(
                    dialog_id=new_message.id,
                    file_path=f'uploads/{filename}',
                    file_name=filename,
                    upload_date=datetime.now(timezone.utc)
                )
                db.session.add(new_file)

        db.session.commit()
        flash("Message and files sent.")

        # Send a notification to the artist
        recipient_id = production_round.artist_id
        dialog_link = url_for('admin.admin_product_dialog', round_id=production_round.id, _external=True)

        Notification.send_notification(
            user_id=recipient_id,
            message=f"You have a new message in the production round for '{production_round.product.name}'.",
            link=dialog_link,
            type='dialog'
        )

    # Fetch all messages in this dialog
    messages = Dialog.query.filter_by(production_round_id=production_round.id).order_by(Dialog.timestamp).all()

    return render_template('admin/order_management_admin/product_dialog.html', production_round=production_round, messages=messages)
