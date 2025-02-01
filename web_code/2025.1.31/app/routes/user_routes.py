from flask import request, Blueprint,current_app, render_template, render_template_string, redirect, url_for, session, flash, current_app, send_file, jsonify
from datetime import datetime, timezone, timedelta
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func
from app.models import *
import json

# this line needs modification
from app.extensions import db
import uuid
from uuid import UUID
import uuid6
from sqlalchemy.dialects.postgresql import UUID
import pyotp
import re
import logging

import math



user_interface = Blueprint('user_interface', __name__)



# Web Routes
@user_interface.route('/')
def home():
    return render_template('user/account/user_home.html')



@user_interface.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role'].lower()  # Either "customer" or "artist"
        region = request.form.get('region', None)  # Region is optional for non-customers

        # Check if the email is already in use
        if User.query.filter_by(email=email).first():
            flash('Error: Email address already registered.', 'error')
            return redirect(url_for('user_interface.signup'))

        # Check if the artist name is unique if the role is 'artist'
        if role == 'artist' and Artist.query.filter_by(name=name).first():
            flash('Error: Artist name already taken. Please choose a different name.', 'error')
            return redirect(url_for('user_interface.signup'))

        try:
            # Hash the password before storing it in the database
            password_hash = generate_password_hash(password)

            # Create and add the user to the database using the correct subclass
            if role == 'customer':
                # Validate that a region was selected
                if not region or not region.isdigit():
                    flash('Error: Please select a valid region.', 'error')
                    return redirect(url_for('user_interface.signup'))
                
                new_user = Customer(
                    name=name, 
                    email=email, 
                    password_hash=password_hash, 
                    role=role, 
                    region=int(region)
                )
            elif role == 'artist':
                new_user = Artist(name=name, email=email, password_hash=password_hash, role=role)
            else:
                flash('Error: Invalid role selected. Please choose either "Customer" or "Artist".', 'error')
                return redirect(url_for('user_interface.signup'))

            with current_app.app_context():
                db.session.add(new_user)
                db.session.commit()

            flash('Signup successful! Welcome, {}.'.format(name), 'success')
            return redirect(url_for('user_interface.signup_success', name=name, role=role))

        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('user_interface.signup'))

    return render_template('user/account/signup.html')




@user_interface.route('/signup_success/<string:name>/<string:role>')  # Include 'role' as a URL parameter
def signup_success(name, role):
    return render_template('user/account/signup_success.html', name=name, role=role)

# customer and artist login page and the admins' login page is separated for safefy



@user_interface.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Query the user from the database
        user = User.query.filter_by(email=email).first()

        # Ensure only customers and artists can log in here
        if user and user.role in ['customer', 'artist'] and check_password_hash(user.password_hash, password):
            session['user_id'] = str(user.id)
            session['role'] = user.role
            flash("Login successful!")

            if user.role == 'artist':
                return redirect(url_for('user_interface.artist_dashboard'))
            elif user.role == 'customer':
                return redirect(url_for('user_interface.customer_home'))
        else:
            error = "Wrong email or password, or invalid user role"
            return render_template('user/account/login.html', error=error)
        
    return render_template('user/account/login.html')


@user_interface.route('/login_required')
def login_required():
    action = request.args.get('action', 'perform this action')
    return render_template('user/account/login_required.html', action=action)




@user_interface.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash("You have been logged out.")
    return redirect(url_for('user_interface.home'))


# after login, the customer will be redirected to the customer_home page
@user_interface.route('/customer_home', methods=['GET', 'POST'])
def customer_home():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to access the home page.")
        return redirect(url_for('user_interface.login'))

    try:
        # Convert the user_id from session to UUID before querying
        user_uuid = uuid.UUID(session['user_id'])
        customer = Customer.query.get(user_uuid)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user_interface.login'))

    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.login'))

    # Handle search functionality, similar to the home route
    search_results = []
    if request.method == 'POST':
        keyword = request.form['keyword'].lower()

        # Base query for searching artworks based on the keyword
        base_query = Artwork.query.options(joinedload(Artwork.artist)).filter(
            (Artwork.title.ilike(f"%{keyword}%")) |
            (Artwork.description.ilike(f"%{keyword}%")) |
            (Artwork.hard_tags.ilike(f"%{keyword}%")) |
            (Artwork.soft_tags.ilike(f"%{keyword}%"))
        )

        # Regular users, order management admins, or artists see only approved artworks
        search_results = base_query.filter(Artwork.approval_status == 'Approved').all()

    return render_template('user/customer/customer_home.html', customer=customer, search_results=search_results)






# public search section

@user_interface.route('/public_search', methods=['GET', 'POST'])
def public_search():
    search_results = []
    if request.method == 'POST':
        keyword = request.form['keyword'].lower()

        # Filter artworks and associated products where product status is 'display'
        search_results = (
            Artwork.query
            .join(Artist)
            .options(joinedload(Artwork.artist))
            .filter(
                or_(
                    Artwork.title.ilike(f"%{keyword}%"),
                    Artwork.description.ilike(f"%{keyword}%"),
                    Artwork.manufacturing_specs.ilike(f"%{keyword}%"),
                    Artwork.hard_tags.ilike(f"%{keyword}%"),
                    Artwork.soft_tags.ilike(f"%{keyword}%"),
                    Artist.name.ilike(f"%{keyword}%")  # Search by artist name
                ),
                Artwork.approval_status == 'Approved'  # Only include approved artworks
            )
            .all()
        )
        # Filter the products attached to each artwork that have a "display" status
        for artwork in search_results:
            artwork.display_products = [product for product in artwork.products if product.production_status == 'display']

    return render_template('user/public_search/public_search.html', search_results=search_results)






# routes that are related to the display the artist's public page
@user_interface.route('/artist/<uuid6:artist_id>')
def artist_public_page(artist_id):
    # Fetch the artist using the provided artist_id
    artist = Artist.query.get_or_404(artist_id)

    # Fetch all approved artworks for the artist
    artworks = Artwork.query.filter_by(artist_id=artist.id, approval_status='Approved').all()

    # Fetch only products that are approved and marked for display
    products = Product.query.filter(
        Product.artwork_id.in_([artwork.id for artwork in artworks]),
        Product.production_status == 'Approved',
        Product.display_status == True
    ).all()

    # Fetch the current logged-in customer, if available
    customer = None
    if 'user_id' in session and session['role'] == 'customer':
        try:
            customer = Customer.query.get(uuid.UUID(session['user_id']))
        except Exception as e:
            flash(f"Error fetching customer: {str(e)}", 'error')
            customer = None

    # Render the public artist page, passing all necessary data
    return render_template(
        'user/public_search/artist_public_page.html', 
        artist=artist, 
        artworks=artworks, 
        products=products, 
        customer=customer
    )




@user_interface.route('/artwork/<uuid6:artwork_id>')
def artwork_page(artwork_id):
    # Fetch the artwork using the provided artwork_id
    artwork = Artwork.query.get_or_404(artwork_id)

    # Fetch the current logged-in customer, if available
    customer = None
    if 'user_id' in session and session['role'] == 'customer':
        customer = Customer.query.get(uuid.UUID(session['user_id']))

    if artwork and artwork.approval_status == 'Approved':
        # Fetch only approved products that are marked for display
        approved_products = Product.query.filter_by(
            artwork_id=artwork.id, 
            production_status='Approved', 
            display_status= True
        ).all()

    # Render the artwork page, passing all necessary data
    return render_template(
        'user/public_search/artwork_page.html',
        work=artwork,
        approved_products=approved_products,
        customer=customer
    )


@user_interface.route('/product_public/<uuid6:product_id>')
def product_public(product_id):
    """Display the public product page with details about production round and stage goals."""
    product = Product.query.get(product_id)
    if product and product.production_status == 'Approved' and product.display_status:
        # Fetch the active production round (only one can be active at a time)
        production_round = (
            ProductionRound.query.filter_by(product_id=product_id, is_active=True, is_published=True)
            .first()
        )

        # Extract stage goals from production_goals JSON if there is a production round
        stage_goals = []
        if production_round and production_round.production_goals:
            try:
                stage_goals = json.loads(production_round.production_goals)
            except ValueError:
                flash("Error loading stage goals. Please contact support.")

        return render_template(
            'user/public_search/product_public.html',
            product=product,
            production_round=production_round,
            stage_goals=stage_goals,
        )
    
    flash("This product is not available for public viewing.")
    return redirect(url_for('user_interface.home'))



# Customer Dashboard: Region adjust, View Item & Order, Favorite Artworks, Followed Artists, Wallet Balance

@user_interface.route('/customer_dashboard')
def customer_dashboard():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to access the dashboard.")
        return redirect(url_for('user_interface.customer_home'))

    try:
        # Convert the user_id from session to UUID before querying
        user_uuid = uuid.UUID(session['user_id'])
        customer = Customer.query.get(user_uuid)
    except ValueError:
        flash("Invalid user ID format.")
        return redirect(url_for('user_interface.login'))

    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.login'))

    return render_template(
        'user/customer/customer_dashboard.html',
        customer=customer,
        wallet_balance=customer.wallet_balance,
        region=customer.region
    )


@user_interface.route('/customer_dashboard/favorite_artworks')
def favorite_artworks():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to access favorite artworks.")
        return redirect(url_for('user_interface.login'))

    user_uuid = uuid.UUID(session['user_id'])
    customer = Customer.query.get(user_uuid)
    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.login'))

    return render_template(
        'user/customer/favorite_artworks.html',
        favorite_artworks=customer.favorite_artworks  # Assuming relationship exists
    )




