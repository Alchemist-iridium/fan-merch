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


# need an admin homepage...
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
        return redirect(url_for('admin.login'))

    search_results = []

    if request.method == 'POST':
        # If this block is executed, it means the form with either approve_id or disapprove_id was submitted
        if 'approve_id' in request.form:
            artwork_id = request.form['approve_id']
            if artwork_id and artwork_id.isdigit():
                artwork_id = int(artwork_id)
                artwork = Artwork.query.get(artwork_id)
                if artwork and artwork.approval_status == 'Pending':
                    artwork.approval_status = 'Approved'
                    db.session.commit()
                    flash(f"Artwork with ID {artwork_id} has been approved.")
                    return redirect(url_for('admin.artwork_approval_admin_dashboard'))

        elif 'disapprove_id' in request.form:
            artwork_id = request.form['disapprove_id']
            if artwork_id and artwork_id.isdigit():
                return redirect(url_for('admin.disapprove_artwork', artwork_id=artwork_id))

        elif 'keyword' in request.form:
            keyword = request.form['keyword'].lower()
            search_results = (
            Artwork.query
            .join(Artist)
            .options(joinedload(Artwork.artist))
            .filter(
                or_(
                    Artwork.title.ilike(f"%{keyword}%"),
                    Artwork.description.ilike(f"%{keyword}%"),
                    Artwork.hard_tags.ilike(f"%{keyword}%"),
                    Artwork.soft_tags.ilike(f"%{keyword}%"),
                    Artist.name.ilike(f"%{keyword}%")  # Search by artist name
                )
            )
            .all()
        )


    # Fetch all pending artworks
    artworks_info = Artwork.query.filter_by(approval_status='Pending').all()

    return render_template('admin/artwork_approval_admin/artwork_approval_admin_dashboard.html', artworks=artworks_info, search_results=search_results)



@admin_interface.route('/approve_artwork/<uuid:artwork_id>', methods=['POST'])
def approve_artwork(artwork_id):
    # Ensure the user is logged in as an Artwork Approval Admin
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to approve artworks.")
        return redirect(url_for('admin.login'))

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
        return redirect(url_for('admin.login'))

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
        return redirect(url_for('admin.login'))

    # Convert session user ID to UUID
    try:
        admin_id = uuid.UUID(session['user_id'])
        unread_notifications_count = Notification.get_unread_notifications_count(admin_id)
    except ValueError:
        flash("Invalid session user ID.")
        return redirect(url_for('admin.login'))

    # Get products assigned to the logged-in admin
    products = Product.query.filter_by(assigned_admin_id=admin_id).all()

    # Get all production rounds requested but not finalized yet
    production_rounds = ProductionRound.query.filter_by(admin_id=admin_id, status='requested').all()

    return render_template('admin/order_management_admin/order_management_admin_dashboard.html', products=products, production_rounds=production_rounds,unread_notifications_count=unread_notifications_count)


@admin_interface.route('/manage_production_round/<uuid:round_id>', methods=['GET', 'POST'])
def manage_production_round(round_id):
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to manage production rounds.")
        return redirect(url_for('admin.login'))

    production_round = ProductionRound.query.get(round_id)

    if not production_round or production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized action.")
        return redirect(url_for('admin.order_management_admin_dashboard'))

    if request.method == 'POST':
        try:
            # Update the production round details
            production_round.estimated_price = float(request.form['estimated_price'])
            
            # Handle optional actual_price
            actual_price_str = request.form.get('actual_price')
            if actual_price_str:
                production_round.actual_price = float(actual_price_str)
            else:
                production_round.actual_price = None  # or leave unchanged if necessary

            production_round.min_production_size = int(request.form['min_production_size'])
            production_round.max_waiting_time = int(request.form['max_waiting_time'])
            production_round.is_published = request.form.get('is_published') == 'on'
            
            # Update production stage
            production_round.production_stage = request.form['production_stage']

            db.session.commit()
            flash(f"Production round '{production_round.id}' has been updated.")
            return redirect(url_for('admin.order_management_admin_dashboard'))
        except ValueError:
            flash("Invalid input. Please ensure all fields are filled out correctly.")

    return render_template('admin/order_management_admin/manage_production_round.html', production_round=production_round)



@admin_interface.route('/publish_production_round/<uuid:round_id>', methods=['POST'])
def publish_production_round(round_id):
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to publish this production round.")
        return redirect(url_for('admin.login'))

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
        return redirect(url_for('admin.login'))

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

    # Fetch all pending products
    pending_products = Product.query.filter_by(production_status='Pending').all()

    return render_template('admin/product_approval_admin/product_approval_admin_dashboard.html', pending_products=pending_products)


@admin_interface.route('/approve_product/<uuid:product_id>', methods=['POST'])
def approve_product(product_id):
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to approve products.")
        return redirect(url_for('admin.login'))

    # Fetch the product from the database
    product = Product.query.get_or_404(product_id)

    # If the product is pending, redirect to assignment page without changing the status
    if product and product.production_status == 'Pending':
        flash(f"Product '{product.name}' approval initiated. Now, please assign an Order Management Admin.")
        
        # Send notification to the artist
        artist = product.artist  # Assuming there's a relationship between Product and User for the artist
        if artist:
            message = f"Your product '{product.name}' has been approved."
            Notification.send_notification(user_id=artist.id, message=message,type='product')

        # Redirect to assign the Order Management Admin page
        return redirect(url_for('admin.assign_order_management_admin', product_id=product.id))
    else:
        flash("Product not found or it is not pending approval.")

    return redirect(url_for('admin.product_approval_admin_dashboard'))



@admin_interface.route('/disapprove_product/<uuid:product_id>', methods=['GET', 'POST'])
def disapprove_product(product_id):
    # Check if the user is logged in and has the correct role
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to disapprove a product.")
        return redirect(url_for('admin.login'))

    # Fetch the product using its UUID
    product = Product.query.get_or_404(product_id)

    # Ensure the product is in the pending state for disapproval
    if product.production_status != 'Pending':
        flash("Invalid product or product is not pending.")
        return redirect(url_for('admin.product_approval_admin_dashboard'))

    if request.method == 'POST':
        # Get the reason from the form submission
        reason = request.form.get('disapprove_reason')
        if reason:
            # Update product status
            product.production_status = 'Disapproved'
            product.disapproval_reason = reason
            db.session.commit()

            # Send notification to the artist
            artist = product.artist  # Assuming there's a relationship between Product and User for the artist
            if artist:
                message = f"Your product '{product.name}' has been disapproved. Reason: {reason}"
                Notification.send_notification(user_id=artist.id, message=message,type='product')

            flash(f"Product '{product.name}' has been disapproved with reason: {reason}")
            return redirect(url_for('admin.product_approval_admin_dashboard'))
        else:
            flash("Disapproval reason is required.")

    # GET request - render the form for disapproval
    return render_template('admin/product_approval_admin/disapprove_product.html', product=product)



@admin_interface.route('/assign_order_management_admin/<uuid:product_id>', methods=['GET', 'POST'])
def assign_order_management_admin(product_id):
    # Check if the user is logged in and has the correct role
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to assign an Order Management Admin.")
        return redirect(url_for('admin.login'))

    # Get the product based on the UUID
    product = Product.query.get(product_id)
    if not product or product.production_status != 'Pending':
        flash("Invalid product or product is not ready for admin assignment.")
        return redirect(url_for('admin.product_approval_admin_dashboard'))

    # Retrieve all available Order Management Admins to assign
    order_management_admins = OrderManagementAdmin.query.all()

    # Handle the POST request when an admin is assigned
    if request.method == 'POST':
        admin_id = request.form.get('admin_id')

        if admin_id:
            try:
                # Convert the admin_id to a UUID object if provided
                admin_uuid = uuid.UUID(admin_id)

                # Get the Order Management Admin based on the provided UUID
                admin = OrderManagementAdmin.query.get(admin_uuid)
                
                # Check if admin exists
                if admin:
                    product.assigned_admin_id = admin.id
                    # Update the product status to "Approved" after the assignment
                    product.production_status = 'Approved'
                    db.session.commit()

                    flash(f"Product '{product.name}' has been assigned to Order Management Admin '{admin.name}' and is now fully approved.")
                    return redirect(url_for('admin.product_approval_admin_dashboard'))
                else:
                    flash("Selected Order Management Admin does not exist.")
            except ValueError:
                flash("Invalid Order Management Admin ID format.")

    # Send notification to the artist
            order_admin = product.assigned_admin_id  # Assuming there's a relationship between Product and User for the artist
            if order_admin:
                message = f"A new product '{product.name}' has been assigned to you."
                Notification.send_notification(user_id=order_admin, message=message, type='assign_product')

    # Render the template for assigning an admin to the product
    return render_template('admin/product_approval_admin/assign_order_management_admin.html', product=product, order_management_admins=order_management_admins)




@admin_interface.route('/download_file/<uuid:file_id>')
def download_file(file_id):
    if 'user_id' not in session:
        flash("You need to be logged in to download files.")
        return redirect(url_for('admin.login'))

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
        return redirect(url_for('admin.login'))

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
        return redirect(url_for('admin.login'))

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
        return redirect(url_for('admin.login'))

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