@user_interface.route('/customer_dashboard/followed_artists')
def followed_artists():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to access followed artists.")
        return redirect(url_for('user_interface.login'))

    user_uuid = uuid.UUID(session['user_id'])
    customer = Customer.query.get(user_uuid)
    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.login'))

    return render_template(
        'user/customer/followed_artists.html',
        followed_artists=customer.followed_artists  # Assuming relationship exists
    )


@user_interface.route('/update_region', methods=['POST'])
def update_region():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to update your region.")
        return redirect(url_for('user_interface.login'))

    user_uuid = uuid.UUID(session['user_id'])
    customer = Customer.query.get(user_uuid)
    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.login'))

    region = request.form.get('region')
    if not region or not region.isdigit():
        flash("Invalid region selected.")
        return redirect(url_for('user_interface.customer_dashboard'))

    customer.region = int(region)
    db.session.commit()
    flash("Region updated successfully.")
    return redirect(url_for('user_interface.customer_dashboard'))







# add fund for wallet


@user_interface.route('/add_funds', methods=['GET', 'POST'])
def add_funds():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to add funds.")
        return redirect(url_for('user_interface.login'))

    if request.method == 'POST':
        try:
            amount = float(request.form['amount'])
            if amount <= 0:
                raise ValueError("Amount must be positive.")

            customer = Customer.query.get(uuid.UUID(session['user_id']))
            customer.wallet_balance += amount

            db.session.add(customer)
            db.session.commit()

            flash(f"${amount} has been added to your wallet.")
            return redirect(url_for('user_interface.customer_dashboard'))
        except ValueError:
            flash("Invalid amount. Please enter a positive number.")

    return render_template('user/add_funds.html')




# item management, dealt as a category


@user_interface.route('/item_management/<string:category>', methods=['GET'])
def item_management(category):
    """
    Manage customer items categorized into different sections (e.g., in production, waiting for delivery).
    """
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to log in as a Customer to access item management.")
        return redirect(url_for('user_interface.login'))

    try:
        user_uuid = uuid.UUID(session['user_id'])
        customer = Customer.query.get(user_uuid)

        if not customer:
            flash("Customer not found.")
            return redirect(url_for('user_interface.login'))

        # Base query for items
        items_query = ItemOrderItem.query.join(ItemOrder).filter(ItemOrder.customer_id == customer.id)

        # Ensure relationships are loaded
        items_query = items_query.options(
            joinedload(ItemOrderItem.production_round),
            joinedload(ItemOrderItem.item_order)
        )

        # Category-specific filters
        category_filters = {
            "in_production": items_query.join(ProductionRound).filter(
                ProductionRound.is_active.is_(True),
                ProductionRound.stage.in_(["sample", "production", "examination"])
            ),
            "waiting_for_delivery": items_query.join(ProductionRound).filter(
                ProductionRound.is_active.is_(False),
                ProductionRound.stage == "stocking",
                ItemOrderItem.item_status == "item"
            ),
            "delivered": items_query.filter(ItemOrderItem.item_status == "delivered"),
            "in_process": items_query.filter(ItemOrderItem.item_status == "in_process"),
            "refunded": items_query.filter(ItemOrderItem.item_status == "refunded"),
            "transferred": items_query.filter(ItemOrderItem.item_status == "transferred"),
            "all": items_query
        }

        # Fetch items for the selected category
        items = category_filters.get(category)
        if items is None:
            flash("Invalid category selected.")
            return redirect(url_for('user_interface.customer_dashboard'))

        # Fetch all items for the category
        items = items.all()

        # Group items by production_round_id in the template
        return render_template(
            'user/customer/item_management_grouped.html',
            category=category,
            items=items
        )

    except Exception as e:
        logging.exception("Error in item_management route: %s", e)
        flash(f"An error occurred while managing items: {e}", "error")
        return redirect(url_for('user_interface.customer_dashboard'))



# view lists and details of different orders:
# item order (with item order item information)
# transfer item order
# refund item order
# delivery order (with delivery order item and delivery package)



# order section, separate routes to view order and order details


# item order

@user_interface.route('/view_item_orders', methods=['GET'])
def view_item_orders():
    try:
        if 'user_id' not in session or session.get('role') != 'customer':
            logging.warning("Unauthorized access attempt to /view_item_orders.")
            flash("You need to be logged in as a Customer to view your orders.")
            return redirect(url_for('user_interface.login'))

        customer_id = uuid.UUID(session['user_id'])
        logging.debug("Fetching orders for Customer ID: %s", customer_id)

        item_orders = ItemOrder.query.filter_by(customer_id=customer_id).order_by(ItemOrder.created_at.desc()).all()

        if not item_orders:
            logging.info("No orders found for Customer ID: %s", customer_id)
        else:
            logging.info("Retrieved %d orders for Customer ID: %s", len(item_orders), customer_id)

        return render_template('user/customer/view_item_orders.html', item_orders=item_orders)

    except Exception as e:
        logging.exception("Unexpected error in /view_item_orders route: %s", e)
        flash(f"An error occurred while retrieving your orders: {e}", "error")
        return redirect(url_for('user_interface.customer_dashboard'))




@user_interface.route('/view_item_order_detail/<uuid6:order_id>', methods=['GET'])
def view_item_order_detail(order_id):
    if 'user_id' not in session or session.get('role') != 'customer':
        flash("You need to be logged in as a Customer to view your order details.")
        return redirect(url_for('user_interface.login'))

    customer_id = uuid.UUID(session['user_id'])
    item_order = ItemOrder.query.filter_by(id=order_id, customer_id=customer_id).first()

    if not item_order:
        flash("Order not found or you do not have permission to view it.")
        return redirect(url_for('user_interface.view_item_orders'))

    item_order_items = ItemOrderItem.query.filter_by(item_order_id=item_order.id).all()

    return render_template(
        'user/customer/view_item_order_detail.html',
        item_order=item_order,
        item_order_items=item_order_items
    )


# refund item order



@user_interface.route('/view_refund_orders', methods=['GET'])
def view_refund_orders():
    """List all RefundItemOrders for the logged-in customer."""
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to log in as a customer to access this page.", "error")
        return redirect(url_for('user_interface.login'))

    customer_id = uuid.UUID(session['user_id'])
    orders = RefundItemOrder.query.filter_by(customer_id=customer_id).all()
    return render_template('user/orders/view_refund_orders.html', orders=orders)




# transfer item order (need update)

@user_interface.route('/view_transfer_orders', methods=['GET'])
def view_transfer_orders():
    """List all TransferItemOrders for the logged-in customer."""
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to log in as a customer to access this page.", "error")
        return redirect(url_for('user_interface.login'))

    customer_id = uuid.UUID(session['user_id'])
    orders = TransferItemOrder.query.filter_by(from_customer_id=customer_id).all()
    return render_template('user/orders/view_transfer_orders.html', orders=orders)




# delivery order (need update)


@user_interface.route('/view_delivery_orders', methods=['GET'])
def view_delivery_orders():
    """
    Display all delivery orders categorized by their status (created, in_process, delivering, received).
    """
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to log in as a Customer to view your delivery orders.")
        return redirect(url_for('user_interface.login'))

    try:
        user_uuid = uuid.UUID(session['user_id'])
        customer = Customer.query.get(user_uuid)

        if not customer:
            flash("Customer not found.")
            return redirect(url_for('user_interface.login'))

        # Fetch all delivery orders for the customer
        delivery_orders = DeliveryOrder.query.filter_by(customer_id=customer.id).all()

        # Categorize orders by status
        categorized_orders = {
            "created": [order for order in delivery_orders if order.status == "created"],
            "in_process": [order for order in delivery_orders if order.status == "in_process"],
            "delivering": [order for order in delivery_orders if order.status == "delivering"],
            "received": [order for order in delivery_orders if order.status == "received"]
        }

        return render_template(
            'user/customer/view_delivery_orders.html',
            categorized_orders=categorized_orders
        )

    except Exception as e:
        logging.exception("Error in view_delivery_orders route: %s", e)
        flash(f"An error occurred while fetching delivery orders: {e}", "danger")
        return redirect(url_for('user_interface.customer_dashboard'))


@user_interface.route('/delivery_order_detail/<uuid:order_id>', methods=['GET'])
def view_delivery_order_detail(order_id):
    """
    View details of a delivery order including ordered items and delivery packages.
    This page is accessible to the customer who placed the order.
    """
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You must be logged in as a customer to view this order.", "danger")
        return redirect(url_for('user_interface.login'))

    # Fetch the order
    delivery_order = DeliveryOrder.query.get_or_404(order_id)

    # Ensure the logged-in user is the owner of this order
    if session['user_id'] != str(delivery_order.customer_id):
        flash("You do not have permission to view this order.", "danger")
        return redirect(url_for('user_interface.customer_dashboard'))

    # Group ordered items by Production Round with item IDs
    grouped_items = {}
    production_round_ids = set()

    for item in delivery_order.delivery_item:
        pr_id = uuid.UUID(item["production_round_id"])
        item_id = item.get("item_id", "Unknown")  # Ensure item_id is present

        if pr_id not in grouped_items:
            grouped_items[pr_id] = {"quantity": 0, "items": []}

        grouped_items[pr_id]["quantity"] += 1
        grouped_items[pr_id]["items"].append(item_id)
        production_round_ids.add(pr_id)

    # Fetch Production Round details
    production_rounds = ProductionRound.query.filter(ProductionRound.id.in_(production_round_ids)).all()
    production_round_details = {
        pr.id: {
            "product_name": pr.product.name,
            "artwork_image": pr.product.artwork.image_path
        }
        for pr in production_rounds
    }

    # Fetch delivery packages (if any)
    packages = DeliveryPackage.query.filter_by(delivery_order_id=order_id).all()

    return render_template(
        'user/customer/view_delivery_order_detail.html',
        delivery_order=delivery_order,
        grouped_items=grouped_items,
        production_round_details=production_round_details,
        packages=packages
    )



@user_interface.route('/delivery_order/confirm_package/<string:package_number>', methods=['POST'])
def confirm_delivery_package(package_number):
    """
    Allows customers to confirm they have received a specific delivery package.
    If all packages for an order are confirmed, update the order status to 'received'
    and mark all associated ItemOrderItems as 'delivered'.
    """
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You must be logged in as a customer to confirm package receipt.", "danger")
        return redirect(url_for('user_interface.login'))

    # Fetch the package
    package = DeliveryPackage.query.filter_by(package_number=package_number).first_or_404()

    # Ensure the package belongs to the logged-in customer
    if session['user_id'] != str(package.delivery_order.customer_id):
        flash("You do not have permission to confirm this package.", "danger")
        return redirect(url_for('user_interface.view_delivery_order_detail', order_id=package.delivery_order_id))

    # Ensure the package has not already been confirmed
    if package.status == "delivered":
        flash("This package has already been received.", "info")
        return redirect(url_for('user_interface.view_delivery_order_detail', order_id=package.delivery_order_id))

    try:
        # Mark package as delivered
        package.status = "delivered"
        db.session.add(package)
        db.session.commit()

        # Check if all packages for the order are delivered
        all_packages_received = all(pkg.status == "delivered" for pkg in package.delivery_order.packages)

        if all_packages_received:
            # Update delivery order status
            package.delivery_order.status = "received"
            db.session.add(package.delivery_order)

            # Extract item IDs from the delivery order
            item_ids = [uuid.UUID(item["item_id"]) for item in package.delivery_order.delivery_item]

            # Update all associated ItemOrderItem statuses to "delivered"
            item_order_items = ItemOrderItem.query.filter(
                ItemOrderItem.id.in_(item_ids)
            ).all()

            for item in item_order_items:
                item.item_status = "delivered"
                db.session.add(item)

            db.session.commit()
            flash("All packages have been received! Order and items marked as 'delivered'.", "success")
        else:
            flash("Package received! Waiting for other packages to be confirmed.", "info")

    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred while confirming the package: {e}", "danger")

    return redirect(url_for('user_interface.view_delivery_order_detail', order_id=package.delivery_order_id))



# Add artwork to favorites

@user_interface.route('/add_to_favorites/<uuid6:artwork_id>', methods=['POST'])
def add_to_favorites(artwork_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to add to favorites.")
        return redirect(url_for('user_interface.login'))

    customer = Customer.query.get(uuid.UUID(session['user_id']))
    artwork = Artwork.query.get(artwork_id)

    if artwork not in customer.favorite_artworks:
        customer.favorite_artworks.append(artwork)
        db.session.commit()
        flash(f"'{artwork.title}' has been added to your favorites.")

     # Redirect back to the page the user was previously on
    return redirect(request.referrer)


@user_interface.route('/remove_from_favorites/<uuid6:artwork_id>', methods=['POST'])
def remove_from_favorites(artwork_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to remove from favorites.")
        return redirect(url_for('user_interface.login'))

    customer = Customer.query.get(uuid.UUID(session['user_id']))
    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork in customer.favorite_artworks:
        customer.favorite_artworks.remove(artwork)
        db.session.commit()
        flash(f"'{artwork.title}' has been removed from your favorites.", 'success')

    return redirect(request.referrer or url_for('user_interface.customer_home'))




# follow and unfollow artists

@user_interface.route('/follow_artist/<uuid6:artist_id>', methods=['POST'])
def follow_artist(artist_id):
    if 'user_id' not in session:
        flash("You need to login or sign up to follow an artist.", 'error')
        return redirect(url_for('user_interface.login'))

    if session['role'] != 'customer':
        flash("Only customers can follow an artist.", 'error')
        return redirect(url_for('user_interface.home'))

    customer = Customer.query.get(uuid.UUID(session['user_id']))
    artist = Artist.query.get(artist_id)

    if artist not in customer.followed_artists:
        customer.followed_artists.append(artist)
        db.session.commit()
        flash(f"You are now following '{artist.name}'.", 'success')

    return redirect(request.referrer or url_for('user_interface.customer_home'))



@user_interface.route('/unfollow_artist/<uuid6:artist_id>', methods=['POST'])
def unfollow_artist(artist_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to unfollow an artist.", 'error')
        return redirect(url_for('user_interface.login'))

    customer = Customer.query.get(uuid.UUID(session['user_id']))
    artist = Artist.query.get_or_404(artist_id)

    if artist in customer.followed_artists:
        customer.followed_artists.remove(artist)
        db.session.commit()
        flash(f"You have unfollowed '{artist.name}'.", 'success')

    return redirect(request.referrer or url_for('user_interface.customer_home'))






# transaction section for customers, cart, checkout, view orders, view order details, add fund and sandbox payment


@user_interface.route('/add_to_cart/<uuid6:round_id>', methods=['POST'])
def add_to_cart(round_id):
    try:
        # 1) Verify user is logged in as a Customer
        if 'user_id' not in session or session['role'] != 'customer':
            flash("You need to log in as a Customer to add items to your cart.")
            return redirect(url_for('user_interface.login_required'))

        # 2) Fetch the customer
        customer_id = uuid.UUID(session['user_id'])
        customer = Customer.query.get(customer_id)
        if not customer:
            flash("Customer not found.")
            return redirect(url_for('user_interface.home'))

        # 3) Fetch the ProductionRound
        production_round = ProductionRound.query.get(round_id)
        if not production_round:
            flash("Invalid production round.")
            return redirect(url_for('user_interface.home'))
        if not production_round.is_published:
            flash("This production round is not available for purchase.")
            return redirect(url_for('user_interface.home'))

        # 4) Get the requested quantity
        quantity = int(request.form['quantity'])
        if quantity < 1:
            raise ValueError("Quantity must be at least 1.")

        # 5) Ensure the customer has a cart
        if not customer.cart:
            new_cart = Cart(customer_id=customer.id)
            db.session.add(new_cart)
            db.session.flush()  # so that new_cart.id is generated
            customer.cart = new_cart

        # 6) Add item(s) to the cart
        customer.cart.add_item_to_cart(production_round, quantity)

        # 7) Commit changes to DB
        db.session.commit()

        flash(f"Added {quantity} item(s) from '{production_round.product.name}' to your cart.", "success")
        return redirect(url_for('user_interface.view_cart'))

    except ValueError as e:
        db.session.rollback()
        flash(str(e), "error")
        return redirect(url_for('user_interface.home'))
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('user_interface.home'))





@user_interface.route('/view_cart', methods=['GET'])
def view_cart():
    try:
        # 1) Check if user is a Customer
        if 'user_id' not in session or session['role'] != 'customer':
            flash("You need to be logged in as a Customer to view your cart.")
            return redirect(url_for('user_interface.login'))

        # 2) Fetch Customer
        customer_id = uuid.UUID(session['user_id'])
        customer = Customer.query.get(customer_id)
        if not customer:
            flash("Customer not found.")
            return redirect(url_for('user_interface.home'))

        # 3) Check if the cart is present or empty
        if not customer.cart or customer.cart.is_empty():
            flash("Your cart is empty.")
            return render_template('user/customer/empty_cart.html')

        # 4) Retrieve all cart items & total
        cart_items = customer.cart.cart_items
        total_amount = customer.cart.calculate_total()

        return render_template(
            'user/customer/view_cart.html',
            cart_items=cart_items,
            total_amount=total_amount
        )

    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred while viewing the cart: {e}", "error")
        return redirect(url_for('user_interface.home'))





@user_interface.route('/update_cart_quantity', methods=['POST'])
def update_cart_quantity():
    try:
        # 1) Authorization check
        if 'user_id' not in session or session['role'] != 'customer':
            return jsonify({"error": "Unauthorized"}), 403

        # 2) Fetch Customer
        customer_id = uuid.UUID(session['user_id'])
        customer = Customer.query.get_or_404(customer_id)

        # 3) Parse JSON input
        data = request.get_json()
        production_round_id = uuid.UUID(data.get('production_round_id'))
        new_quantity = int(data.get('quantity'))

        # 4) If no cart, there's nothing to update
        if not customer.cart:
            return jsonify({"error": "No active cart"}), 400

        # 5) Perform update or removal
        if new_quantity <= 0:
            customer.cart.remove_item_from_cart(production_round_id)
        else:
            customer.cart.update_item_quantity(production_round_id, new_quantity)

        db.session.commit()
        return jsonify({"message": "Cart updated successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500



@user_interface.route('/select_checkout_items', methods=['POST'])
def select_checkout_items():
    try:
        logging.debug("Entered /select_checkout_items route")

        # 1) Check if user is logged in as a Customer
        if 'user_id' not in session or session['role'] != 'customer':
            logging.debug("User is not logged in or not a customer. Session data: %s", session)
            flash("You need to be logged in as a Customer to proceed with checkout.")
            return redirect(url_for('user_interface.view_cart'))

        # 2) Fetch the customer
        customer_id = uuid.UUID(session['user_id'])
        customer = Customer.query.get(customer_id)
        if not customer:
            logging.debug("Customer not found for ID: %s", customer_id)
            flash("Customer not found. Please log in again.")
            return redirect(url_for('user_interface.view_cart'))

        # 3) Get the list of selected cart items (by production_round_id)
        selected_items = request.form.getlist('selected_items')
        logging.debug("Selected items from form: %s", selected_items)

        if not selected_items:
            logging.debug("No items selected for checkout.")
            flash("No items selected for checkout.")
            return redirect(url_for('user_interface.view_cart'))

        # 4) Validate and prepare session['checkout_items']
        checkout_items = {}
        for item_id_str in selected_items:
            try:
                quantity = int(request.form.get(f'quantity_{item_id_str}', '1'))
                production_round_id = uuid.UUID(item_id_str)

                # Verify the CartItem exists in the customer's cart
                cart_item = CartItem.query.filter_by(
                    cart_id=customer.cart.id,
                    production_round_id=production_round_id
                ).first()

                if not cart_item:
                    logging.warning("CartItem not found for production_round_id: %s", item_id_str)
                    flash(f"Invalid item selected: {item_id_str}", "error")
                    continue

                checkout_items[item_id_str] = quantity
            except Exception as e:
                logging.exception("Error processing selected item: %s", e)

        if not checkout_items:
            logging.debug("No valid items selected for checkout.")
            flash("No valid items selected for checkout.")
            return redirect(url_for('user_interface.view_cart'))

        session['checkout_items'] = checkout_items
        logging.debug("Session updated with checkout items: %s", session['checkout_items'])

        # Log all CartItems for the customer
        customer.cart.log_cart_items()

        return redirect(url_for('user_interface.checkout'))

    except Exception as e:
        logging.exception("Unexpected error in /select_checkout_items: %s", e)
        flash(f"An error occurred during item selection: {e}", "error")
        return redirect(url_for('user_interface.view_cart'))



@user_interface.route('/checkout', methods=['GET', 'POST'])
def checkout():
    try:
        if 'user_id' not in session or session['role'] != 'customer':
            flash("You need to be logged in as a Customer to checkout.", "error")
            return redirect(url_for('user_interface.login'))

        customer = Customer.query.get(uuid.UUID(session['user_id']))
        if not customer:
            flash("Invalid customer session. Please log in again.", "error")
            return redirect(url_for('user_interface.login'))

        # Retrieve selected items from the session
        checkout_items = session.get('checkout_items', {})
        if not checkout_items:
            flash("No items selected for checkout.", "error")
            return redirect(url_for('user_interface.view_cart'))

        # Display selected items
        cart_item_details = []
        subtotal = 0
        for prod_round_id_str, qty in checkout_items.items():
            cart_item = CartItem.query.filter_by(
                cart_id=customer.cart.id,
                production_round_id=uuid.UUID(prod_round_id_str)
            ).first()
            if cart_item:
                subtotal += cart_item.unit_price * qty
                cart_item_details.append({
                    'name': cart_item.product_name,
                    'quantity': qty,
                    'unit_price': cart_item.unit_price,
                    'total_price': cart_item.unit_price * qty,
                    'product_image_path': cart_item.product_image_path,
                })

        # Calculate tax and total
        tax_rate = 0.07
        transaction_fee = 2.00
        tax = subtotal * tax_rate
        total_amount = subtotal + tax + transaction_fee

        if request.method == 'POST':
            payment_method = request.form.get('payment_method')
            if payment_method == "wallet":
                return redirect(url_for('user_interface.item_order_wallet_payment'))
            else:
                flash("Selected payment method is not yet supported.", "error")
                return redirect(url_for('user_interface.checkout'))

        return render_template(
            'user/customer/checkout.html',
            cart_items=cart_item_details,
            subtotal=subtotal,
            tax=tax,
            transaction_fee=transaction_fee,
            total_amount=total_amount
        )

    except Exception as e:
        logging.exception("Unexpected error in /checkout route: %s", e)
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('user_interface.view_cart'))




# now only designed for item order... should I have a uniform payment method???
# right now is not considering that as the order are not of the same type...?
# but have the chance to separate the order creation process out?

# right now the creation of item order is put on the checkout



@user_interface.route('/item_order_wallet_payment', methods=['GET', 'POST'])
def item_order_wallet_payment():
    try:
        logging.debug("Entered /item_order_wallet_payment route")

        if 'user_id' not in session or session['role'] != 'customer':
            logging.warning("User not logged in or not a customer.")
            flash("You need to log in as a Customer to proceed with payment.")
            return redirect(url_for('user_interface.login'))

        customer = Customer.query.get(uuid.UUID(session['user_id']))
        if not customer:
            logging.error("Invalid customer session. User ID: %s", session.get('user_id'))
            flash("Invalid customer session. Please log in again.")
            return redirect(url_for('user_interface.login'))

        # Retrieve checkout items from session
        checkout_items = session.get('checkout_items', {})
        if not checkout_items:
            logging.warning("No items selected for checkout.")
            flash("No items selected for payment.")
            return redirect(url_for('user_interface.checkout'))

        # Calculate total amount
        subtotal = sum(
            CartItem.query.filter_by(
                cart_id=customer.cart.id,
                production_round_id=uuid.UUID(prod_round_id_str)
            ).first().unit_price * qty
            for prod_round_id_str, qty in checkout_items.items()
        )
        tax_rate = 0.07
        transaction_fee = 2.00
        tax = subtotal * tax_rate
        total_amount = round(subtotal + tax + transaction_fee, 2)

        if request.method == 'POST':
            # Create and commit the ItemOrder
            item_order = ItemOrder(customer_id=customer.id, payment_status="unpaid", total_amount=total_amount)
            db.session.add(item_order)
            db.session.commit()  # Commit here to ensure the order is in the database

            # Add ItemOrderItem entries
            for prod_round_id_str, qty in checkout_items.items():
                production_round_id = uuid.UUID(prod_round_id_str)
                cart_item = CartItem.query.filter_by(cart_id=customer.cart.id, production_round_id=production_round_id).first()
                if cart_item:
                    for _ in range(qty):
                        item_order_item = ItemOrderItem(
                            item_order=item_order,
                            production_round_id=production_round_id,
                            unit_price=cart_item.unit_price,
                            product_name=cart_item.product_name,
                            product_image_path=cart_item.product_image_path,
                            item_status="item"
                        )
                        db.session.add(item_order_item)

            # Commit all ItemOrderItem entries together
            db.session.commit()
            
            # Flush to ensure all `ItemOrderItem` entries are added
            db.session.flush()

            # Validate production round statuses
            try:
                item_order.validate_production_round_status()
            except ValueError as e:
                error_message = str(e)
                logging.warning(f"Production round validation failed: {error_message}")
                return redirect(url_for(
                    'user_interface.item_order_payment_status',
                    order_id=item_order.id,
                    message=error_message
                ))

            # Check wallet balance
            if customer.wallet_balance < total_amount:
                logging.warning(f"Insufficient wallet balance for Customer ID: {customer.id}")
                message = "Insufficient wallet balance. The order has been saved but remains unpaid."
                return redirect(url_for('user_interface.item_order_payment_status', order_id=item_order.id, message=message))

            # Deduct wallet balance and finalize payment
            customer.wallet_balance -= total_amount
            item_order.mark_as_paid(payment_method="wallet")
            db.session.add(customer)

            # Update the production round totals
            item_order.update_production_round_totals()

            # Register customer for notifications (ProductionRoundNotification)
            item_order.register_customer_for_notifications()

            # Cleanup cart items
            for prod_round_id_str in checkout_items.keys():
                production_round_id = uuid.UUID(prod_round_id_str)
                cart_item = CartItem.query.filter_by(
                    cart_id=customer.cart.id,
                    production_round_id=production_round_id
                ).first()
                if cart_item:
                    db.session.delete(cart_item)

            # Commit all changes
            db.session.commit()

            logging.info("Payment successful for Order ID: %s", item_order.id)
            session.pop('checkout_items', None)  # Clear session checkout items

            return redirect(url_for('user_interface.item_order_payment_status', order_id=item_order.id))

        return render_template(
            'user/customer/item_order_wallet_payment.html',
            checkout_items=checkout_items,
            subtotal=subtotal,
            tax=round(tax_rate * subtotal, 2),
            transaction_fee=transaction_fee,
            total_amount=total_amount,
            wallet_balance=customer.wallet_balance
        )

    except Exception as e:
        db.session.rollback()
        logging.exception("Unexpected error in /item_order_wallet_payment route: %s", e)
        flash("An error occurred during payment. Please try again.", "error")
        return redirect(url_for('user_interface.view_cart'))




@user_interface.route('/item_order_payment_status/<uuid6:order_id>', methods=['GET'])
def item_order_payment_status(order_id):
    try:
        logging.debug(f"Accessed item_order_payment_status with order ID: {order_id}")
        
        # Fetch the order
        order = ItemOrder.query.get(order_id)
        if not order:
            logging.warning(f"Order ID {order_id} not found in the database.")
            flash("Order not found.")
            return redirect(url_for('user_interface.view_cart'))

        # Retrieve optional message passed via query parameters
        message = request.args.get('message', None)

        logging.debug(f"Rendering payment status for Order ID: {order.id}")
        return render_template('user/customer/item_order_payment_status.html', order=order, message=message)

    except Exception as e:
        logging.exception(f"Error displaying payment status for Order ID: {order_id}: {e}")
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('user_interface.view_cart'))






# proceed the unpaid item order
@user_interface.route('/pay_unpaid_item_order/<uuid6:order_id>', methods=['GET', 'POST'])
def pay_unpaid_item_order(order_id):
    try:
        if 'user_id' not in session or session['role'] != 'customer':
            flash("You need to be logged in as a Customer to continue payment.")
            return redirect(url_for('user_interface.login'))

        customer_id = uuid.UUID(session['user_id'])
        item_order = ItemOrder.query.filter_by(id=order_id, customer_id=customer_id).first()

        if not item_order or item_order.payment_status != 'unpaid':
            flash("Order not found or payment is already processed.")
            return redirect(url_for('user_interface.view_item_orders'))

        if request.method == 'POST':
            payment_method = request.form.get('payment_method')
            if payment_method == 'wallet':
                return redirect(url_for('user_interface.unpaid_item_order_wallet_payment', order_id=order_id))
            else:
                flash("Payment method not supported yet.", "error")
                return redirect(url_for('user_interface.pay_unpaid_item_order', order_id=order_id))

        return render_template('user/customer/pay_unpaid_item_order.html', item_order=item_order)

    except Exception as e:
        logging.exception("Unexpected error in /pay_unpaid_item_order route: %s", e)
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('user_interface.view_item_orders'))



@user_interface.route('/unpaid_item_order_wallet_payment/<uuid6:order_id>', methods=['GET', 'POST'])
def unpaid_item_order_wallet_payment(order_id):
    try:
        logging.debug("Entered /unpaid_item_order_wallet_payment route")

        # Verify user session and role
        if 'user_id' not in session or session.get('role') != 'customer':
            flash("You need to log in as a Customer to proceed with payment.")
            return redirect(url_for('user_interface.login'))

        # Fetch the order and validate it
        customer_id = uuid.UUID(session['user_id'])
        item_order = ItemOrder.query.filter_by(id=order_id, customer_id=customer_id).first()

        if not item_order or item_order.payment_status != 'unpaid':
            flash("Order not found or payment is already processed.")
            return redirect(url_for('user_interface.view_item_orders'))

        # Handle POST: Perform wallet payment
        if request.method == 'POST':
            customer = Customer.query.get(customer_id)

            # Check wallet balance
            if customer.wallet_balance < item_order.total_amount:
                error_message = "Insufficient wallet balance to complete the payment. Please add funds to your wallet or use a different payment method."
                return redirect(url_for(
                    'user_interface.item_order_payment_status', 
                    order_id=item_order.id, 
                    message=error_message
                ))

            try:
                # Validate the production round statuses before proceeding
                item_order.validate_production_round_status()
            except ValueError as e:
                # Redirect immediately if validation fails
                error_message = str(e)
                logging.warning(f"Production round validation failed: {error_message}")
                return redirect(url_for(
                    'user_interface.item_order_payment_status',
                    order_id=item_order.id,
                    message=error_message
                ))


            # Deduct wallet balance and update order
            customer.wallet_balance -= item_order.total_amount
            item_order.mark_as_paid(payment_method="wallet")
            db.session.add(customer)
            db.session.add(item_order)

            #increase the count of the total of the production round
            item_order.update_production_round_totals()

            # Register customer for notifications (ProductionRoundNotification)
            item_order.register_customer_for_notifications()

            # Commit changes to the database
            db.session.commit()

            # Redirect to payment status page
            flash("Payment successful!", "success")
            return redirect(url_for('user_interface.item_order_payment_status', order_id=item_order.id))

        # GET request: Render the payment page
        return render_template(
            'user/customer/unpaid_item_order_wallet_payment.html',
            item_order=item_order
        )

    except Exception as e:
        db.session.rollback()
        logging.exception("Error in /unpaid_item_order_wallet_payment route: %s", e)
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('user_interface.view_item_orders'))






@user_interface.route('/pay_with_sandbox', methods=['GET', 'POST'])
def pay_with_sandbox():
    # Implement mock or sandbox payment
    pass



# test for refund and transfer
@user_interface.route('/mock_refund_item/<uuid6:item_id>', methods=['GET'])
def mock_refund_item(item_id):
    # Simulate refund processing
    return f"Mock Refund: ItemOrderItem with ID {item_id} has been processed for refund."


@user_interface.route('/mock_transfer_item/<uuid6:item_id>', methods=['GET'])
def mock_transfer_item(item_id):
    # Simulate transfer processing
    return f"Mock Transfer: ItemOrderItem with ID {item_id} has been processed for transfer."





# preview page for the delivery order, (just a preview), nothing would be change on the item



# preview delivery order


@user_interface.route('/preview_delivery_order', methods=['GET', 'POST'])
def preview_delivery_order():
    """
    On POST (from some item selection page), gather ItemOrderItem IDs, group them, and render a preview.
    On GET, you could either show an empty page or redirect somewhere else.
    """
    if request.method == 'POST':
        selected_item_ids = request.form.getlist("selected_items")  # e.g. ["uuid1", "uuid2"]
        if not selected_item_ids:
            flash("No items selected for delivery.", "danger")
            return redirect(url_for('user_interface.customer_home'))

        # Validate UUIDs
        try:
            selected_uuids = [uuid.UUID(item_id) for item_id in selected_item_ids]
        except ValueError:
            flash("Invalid item IDs provided.", "danger")
            return redirect(url_for('user_interface.customer_home'))

        # Fetch the items
        item_objs = db.session.query(ItemOrderItem).filter(ItemOrderItem.id.in_(selected_uuids)).all()
        if not item_objs:
            flash("No valid items found.", "danger")
            return redirect(url_for('user_interface.customer_home'))

        # Group them by production_round_id
        grouped_map = {}
        for itm in item_objs:
            pr_id_str = str(itm.production_round_id)
            if pr_id_str not in grouped_map:
                grouped_map[pr_id_str] = {
                    "production_round_id": pr_id_str,
                    "total_quantity": 0,
                    "product_name": None,
                    "product_image_path": None
                }
            grouped_map[pr_id_str]["total_quantity"] += 1

        # Fetch ProductionRound info to fill product name and image
        round_ids = list(grouped_map.keys())
        prod_rounds = (
            db.session.query(ProductionRound)
            .filter(ProductionRound.id.in_([uuid.UUID(r) for r in round_ids]))
            .all()
        )
        round_map = {str(pr.id): pr for pr in prod_rounds}

        for r_id, data in grouped_map.items():
            round_obj = round_map.get(r_id)
            if round_obj and round_obj.product:
                data["product_name"] = round_obj.product.name
                if round_obj.product.artwork:
                    data["product_image_path"] = round_obj.product.artwork.image_path

        grouped_items = list(grouped_map.values())

        # Build raw_items for hidden storage, e.g. so we know exactly which items the user selected
        raw_items = []
        for itm in item_objs:
            raw_items.append({
                "item_id": str(itm.id),
                "production_round_id": str(itm.production_round_id)
            })

        return render_template(
            "user/customer/preview_delivery_order.html",
            grouped_items=grouped_items,
            raw_items=raw_items,
            region="region_1",
            shipping_address=""
        )
    else:
        # GET => show blank or redirect
        return render_template(
            "user/customer/preview_delivery_order.html",
            grouped_items=[],
            raw_items=[],
            region="region_1",
            shipping_address=""
        )




@user_interface.route('/api/calculate_delivery_cost', methods=['POST'])
def calculate_delivery_cost_api():
    """Calculate and return the delivery cost as JSON."""
    try:
        data = request.get_json()
        region = data.get("region")
        grouped_items = data.get("grouped_items")

        # Just define it here:
        REGION_MULTIPLIERS = {
            "1": 1.5,
            "2": 2.0,
            "3": 2.5,
            "4": 3.0
        }

        if not region or not grouped_items:
            return jsonify({"error": "Missing region or grouped_items"}), 400

        if region not in REGION_MULTIPLIERS:
            return jsonify({"error": f"Invalid region: {region}"}), 400

        multiplier = REGION_MULTIPLIERS[region]

        total_points = 0
        for item in grouped_items:
            round_id = item.get("production_round_id")
            quantity = item.get("total_quantity", 0)

            if not round_id or not quantity:
                continue

            production_round = ProductionRound.query.get(uuid.UUID(round_id))
            if production_round:
                total_points += (production_round.delivery_point or 0) * quantity

        total_cost = multiplier * total_points

        return jsonify({"delivery_cost": round(total_cost, 2)})

    except Exception as e:
        logging.exception("Error in calculate_delivery_cost_api:")
        return jsonify({"error": "Server error"}), 500




@user_interface.route('/confirm_delivery_order', methods=['POST'])
def confirm_delivery_order():
    """
    1) Validate user
    2) Read form: region, shipping_address, payment_method, raw_items
    3) Calculate cost server-side
    4) Create DeliveryOrder with payment_status='unpaid'
    5) Redirect to a payment route (wallet, etc.)
    """
    try:
        # Ensure user is a logged-in customer
        if 'user_id' not in session or session['role'] != 'customer':
            flash("You must be logged in as a customer to confirm delivery.", "danger")
            return redirect(url_for('user_interface.login'))

        customer = Customer.query.get(uuid.UUID(session['user_id']))
        if not customer:
            flash("Invalid customer session.", "danger")
            return redirect(url_for('user_interface.login'))

        region = request.form.get('region')
        shipping_address = request.form.get('shipping_address')
        payment_method = request.form.get('payment_method', 'wallet')

        raw_items_str = request.form.get('raw_items')
        if not raw_items_str:
            flash("No items found for delivery.", "danger")
            return redirect(url_for('user_interface.preview_delivery_order'))

        raw_items = json.loads(raw_items_str)

        # Recalc cost on the server to prevent tampering
        total_cost = calculate_delivery_cost_server_side(raw_items, region)

        # Create the DeliveryOrder
        new_order = DeliveryOrder(
            customer_id=customer.id,
            region = region,
            shipping_address=shipping_address,
            delivery_cost=total_cost,
            status="created",
            payment_status="unpaid",
            timestamp=datetime.now(),
            delivery_item=raw_items,
            payment_method=payment_method
        )
        db.session.add(new_order)
        db.session.commit()

        # Now route user to the chosen payment method
        if payment_method == 'wallet':
            return redirect(url_for('user_interface.delivery_order_wallet_payment', delivery_order_id=new_order.id))
        else:
            flash("Payment method not yet supported.", "info")
            return redirect(url_for('user_interface.delivery_order_payment_status', delivery_order_id=new_order.id))

    except Exception as e:
        db.session.rollback()
        logging.exception("confirm_delivery_order error: %s", e)
        flash("An error occurred while creating your delivery order.", "danger")
        return redirect(url_for('user_interface.preview_delivery_order'))


def calculate_delivery_cost_server_side(raw_items, region):
    """
    Almost the same logic as /api/calculate_delivery_cost, but used in final server check.
    """
    REGION_MULTIPLIERS = {
        "1": 1.5,
        "2": 2.0,
        "3": 2.5,
        "4": 3.0
    }
    multiplier = REGION_MULTIPLIERS.get(region, 1.0)

    total_points = 0
    for item_data in raw_items:
        pr_id_str = item_data.get("production_round_id")
        if pr_id_str:
            pr = ProductionRound.query.get(uuid.UUID(pr_id_str))
            if pr:
                total_points += pr.delivery_point

    return round(total_points * multiplier, 2)


# delivery order payment (wallet)


@user_interface.route('/delivery_order_wallet_payment/<uuid6:delivery_order_id>', methods=['GET', 'POST'])
def delivery_order_wallet_payment(delivery_order_id):
    """
    Handles the wallet payment for a newly created, unpaid DeliveryOrder.
    """
    try:
        logging.debug("Entered /delivery_order_wallet_payment route")

        # 1) Verify user session
        if 'user_id' not in session or session['role'] != 'customer':
            flash("You need to log in as a Customer to proceed with payment.")
            return redirect(url_for('user_interface.login'))

        # 2) Fetch the DeliveryOrder
        customer_id = uuid.UUID(session['user_id'])
        delivery_order = DeliveryOrder.query.filter_by(
            id=delivery_order_id,
            customer_id=customer_id
        ).first()

        if not delivery_order:
            flash("Delivery order not found.", "danger")
            return redirect(url_for('user_interface.preview_delivery_order'))

        if delivery_order.payment_status != 'unpaid':
            flash("This order has already been paid or is invalid for payment.", "info")
            return redirect(url_for('user_interface.delivery_order_payment_status',
                                    delivery_order_id=delivery_order.id))

        customer = Customer.query.get(customer_id)
        if not customer:
            flash("Invalid customer session. Please log in again.", "danger")
            return redirect(url_for('user_interface.login'))

        # 3) GET request => show a simple page with the total cost, wallet balance, a confirm button, etc.
        if request.method == 'GET':
            return render_template(
                "user/customer/delivery_order_wallet_payment.html",
                delivery_order=delivery_order,
                wallet_balance=customer.wallet_balance
            )

        # 4) POST => Perform the payment
        if request.method == 'POST':
            total_cost = delivery_order.delivery_cost
            if customer.wallet_balance < total_cost:
                error_msg = "Insufficient wallet balance. Please recharge or use another payment method."
                logging.warning(error_msg)
                return redirect(url_for('user_interface.delivery_order_payment_status',
                                        delivery_order_id=delivery_order.id,
                                        message=error_msg))

            # Deduct from wallet
            customer.wallet_balance -= total_cost
            db.session.add(customer)

            # Mark delivery_order as paid
            delivery_order.payment_status = "paid"
            delivery_order.payment_timestamp = datetime.now()
            db.session.add(delivery_order)

            # Also, set item_status='in_process' for each item in the order
            # We have the "delivery_item" storing all item_ids. Let's update them:
            raw_items = delivery_order.delivery_item  # e.g. [{"item_id": "...", ...}, ...]
            for item_data in raw_items:
                item_id_str = item_data.get("item_id")
                if not item_id_str:
                    continue
                ioi = ItemOrderItem.query.get(uuid.UUID(item_id_str))
                if ioi:
                    ioi.item_status = "in_process"
                    db.session.add(ioi)

            db.session.commit()
            logging.info(f"Payment successful for DeliveryOrder {delivery_order.id} via wallet.")

            # Redirect to status page
            return redirect(url_for('user_interface.delivery_order_payment_status',
                                    delivery_order_id=delivery_order.id))

    except Exception as e:
        db.session.rollback()
        logging.exception("Unexpected error in /delivery_order_wallet_payment route: %s", e)
        flash("An error occurred during wallet payment.", "error")
        return redirect(url_for('user_interface.preview_delivery_order'))



@user_interface.route('/delivery_order_payment_status/<uuid6:delivery_order_id>', methods=['GET'])
def delivery_order_payment_status(delivery_order_id):
    """
    Shows the payment status (paid/unpaid) of the DeliveryOrder.
    """
    try:
        logging.debug(f"Accessed delivery_order_payment_status with order ID: {delivery_order_id}")
        
        # Possibly check user session
        if 'user_id' not in session or session['role'] != 'customer':
            flash("You need to log in as a Customer.")
            return redirect(url_for('user_interface.login'))

        delivery_order = DeliveryOrder.query.get(delivery_order_id)
        if not delivery_order:
            flash("Delivery order not found.", "danger")
            return redirect(url_for('user_interface.preview_delivery_order'))

        message = request.args.get('message', None)
        return render_template(
            'user/customer/delivery_order_payment_status.html',
            delivery_order=delivery_order,
            message=message
        )

    except Exception as e:
        logging.exception(f"Error displaying payment status for DeliveryOrder {delivery_order_id}: {e}")
        flash("An error occurred while showing the payment status.", "error")
        return redirect(url_for('user_interface.preview_delivery_order'))



# Artist Dashboard: Submit Artwork and Products, View Disapproval Reasons for artwork and product
# if the product is artist arranged, the artist can edit the product introduction (need implementation for product that is platform arranged)
# the artist can also toggle the display status of the product
# for both artist and platform arranged products, their details is only going to be changed by the order management admin
# However, for artist arranged products, the artist can submit the request for the change (need implementation)


@user_interface.route('/artist_dashboard', methods=['GET'])
def artist_dashboard():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access the dashboard.")
        return redirect(url_for('user_interface.login'))

    try:
        # Convert the user_id from session to UUID before querying
        user_uuid = uuid.UUID(session['user_id'])
        artist = Artist.query.get(user_uuid)
        unread_notifications_count = Notification.get_unread_notifications_count(user_uuid)
    except ValueError:
        flash("Invalid user ID format.")
        return redirect(url_for('user_interface.login'))

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user_interface.login'))

    # Retrieve the latest five artworks with the most recent changes in status
    recent_artworks = Artwork.query.filter_by(artist_id=artist.id).order_by(Artwork.updated_at.desc()).limit(5).all()

    # Using the relationship to get products associated with each artwork
    recent_artworks_with_products = [
        {"artwork": artwork, "products": artwork.products} for artwork in recent_artworks
    ]

    return render_template(
        'user/artist/artist_dashboard.html',
        artist=artist,
        recent_artworks=recent_artworks_with_products,
        unread_notifications_count=unread_notifications_count
    )




@user_interface.route('/edit_artist_bio', methods=['GET', 'POST'])
def edit_artist_bio():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to edit your bio.")
        return redirect(url_for('user_interface.login'))

    # Fetch the current logged-in artist
    artist = Artist.query.get(uuid.UUID(session['user_id']))

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user_interface.login'))

    if request.method == 'POST':
        # Get the bio from the form submission
        new_bio = request.form.get('bio')
        if new_bio:
            # Update the artist's bio
            artist.bio = new_bio
            db.session.commit()
            flash("Your bio has been successfully updated.")
            return redirect(url_for('user_interface.artist_dashboard'))
        else:
            flash("Bio cannot be empty.")

    # Render the form for editing the bio (GET request)
    return render_template('user/artist/edit_artist_bio.html', artist=artist)




# artwork

@user_interface.route('/submit_new_artwork', methods=['GET', 'POST'])
def submit_new_artwork():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access this page.")
        return redirect(url_for('user_interface.login'))

    # Convert the user_id from session to UUID before querying
    user_uuid = uuid.UUID(session['user_id'])
    artist = Artist.query.get(user_uuid)
    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user_interface.login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        manufacturing_specs = request.form['manufacturing_specs']
        hard_tags = request.form['hard_tags']
        soft_tags = request.form.get('soft_tags', "")

        # Handle file upload
        if 'image' not in request.files or request.files['image'].filename == '':
            flash("Error: Image file is required.")
            return redirect(request.url)

        file = request.files['image']
        filename = secure_filename(file.filename)
        upload_folder = current_app.config['UPLOAD_FOLDER']

        # Ensure the upload folder exists
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        # Save the file
        file.save(os.path.join(upload_folder, filename))

        # Save the relative path to the database
        image_path = f'uploads/{filename}'

        # Create new artwork
        try:
            new_artwork = Artwork(
                title=title,
                description=description,
                image_path=image_path,
                manufacturing_specs=manufacturing_specs,
                hard_tags=hard_tags,
                soft_tags=soft_tags,
                approval_status='Pending',
                artist_id=artist.id
            )
            db.session.add(new_artwork)
            db.session.commit()
            flash("Artwork submitted successfully for approval.")
        except Exception as e:
            flash(f"Error: {str(e)}", 'error')
            return redirect(request.url)

        return redirect(url_for('user_interface.artwork_upload_success'))

    return render_template('user/artist/submit_artwork.html', artist=artist)



@user_interface.route('/artwork_upload_success', methods=['GET'])
def artwork_upload_success():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to view this page.")
        return redirect(url_for('user_interface.login'))

    # Retrieve the artist's name for display
    user_uuid = uuid.UUID(session['user_id'])
    artist = Artist.query.get(user_uuid)

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user_interface.login'))

    return render_template('user/artist/artwork_upload_success.html', artist=artist)


@user_interface.route('/all_artworks', methods=['GET'])
def all_artworks():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to view this page.")
        return redirect(url_for('user_interface.login'))

    try:
        user_uuid = uuid.UUID(session['user_id'])
        artist = Artist.query.get(user_uuid)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user_interface.login'))

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user_interface.login'))

    # Retrieve all artworks created by the artist
    all_artworks = Artwork.query.filter_by(artist_id=artist.id).all()

    return render_template('user/artist/all_artworks.html', artist=artist, artworks=all_artworks)




@user_interface.route('/artist_search_artworks', methods=['GET'])
def artist_search_artworks():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to perform a search.")
        return redirect(url_for('user_interface.login'))

    query = request.args.get('query')
    if not query:
        flash("Please enter a search query.")
        return redirect(url_for('user_interface.all_artworks'))

    try:
        user_uuid = uuid.UUID(session['user_id'])
        artist = Artist.query.get(user_uuid)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user_interface.login'))

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user_interface.login'))

    # Search for artworks and associated products
    search_term = f"%{query}%"
    artworks = Artwork.query.filter(
        Artwork.artist_id == artist.id,
        (Artwork.title.ilike(search_term)) | (Artwork.description.ilike(search_term)) | (Artwork.hard_tags.ilike(search_term)) | (Artwork.soft_tags.ilike(search_term))
    ).all()

    return render_template('user/artist/artist_search_results.html', artist=artist, artworks=artworks, query=query)



# artwork update request

@user_interface.route('/update_artwork/<uuid6:artwork_id>', methods=['GET', 'POST'])
def update_artwork(artwork_id):
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an artist to update artwork.")
        return redirect(url_for('user_interface.artist_login'))

    # Retrieve the artwork
    artwork = Artwork.query.get_or_404(artwork_id)
    
    # Ensure the logged-in artist owns the artwork
    if artwork.artist_id != uuid.UUID(session['user_id']):
        flash("You do not have permission to update this artwork.")
        return redirect(url_for('user_interface.artist_dashboard'))

    if request.method == 'POST':
        # Retrieve updated information from the form
        proposed_title = request.form.get('title', None)
        proposed_description = request.form.get('description', None)
        proposed_hard_tags = request.form.get('hard_tags', None)
        proposed_soft_tags = request.form.get('soft_tags', None)
        proposed_manufacturing_specs = request.form.get('manufacturing_specs', None)

        # Create a new ArtworkUpdate entry
        new_update = ArtworkUpdate(
            artwork_id=artwork.id,
            artist_id=artwork.artist_id,
            proposed_title=proposed_title,
            proposed_description=proposed_description,
            proposed_hard_tags=proposed_hard_tags,
            proposed_soft_tags=proposed_soft_tags,
            proposed_manufacturing_specs=proposed_manufacturing_specs,
            status='Pending'
        )
        db.session.add(new_update)
        db.session.commit()

        flash("Your artwork update request has been submitted for review.")
        return redirect(url_for('user_interface.artist_dashboard'))

    return render_template('user/artist/update_artwork.html', artwork=artwork)


# product

@user_interface.route('/artist_product_management/<uuid6:product_id>', methods=['GET'])
def artist_product_management(product_id):
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access this page.")
        return redirect(url_for('user_interface.login'))

    # Convert product_id from URL to UUID and fetch the product
    try:
        product_uuid = uuid.UUID(str(product_id))
        product = Product.query.get(product_uuid)
    except ValueError:
        flash("Invalid product ID format.")
        return redirect(url_for('user_interface.artist_dashboard'))

    if not product:
        flash("Product not found.")
        return redirect(url_for('user_interface.artist_dashboard'))

    return render_template('user/artist/artist_product_management.html', product=product)



# this might need to be deleted?


@user_interface.route('/toggle_display_status/<uuid6:product_id>', methods=['POST'])
def toggle_display_status(product_id):
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to change product display status.")
        return redirect(url_for('user_interface.login'))

    product = Product.query.get(product_id)

    # Ensure product belongs to the artist and is approved
    if product and product.production_status == 'Approved':
        product.toggle_display_status()
        flash(f"Display status for '{product.name}' updated to '{product.display_status}'.")
    else:
        flash("Invalid product or product is not approved.")

    return redirect(url_for('user_interface.artist_dashboard'))

# product series, for display
# need rebuild for the artist to manage the series
# the series should be independent of what artwork it belongs to
# just a collection of products that the artist wants to group together





@user_interface.route('/view_artwork_disapproval_reason/<uuid6:artwork_id>')
def view_artwork_disapproval_reason(artwork_id):
    # Ensure the user is logged in as an artist
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to view the disapproval reason.")
        return redirect(url_for('user_interface.login'))

    # Retrieve the artwork directly using the artwork_id passed by the route
    artwork = Artwork.query.get(artwork_id)

    # If artwork not found or the current user is not authorized to view it, flash an error
    if not artwork or str(artwork.artist_id) != session['user_id']:
        flash("You are not authorized to view this disapproval reason.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Ensure the artwork has been disapproved before allowing access to disapproval reason
    if artwork.approval_status != 'Disapproved':
        flash("This artwork has not been disapproved.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Render the disapproval reason page with the artwork details
    return render_template('user/artist/view_artwork_disapproval_reason.html', artwork=artwork)



@user_interface.route('/view_product_disapproval_reason/<uuid6:product_id>', methods=['GET'])
def view_product_disapproval_reason(product_id):
    # Ensure the user is logged in as an artist
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to view the disapproval reason.")
        return redirect(url_for('user_interface.login'))

    # Retrieve the product directly using the product_id passed by the route
    product = Product.query.get_or_404(product_id)

    # Ensure the product belongs to the current artist via the associated artwork
    if str(product.artwork.artist_id) != session['user_id']:
        flash("You are not authorized to view this disapproval reason.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Ensure the product has been disapproved before allowing access to disapproval reason
    if product.production_status != 'Disapproved':
        flash("This product has not been disapproved.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Render the disapproval reason template with the product details
    return render_template('user/artist/view_product_disapproval_reason.html', product=product)




@user_interface.route('/submit_product/<uuid6:artwork_id>', methods=['GET', 'POST'])
def submit_product(artwork_id):
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to submit a product.", 'error')
        return redirect(url_for('user_interface.login'))

    # Get the artwork using the provided artwork_id
    artwork = Artwork.query.get(artwork_id)

    # Ensure that the artwork belongs to the logged-in artist
    if not artwork or artwork.artist_id != uuid.UUID(session['user_id']):
        flash("You are not authorized to submit a product for this artwork.", 'error')
        return redirect(url_for('user_interface.artist_dashboard'))

    if request.method == 'POST':
        name = request.form['name']
        production_specs = request.form['production_specs']
        manufacture_type = request.form['manufacture_type']

        try:
            # Create product with Pending status for Product Approval Admin approval
            new_product = Product(
                name=name,
                production_specs=production_specs,
                manufacture_type=manufacture_type,
                artwork_id=artwork.id,
                artist_id=artwork.artist_id,  # Set artist_id to link the product to the artist
                production_status='Pending'
            )

            db.session.add(new_product)
            db.session.commit()

            # Handle multiple file uploads if "platform arranged" is selected
            if manufacture_type == 'platform arranged':
                if 'design_files' in request.files:
                    files = request.files.getlist('design_files')
                    for file in files:
                        if file.filename == '':
                            continue  # Skip empty file fields

                        # Secure the filename and save the file
                        filename = secure_filename(file.filename)
                        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)

                        # Create a DesignFile entry in the database
                        new_file = DesignFile(
                            filename=filename,
                            file_type=file.content_type,
                            product_id=new_product.id
                        )
                        db.session.add(new_file)

                    db.session.commit()

            # Redirect to the submission status page with success
            return render_template(
                'user/artist/product_submission_status.html',
                success=True,
                redirect_url=url_for('user_interface.artist_dashboard')
            )

        except Exception as e:
            # Handle any unexpected exceptions
            print(f"Error: {e}")  # For debugging purposes
            # Redirect to the submission status page with failure
            return render_template(
                'user/artist/product_submission_status.html',
                success=False,
                redirect_url=url_for('user_interface.artist_dashboard')
            )

    return render_template('user/artist/submit_product.html', artwork=artwork)


# artist choose who would be in control of starting the production round for a product

@user_interface.route('/manage_production_initialization/<uuid6:product_id>', methods=['GET', 'POST'])
def manage_production_initialization(product_id):
    """Manage the initialization control of production rounds for a product."""
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to manage production initialization.")
        return redirect(url_for('user_interface.login'))

    try:
        product = Product.query.get_or_404(product_id)
        if product.artist_id != uuid.UUID(session['user_id']):
            flash("Unauthorized access to this product.")
            return redirect(url_for('user_interface.artist_dashboard'))

        if request.method == 'POST':
            # Toggle the artist-controlled flag
            product.toggle_control()
            flash(
                "Production round initialization is now "
                + ("controlled by the artist." if product.artist_controlled else "controlled by the admin.")
            )
            return redirect(url_for('user_interface.manage_production_initialization', product_id=product.id))

        return render_template(
            'user/artist/manage_production_initialization.html',
            product=product
        )

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('user_interface.artist_dashboard'))



# route for the situation where the artist is in control of the production round initialization


@user_interface.route('/artist_initialize_production_round/<uuid6:product_id>', methods=['POST'])
def artist_initialize_production_round(product_id):
    """Route for the artist to initialize a production round."""
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to initialize a production round.")
        return redirect(url_for('user_interface.login'))

    product = Product.query.get_or_404(product_id)
    if product.artist_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access to this product.")
        return redirect(url_for('user_interface.artist_dashboard'))

    if not product.artist_controlled:
        flash("You do not have control over initializing production rounds for this product.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Check if an active production round already exists
    existing_round = ProductionRound.query.filter_by(product_id=product.id, is_active=True).first()
    if existing_round:
        flash("An in-progress production round already exists. You cannot initialize a new one.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Create a new production round
    max_waiting_time_days = 60  # Default to 60 days
    max_waiting_time = datetime.now(timezone.utc) + timedelta(days=max_waiting_time_days)

    new_round = ProductionRound(
        product_id=product.id,
        artist_id=product.artist_id,
        admin_id=product.assigned_admin_id,  # Notify the assigned admin
        max_waiting_time=max_waiting_time,
        stage="initialize",
        is_published=False,
        is_active=True,  # Set the new round as active
        created_at=datetime.now(),  # Explicit initialization (optional)
        updated_at=datetime.now()   # Explicit initialization (optional)
    )
    db.session.add(new_round)
    db.session.commit()

    # Send a notification to the assigned admin
    admin = OrderManagementAdmin.query.get(product.assigned_admin_id)
    if admin:
        try:
            Notification.send_notification(
                user_id=admin.id,
                message=f"A new production round for '{product.name}' has been initialized by the artist.",
                type="production_round",
                link=url_for('admin.admin_manage_production_round', product_id=product.id, _external=True)
            )
        except Exception as e:
            flash(f"Notification failed: {str(e)}", 'error')

    flash("Production round initialized and the admin has been notified.")
    return redirect(url_for('user_interface.artist_product_management', product_id=product_id))




@user_interface.route('/download_file/<uuid6:file_id>')
def download_file(file_id):
    if 'user_id' not in session:
        flash("You need to be logged in to download files.")
        return redirect(url_for('user_interface.login'))

    design_file = DesignFile.query.get(file_id)
    if not design_file:
        flash("File not found.")
        return redirect(request.referrer or url_for('user_interface.home'))

    # Construct the full file path
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], design_file.filename)

    # Return the file as an attachment
    return send_file(file_path, as_attachment=True)



# notification system for the customer and the artist

# Dialog Route for Artists, right now there is no dialog for the customer...
# maybe there would be customer service dialog in the future?
# customer service dialog might be very different from the artist dialog...
# therefore right now, only artist dialog is implemented


# dialog section:
# product dialog for the active production round
# historical dialog collection and the dialog for previous dialogs (changed to the archived information section)



@user_interface.route('/product_dialog/<uuid6:product_id>', methods=['GET', 'POST'])
def artist_active_product_dialog(product_id):
    """Dialog for the current active production round for the artist."""
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access this dialog.")
        return redirect(url_for('user_interface.login'))

    # Fetch the active production round
    production_round = ProductionRound.query.filter_by(product_id=product_id, is_active=True).first()
    if not production_round:
        flash("No active production round found for this product.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Check if the artist is authorized
    if production_round.artist_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access to this dialog.")
        return redirect(url_for('user_interface.artist_dashboard'))

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

        # Notify the admin
        recipient_id = production_round.admin_id
        Notification.send_notification(
            user_id=recipient_id,
            message=f"You have a new message in the production round for '{production_round.product.name}'.",
            link=url_for('admin.admin_active_product_dialog', product_id=production_round.product_id, _external=True),
            type='dialog'
        )

    # Fetch all messages in this dialog
    messages = Dialog.query.filter_by(production_round_id=production_round.id).order_by(Dialog.timestamp).all()

    return render_template('user/artist/product_dialog.html', production_round=production_round, messages=messages)



# archieved information section for inactive production round (information and dialog)


# archived information for a production round: information and dialog

@user_interface.route('/archived_production_rounds/<uuid6:product_id>', methods=['GET'])
def archived_production_rounds(product_id):
    """List all inactive production rounds for a specific product."""
    product = Product.query.get(product_id)
    if not product:
        flash("Product not found.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Fetch all inactive production rounds for the product
    inactive_rounds = (
        ProductionRound.query.filter_by(product_id=product_id, is_active=False)
        .order_by(ProductionRound.created_at.desc())
        .all()
    )

    return render_template(
        'user/artist/archived_production_rounds.html',
        product=product,
        inactive_rounds=inactive_rounds,
    )





@user_interface.route('/archived_production_round_dialogs/<uuid6:round_id>', methods=['GET'])
def archived_production_round_dialogs(round_id):
    """View archived dialogs of a specific production round."""
    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.is_active:
        flash("Invalid or active production round.")
        return redirect(url_for('user_interface.artist_dashboard'))

    dialogs = production_round.dialogs  # Retrieve all dialogs for the production round

    # Attach files to each dialog for display
    for dialog in dialogs:
        dialog.files_list = dialog.files  # Collect related files

    return render_template(
        'user/artist/archived_production_round_dialogs.html',
        production_round=production_round,
        dialogs=dialogs,
    )




@user_interface.route('/archived_production_round_details/<uuid6:round_id>', methods=['GET'])
def archived_production_round_details(round_id):
    """View detailed information about an archived production round."""
    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.is_active:
        flash("Invalid or active production round.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Extract stage goals (assuming JSON format)
    stage_goals = json.loads(production_round.production_goals or "[]")

    return render_template(
        'user/artist/archived_production_round_details.html',
        production_round=production_round,
        stage_goals=stage_goals,
    )


# Notifications Viewing System for Artists and Customers

@user_interface.route('/view_notifications', methods=['GET', 'POST'])
def view_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('user_interface.login'))

    user_id = uuid.UUID(session['user_id'])
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.timestamp.desc()).all()

    categorized_notifications = {}
    for notification in unread_notifications:
        if notification.type not in categorized_notifications:
            categorized_notifications[notification.type] = []
        categorized_notifications[notification.type].append(notification)

    if request.method == 'POST':
        for notification in unread_notifications:
            notification.is_read = True
        db.session.commit()
        flash("All notifications marked as read.")

    return render_template('user/account/unread_notifications.html', categorized_notifications=categorized_notifications)


@user_interface.route('/mark_notification_read/<uuid6:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    # Ensure the user is logged in
    if 'user_id' not in session:
        flash("You need to be logged in to mark a notification as read.")
        return redirect(url_for('user_interface.login'))

    try:
        # Find the notification by ID
        notification = Notification.query.get(notification_id)

        # Ensure the notification belongs to the logged-in user
        user_id = uuid.UUID(session['user_id'])
        if notification.user_id != user_id:
            flash("You are not authorized to mark this notification as read.")
            return redirect(url_for('user_interface.view_notifications'))

        # Mark the notification as read
        notification.is_read = True
        db.session.commit()
        flash("Notification has been marked as read.")

    except Exception as e:
        flash("An error occurred while trying to mark the notification as read.")

    return redirect(url_for('user_interface.view_notifications'))




@user_interface.route('/view_read_notifications', methods=['GET', 'POST'])
def view_read_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('user_interface.login'))

    user_id = uuid.UUID(session['user_id'])
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=True).order_by(Notification.timestamp.desc()).all()

    # Categorize notifications
    categorized_notifications = {}
    for notification in unread_notifications:
        if notification.type not in categorized_notifications:
            categorized_notifications[notification.type] = []
        categorized_notifications[notification.type].append(notification)

    return render_template('user/account/read_notifications.html', categorized_notifications=categorized_notifications)


# customer service

# customer service for item order

# customer service for delivery order


@user_interface.route('/customer_service/delivery_created/<uuid:delivery_order_id>', methods=['GET', 'POST'])
def customer_service_delivery_created(delivery_order_id):
    """
    Mock route for customer service requests for a paid but created delivery order.
    """
    # Example logic for "paid and created" orders
    # Fetch the delivery order (mock data for now)
    delivery_order = {
        "id": delivery_order_id,
        "status": "created",
        "payment_status": "paid",
        "shipping_address": "123 Mock Street",
        "delivery_cost": 15.00,
        "timestamp": "2025-01-27 14:45:00"
    }

    # Render the mock customer service page
    return render_template(
        "user/customer/customer_service_delivery_created.html",
        delivery_order=delivery_order
    )


@user_interface.route('/customer_service/delivery_delivered/<uuid:delivery_order_id>', methods=['GET', 'POST'])
def customer_service_delivery_delivered(delivery_order_id):
    """
    Mock route for customer service requests for a delivered order.
    """
    # Example logic for "delivered" orders
    # Fetch the delivery order (mock data for now)
    delivery_order = {
        "id": delivery_order_id,
        "status": "delivered",
        "shipping_address": "456 Example Lane",
        "delivery_cost": 20.00,
        "timestamp": "2025-01-27 10:30:00",
        "packages": [
            {"package_number": "PKG001", "status": "delivered", "packaging_video_path": "/static/videos/PKG001.mp4"},
            {"package_number": "PKG002", "status": "delivered", "packaging_video_path": "/static/videos/PKG002.mp4"}
        ]
    }

    # Render the mock customer service page
    return render_template(
        "user/customer/customer_service_delivery_delivered.html",
        delivery_order=delivery_order
    )
