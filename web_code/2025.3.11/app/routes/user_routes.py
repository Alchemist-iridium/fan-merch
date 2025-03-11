from flask import request, Blueprint,current_app, render_template, redirect, url_for, session, flash, current_app, send_file, jsonify
from datetime import datetime, timezone, timedelta
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from app.models import *
import json
from uuid6 import uuid6
# this line needs modification
from app.extensions import db
import uuid
import uuid6
from sqlalchemy.sql import func
import logging

from dateutil.relativedelta import relativedelta
from flask_login import login_user, logout_user, login_required, current_user

from app.user_utils import *

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
                new_user = Customer(name=name, email=email, password_hash=password_hash, role=role)
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
    if current_user.is_authenticated:
        if current_user.role == 'artist':
            return redirect(url_for('user_interface.artist_dashboard'))
        elif current_user.role == 'customer':
            return redirect(url_for('user_interface.customer_home'))
        else:
            flash("Please use the appropriate login page for your role.")
            return redirect(url_for('user_interface.login'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.role in ['customer', 'artist'] and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Login successful!")
            if user.role == 'artist':
                return redirect(url_for('user_interface.artist_dashboard'))
            elif user.role == 'customer':
                return redirect(url_for('user_interface.customer_home'))
        else:
            error = "Wrong email or password, or invalid user role"
            return render_template('user/account/login.html', error=error)
    return render_template('user/account/login.html')




# Renamed to avoid conflict with Flask-Login's login_required
@user_interface.route('/login_needed')
def login_needed():
    return render_template('user/account/login_needed.html')


@user_interface.route('/logout')
@login_required  # Uses Flask-Login's decorator
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for('user_interface.home'))




# after login, the customer will be redirected to the customer_home page
@user_interface.route('/customer_home', methods=['GET'])
@customer_required
def customer_home():
    customer = current_user
    unread_count = Notification.get_unread_notifications_count(customer.id)
    return render_template('user/customer/customer_home.html', customer=customer, unread_count=unread_count)


# will be different??? customization?

@user_interface.route('/customer_search', methods=['POST'])
@customer_required
def customer_search():
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

    return render_template('user/public_search/search_result.html', search_results=search_results, current_user = current_user)






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

    return render_template('user/public_search/search_result.html', search_results=search_results)




@user_interface.route('/artist/<uuid6:artist_id>')
def artist_public_page(artist_id):
    artist = Artist.query.get_or_404(artist_id)
    artworks = Artwork.query.filter_by(artist_id=artist.id, approval_status='Approved').all()

    customer = None
    fallback_url = url_for('user_interface.home')  # Default for unauthenticated users
    if current_user.is_authenticated:
        if current_user.role == 'customer':
            customer = current_user
            fallback_url = url_for('user_interface.customer_home')
        elif current_user.role == 'artist':
            fallback_url = url_for('user_interface.artist_dashboard')

    return render_template(
        'user/public_search/artist_public_page.html', 
        artist=artist, 
        artworks=artworks,
        customer=customer,
        fallback_url=fallback_url
    )



@user_interface.route('/artwork/<uuid6:artwork_id>')
def artwork_page(artwork_id):
    artwork = Artwork.query.get_or_404(artwork_id)

    customer = None
    fallback_url = url_for('user_interface.home')  # Default for unauthenticated users
    if current_user.is_authenticated:
        if current_user.role == 'customer':
            customer = current_user
            fallback_url = url_for('user_interface.customer_home')
        elif current_user.role == 'artist':
            fallback_url = url_for('user_interface.artist_dashboard')

    approved_products = []
    if artwork and artwork.approval_status == 'Approved':
        approved_products = Product.query.filter_by(
            artwork_id=artwork.id, 
            production_status='Approved', 
            display_status=True
        ).all()

    return render_template(
        'user/public_search/artwork_page.html',
        work=artwork,
        approved_products=approved_products,
        customer=customer,
        fallback_url=fallback_url
    )


@user_interface.route('/product_public/<uuid6:product_id>', methods=['GET'])
def product_public(product_id):
    product = Product.query.get(product_id)
    if not (product and product.production_status == 'Approved' and product.display_status):
        flash("This product is not available for public viewing.")
        return redirect(url_for('user_interface.home'))

    production_round = (
        ProductionRound.query.filter_by(product_id=product_id, is_active=True, is_published=True)
        .first()
    )

    stage_goals = []
    if production_round and production_round.production_goals:
        try:
            stage_goals = json.loads(production_round.production_goals)
        except ValueError:
            flash("Error loading stage goals. Please contact support.")

    customer = None
    is_signed_up = False
    fallback_url = url_for('user_interface.home')  # Default for unauthenticated users
    if current_user.is_authenticated:
        if current_user.role == 'customer':
            customer = current_user
            signup = ProductNotificationSignup.query.filter_by(
                customer_id=customer.id, product_id=product_id
            ).first()
            is_signed_up = bool(signup)
            fallback_url = url_for('user_interface.customer_home')
        elif current_user.role == 'artist':
            fallback_url = url_for('user_interface.artist_dashboard')

    return render_template(
        'user/public_search/product_public.html',
        product=product,
        production_round=production_round,
        stage_goals=stage_goals,
        is_signed_up=is_signed_up,
        is_logged_in=current_user.is_authenticated,
        fallback_url=fallback_url
    )




@user_interface.route('/register_notification/<uuid6:product_id>', methods=['POST'])
@customer_required
def register_notification(product_id):
    """Register a customer for product notification signup."""

    customer = current_user
    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.product_public', product_id=product_id))
    
     # Fetch the product
    product = Product.query.get(product_id)
    if not product:
        flash("Product not found.")
        return redirect(url_for('user_interface.product_public', product_id=product_id))

    # Check if already signed up
    signup = ProductNotificationSignup.query.filter_by(
        customer_id=customer.id, product_id=product_id
    ).first()

    if signup:
        flash("You are already signed up for notifications for this product.")
    else:
        try:
            new_signup = ProductNotificationSignup(
                customer_id=customer.id,
                product_id=product_id
            )
            db.session.add(new_signup)
            db.session.commit()
            # Check threshold after signup is committed

            product.check_and_notify_threshold()

            flash("Successfully signed up for product notifications!")
        except Exception as e:
            db.session.rollback()
            flash(f"Error signing up: {str(e)}", 'error')

    return redirect(url_for('user_interface.product_public', product_id=product_id))





@user_interface.route('/unregister_notification/<uuid6:product_id>', methods=['POST'])
@customer_required
def unregister_notification(product_id):
    """Unregister a customer from product notification signup."""


    customer = current_user
    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.product_public', product_id=product_id))

    signup = ProductNotificationSignup.query.filter_by(
        customer_id=customer.id, product_id=product_id
    ).first()

    if not signup:
        flash("You are not signed up for notifications for this product.")
    else:
        try:
            db.session.delete(signup)
            db.session.commit()
            flash("Successfully unregistered from product notifications.")
        except Exception as e:
            db.session.rollback()
            flash(f"Error unregistering: {str(e)}", 'error')

    return redirect(url_for('user_interface.product_public', product_id=product_id))



# Customer Dashboard: Region adjust, View Item & Order, Favorite Artworks, Followed Artists, Wallet Balance

@user_interface.route('/customer_dashboard')
@customer_required
def customer_dashboard():

    try:
        customer = current_user
    except ValueError:
        flash("Invalid user ID format.")
        return redirect(url_for('user_interface.login'))

    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.login'))

    return render_template(
        'user/customer/customer_dashboard.html',
        customer=customer,
        wallet_balance=customer.wallet_balance
    )


@user_interface.route('/customer_dashboard/favorite_artworks')
@customer_required
def favorite_artworks():

    customer = current_user
    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.login'))

    return render_template(
        'user/customer/favorite_artworks.html',
        favorite_artworks=customer.favorite_artworks  # Assuming relationship exists
    )




@user_interface.route('/customer_dashboard/followed_artists')
@customer_required
def followed_artists():

    customer = current_user
    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user_interface.login'))

    return render_template(
        'user/customer/followed_artists.html',
        followed_artists=customer.followed_artists  # Assuming relationship exists
    )



# add fund for wallet

@user_interface.route('/add_funds', methods=['POST'])
@customer_required
def add_funds():
    """
    Add funds to the user's wallet.
    """

    try:
        # Ensure the amount is a valid float with two decimal places
        amount = request.form['amount']
        if not amount.replace('.', '', 1).isdigit():
            raise ValueError("Invalid input. Please enter a valid number.")

        amount = round(float(amount), 2)  # Convert and round to two decimal places

        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        customer = current_user
        customer.wallet_balance = round(customer.wallet_balance + amount, 2)  # Ensure two decimal places

        db.session.add(customer)
        db.session.commit()

        flash(f"${amount:.2f} has been added to your wallet.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for('user_interface.customer_dashboard'))




# item management, dealt as a category (waiting for delivery category is separated)

@user_interface.route('/item_management/<string:category>', methods=['GET'])
@customer_required
def item_management(category):
    """
    Handle item management for all categories except "waiting_for_delivery".
    """

    try:

        # Base query
        items_query = ItemOrderItem.query.join(ItemOrder).filter(ItemOrder.customer_id == current_user.id)

        # Ensure relationships are loaded
        items_query = items_query.options(
            joinedload(ItemOrderItem.production_round),
            joinedload(ItemOrderItem.item_order)
        )

        # Filter for each category
        category_filters = {
            "waiting": items_query.join(ProductionRound).filter(
                ProductionRound.is_active.is_(True),
                ProductionRound.stage.in_(["waiting"]),
                ItemOrderItem.item_status == "item"
            ),
            "sample": items_query.join(ProductionRound).filter(
                ProductionRound.is_active.is_(True),
                ProductionRound.stage.in_(["sample"]),
                ItemOrderItem.item_status == "item"
            ),
            "in_production": items_query.join(ProductionRound).filter(
                ProductionRound.is_active.is_(True),
                ProductionRound.stage.in_(["production", "examination"]),
                ItemOrderItem.item_status == "item"
            ),
            "delivered": items_query.filter(ItemOrderItem.item_status == "delivered"),
            "in_process": items_query.filter(ItemOrderItem.item_status == "in_process"),
            "refunded": items_query.filter(ItemOrderItem.item_status == "refunded"),
            "transferred": items_query.filter(ItemOrderItem.item_status == "transferred"),
        }

        items = category_filters.get(category)
        if items is None:
            flash("Invalid category selected.")
            return redirect(url_for('user_interface.customer_dashboard'))

        items = items.all()

        return render_template(
            f"user/customer/item_management/{category}.html",
            category=category,
            items=items
        )

    except Exception as e:
        logging.exception("Error in item_management route: %s", e)
        flash(f"An error occurred while managing items: {e}", "error")
        return redirect(url_for('user_interface.customer_dashboard'))


# item management
# waiting_for_delivery, first display all
# to form a delivery order, 

@user_interface.route('/waiting_for_delivery', methods=['GET'])
@customer_required
def waiting_for_delivery():

    # Fetch all in-stock items for the customer across all orders
    items = ItemOrderItem.query.join(ItemOrder).filter(
        ItemOrder.customer_id == current_user.id,
        ItemOrderItem.item_status == "in_stock"
    ).all()

    # Get unique regions with in-stock items
    region_ids = set(item.region_id for item in items) if items else set()
    regions = Region.query.filter(Region.id.in_(region_ids)).order_by(Region.name).all() if region_ids else []

    return render_template(
        'user/customer/item_management/waiting_for_delivery.html',
        items=items,
        regions=regions
    )



# after select a region, the items can be picked for delivery
@user_interface.route('/select_items_for_delivery', methods=['GET', 'POST'])
@customer_required
def select_items_for_delivery():

    if request.method == 'GET':
        region_id = request.args.get('region_id', type=int)
        if not region_id:
            flash("No region selected.", "error")
            return redirect(url_for('user_interface.waiting_for_delivery'))

        # Fetch in-stock items for the selected region, sorted by production_round_id
        items = ItemOrderItem.query.join(ItemOrder).filter(
            ItemOrder.customer_id == current_user.id,
            ItemOrderItem.item_status == "in_stock",
            ItemOrderItem.region_id == region_id
        ).order_by(ItemOrderItem.production_round_id).all()

        if not items:
            flash("No items available in the selected region.", "info")
            return redirect(url_for('user_interface.waiting_for_delivery'))

        return render_template(
            'user/customer/select_items_for_delivery.html',
            items=items,
            region_id=region_id
        )

    # POST: Submit to preview
    item_ids = request.form.getlist('item_ids')
    postal_code_prefix = request.form.get('postal_code_prefix', '')
    shipping_address = request.form.get('shipping_address')
    region_id = request.form.get('region_id', type=int)

    if not item_ids or not shipping_address or not region_id:
        flash("Please fill all required fields: items, shipping address, and region.", "error")
        return redirect(url_for('user_interface.select_items_for_delivery', region_id=region_id))

    # Store in session for preview
    session['preview_data'] = {
        'item_ids': item_ids,
        'postal_code_prefix': postal_code_prefix,
        'shipping_address': shipping_address,
        'region_id': region_id
    }
    return redirect(url_for('user_interface.preview_delivery_order'))



@user_interface.route('/preview_delivery_order', methods=['GET', 'POST'])
@customer_required
def preview_delivery_order():
    preview_data = session.get('preview_data')

    if not preview_data:
        flash("No items selected for preview.", "error")
        return redirect(url_for('user_interface.select_items_for_delivery'))

    item_ids = [uuid.UUID(id_str) for id_str in preview_data['item_ids']]
    postal_code_prefix = preview_data['postal_code_prefix']
    shipping_address = preview_data['shipping_address']
    region_id = preview_data['region_id']

    # Fetch selected items with relationships loaded
    items = ItemOrderItem.query.options(
        db.joinedload(ItemOrderItem.production_round).joinedload(ProductionRound.product).joinedload(Product.artwork)
    ).filter(
        ItemOrderItem.id.in_(item_ids),
        ItemOrderItem.item_status == "in_stock"
    ).all()

    if len(items) != len(item_ids):
        flash("Some selected items are invalid or unavailable.", "error")
        return redirect(url_for('user_interface.select_items_for_delivery', region_id=region_id))

    # Determine warehouse_id
    warehouse = WarehouseRegionMapping.query.filter_by(region_id=region_id).first()
    if not warehouse:
        flash("No warehouse mapped to this region.", "error")
        return redirect(url_for('user_interface.select_items_for_delivery', region_id=region_id))
    warehouse_id = warehouse.warehouse_id

    # Calculate total delivery points
    total_delivery_points = sum(
        ProductionRound.query.get(item.production_round_id).delivery_point for item in items
    )

    # Fetch cost grid with postal_code_prefix consideration
    if postal_code_prefix:
        cost_entry = DeliveryCostGrid.query.filter_by(
            warehouse_id=warehouse_id,
            region_id=region_id,
            postal_code_prefix=postal_code_prefix
        ).first()
    else:
        cost_entry = None

    # Fallback to NULL postal_code_prefix if no match or not provided
    if not cost_entry:
        cost_entry = DeliveryCostGrid.query.filter_by(
            warehouse_id=warehouse_id,
            region_id=region_id,
            postal_code_prefix=None
        ).first()

    if not cost_entry:
        flash("No delivery cost defined for this warehouse and region.", "error")
        return redirect(url_for('user_interface.select_items_for_delivery', region_id=region_id))

    # Calculate delivery cost
    base_cost = cost_entry.base_cost
    point_cost = cost_entry.per_delivery_point * total_delivery_points
    delivery_cost = base_cost + point_cost

    region = Region.query.get(region_id)
    tax = delivery_cost * region.delivery_tax_rate
    total_cost = delivery_cost + tax

    # Summarize items by product name, quantity, and image path
    item_summary = {}
    for item in items:
        product_name = item.product_name
        image_path = item.production_round.product.artwork.image_path if item.production_round.product and item.production_round.product.artwork else None
        if product_name not in item_summary:
            item_summary[product_name] = {'quantity': 0, 'image_path': image_path}
        item_summary[product_name]['quantity'] += 1

    if request.method == 'GET':
        return render_template(
            'user/customer/preview_delivery_order.html',
            item_summary=item_summary,
            delivery_cost=delivery_cost,
            tax=tax,
            total_cost=total_cost,
            shipping_address=shipping_address,
            postal_code_prefix=postal_code_prefix or 'N/A'
        )

    # POST: Create DeliveryOrder
    payment_method = request.form.get('payment_method')
    customer = current_user

    if payment_method != 'wallet':
        flash("Only wallet payment is supported for now.", "error")
        return redirect(url_for('user_interface.preview_delivery_order'))

    try:
        # Prepare delivery_item with explicit string conversion and validation
        delivery_items = []
        for item in items:
            item_id = str(item.id)  # Ensure item_id is a string
            production_round_id = str(item.production_round_id)  # Ensure production_round_id is a string
            if not isinstance(item_id, str) or not isinstance(production_round_id, str):
                raise ValueError(f"Invalid ID type for item {item.id}: item_id={item_id}, production_round_id={production_round_id}")
            delivery_items.append({"item_id": item_id, "production_round_id": production_round_id})

        delivery_order = DeliveryOrder(
            customer_id=customer.id,
            warehouse_id=warehouse_id,
            region_id=region_id,
            postal_code_prefix=postal_code_prefix if postal_code_prefix else None,
            shipping_address=shipping_address,
            delivery_cost=total_cost,
            status="created",
            delivery_item=delivery_items,
            payment_method='wallet',
            payment_status='unpaid'
        )
        db.session.add(delivery_order)

        # Update item statuses
        for item in items:
            item.item_status = "in_process"
            db.session.add(item)

        db.session.commit()
        session.pop('preview_data', None)
        return redirect(url_for('user_interface.delivery_order_wallet_payment', delivery_order_id=delivery_order.id))

    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error creating delivery order: {e}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('user_interface.preview_delivery_order'))





# order section, separate routes to view order and order details


# item order

@user_interface.route('/view_item_orders', methods=['GET'])
@customer_required
def view_item_orders():
    try:
        customer = current_user
        item_orders = ItemOrder.query.filter_by(customer_id=customer.id).order_by(ItemOrder.created_at.desc()).all()

        if not item_orders:
            logging.info("No orders found for Customer ID: %s", customer.id)
        else:
            logging.info("Retrieved %d orders for Customer ID: %s", len(item_orders), customer.id)

        return render_template('user/customer/view_item_orders.html', item_orders=item_orders)

    except Exception as e:
        flash(f"An error occurred while retrieving your orders: {e}", "error")
        return redirect(url_for('user_interface.customer_dashboard'))


@user_interface.route('/view_item_order_detail/<uuid6:order_id>', methods=['GET'])
@customer_required
def view_item_order_detail(order_id):

    customer = current_user

    item_order = ItemOrder.query.filter_by(id=order_id, customer_id=customer.id).first()

    if not item_order:
        flash("Order not found or you do not have permission to view it.")
        return redirect(url_for('user_interface.view_item_orders'))

    # Fetch the region object
    region = Region.query.get(item_order.region)
    if not region:
        logging.warning(f"Region ID {item_order.region} not found for order {order_id}")
        region_name = "Unknown Region"  # Fallback if region is missing
    else:
        region_name = region.name

    # Extract item details from `item_list` and fetch product details
    order_items = []
    for item in item_order.item_list:
        production_round = ProductionRound.query.get(uuid.UUID(item["production_round_id"]))
        if production_round and production_round.product:
            order_items.append({
                "production_round_id": item["production_round_id"],
                "quantity": item["quantity"],
                "product_name": production_round.product.name,
                "product_id": production_round.product.id,
            })

    return render_template(
        'user/customer/view_item_order_detail.html',
        item_order=item_order,
        order_items=order_items,
        region_name=region_name  # Pass region name to template
    )


# refund item order

@user_interface.route('/customer/view_refund_orders', methods=['GET'])
@customer_required
def view_refund_orders():
    """
    Displays a list of refund orders for the logged-in customer.
    """
    customer = current_user
    try:

        refund_orders = RefundItemOrder.query.filter_by(customer_id=customer.id).order_by(RefundItemOrder.created_at.desc()).all()

        if not refund_orders:
            logging.info("No refund orders found for Customer ID: %s", customer.id)
        else:
            logging.info("Retrieved %d refund orders for Customer ID: %s", len(refund_orders), customer.id)

        return render_template(
            'user/customer/view_refund_orders.html',
            refund_orders=refund_orders
        )

    except Exception as e:
        flash(f"An error occurred while retrieving your refund orders: {e}", "error")
        return redirect(url_for('user_interface.customer_dashboard'))  # Adjust as needed



@user_interface.route('/customer/view_refund_order_detail/<uuid6:refund_id>', methods=['GET'])
@customer_required
def view_refund_order_detail( refund_id):
    """
    Displays details of a specific refund order for the logged-in customer.
    """
    customer = current_user

    refund_order = RefundItemOrder.query.filter_by(id=refund_id, customer_id=customer.id).first()
    if not refund_order:
        flash("Refund order not found or you do not have permission to view it.")
        return redirect(url_for('user_interface.view_refund_orders'))

    return render_template(
        'user/customer/view_refund_order_detail.html',
        refund_order=refund_order
    )



# transfer item order (need update)

@user_interface.route('/view_transfer_orders', methods=['GET'])
@customer_required
def view_transfer_orders():

    customer = current_user

    orders = TransferItemOrder.query.filter_by(from_customer_id=customer.id).all()
    return render_template('user/orders/view_transfer_orders.html', orders=orders)




# delivery order (need update)


@user_interface.route('/view_delivery_orders', methods=['GET'])
@customer_required
def view_delivery_orders():
    """
    Display all delivery orders categorized by their status (created, in_process, delivering, received).
    """

    try:
        customer = current_user

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


# delete unpaid, put the item back

@user_interface.route('/delete_unpaid_delivery_order/<uuid6:order_id>', methods=['POST'])
@customer_required
def delete_unpaid_delivery_order(order_id):
    try:
        # Fetch the delivery order or return 404 if not found
        delivery_order = DeliveryOrder.query.get_or_404(order_id)

        # Check permissions and order state
        if delivery_order.customer_id != current_user.id:
            flash("You do not have permission to delete this order.", "danger")
            return redirect(url_for('user_interface.view_delivery_orders'))
        if delivery_order.status != 'created' or delivery_order.payment_status != 'unpaid':
            flash("Only unpaid orders in 'created' status can be deleted.", "danger")
            return redirect(url_for('user_interface.view_delivery_orders'))

        # Process each item in the delivery order (delivery_items is confirmed to be a list)
        for item in delivery_order.delivery_item:
            if not isinstance(item, dict):
                flash(f"Skipping invalid item format: {item}", "warning")
                continue

            # Extract item_id, handling string or legacy dictionary cases
            item_id_str = item.get('item_id')
            if isinstance(item_id_str, dict):
                # Legacy data fix: extract UUID from nested structure
                item_id_str = item_id_str.get('pk_1') or str(item_id_str)
            if not isinstance(item_id_str, str):
                flash(f"Skipping item with invalid ID: {item_id_str}", "warning")
                continue

            # Convert item_id string to UUID object
            try:
                item_id = uuid.UUID(item_id_str)
            except ValueError:
                flash(f"Invalid UUID format for item_id: {item_id_str}", "warning")
                continue

            # Query the ItemOrderItem and update status if applicable
            order_item = ItemOrderItem.query.get(item_id)
            if order_item:
                if order_item.item_status == 'in_process':
                    order_item.item_status = 'in_stock'
                else:
                    flash(
                        f"Item {item_id} is not in 'in_process' status. Current status: {order_item.item_status}",
                        "warning"
                    )
            else:
                flash(f"No item found for ID: {item_id}", "warning")

        # Delete the delivery order after processing items
        db.session.delete(delivery_order)
        db.session.commit()
        flash("Delivery order deleted successfully.", "success")
        return redirect(url_for('user_interface.view_delivery_orders'))

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting order: {str(e)}", "danger")
        return redirect(url_for('user_interface.view_delivery_orders'))
    



@user_interface.route('/delivery_order_detail/<uuid6:order_id>', methods=['GET'])
@customer_required
def view_delivery_order_detail(order_id):
    """
    View details of a delivery order including ordered items and delivery packages.
    This page is accessible to the customer who placed the order.
    """

    # Fetch the order and customer
    customer = current_user
    delivery_order = DeliveryOrder.query.get_or_404(order_id)

    # Ensure the logged-in user is the owner of this order
    if customer.id != delivery_order.customer_id:
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
@customer_required
def confirm_delivery_package(package_number):
    """
    Allows customers to confirm they have received a specific delivery package.
    If all packages for an order are confirmed, update the order status to 'received'
    and mark all associated ItemOrderItems as 'delivered'.
    """

    # Fetch the package
    customer = current_user
    package = DeliveryPackage.query.filter_by(package_number=package_number).first_or_404()

    # Ensure the package belongs to the logged-in customer
    if customer.id != package.delivery_order.customer_id:
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
@customer_required
def add_to_favorites(artwork_id):

    customer = current_user
    artwork = Artwork.query.get(artwork_id)

    if artwork not in customer.favorite_artworks:
        customer.favorite_artworks.append(artwork)
        db.session.commit()
        flash(f"'{artwork.title}' has been added to your favorites.")

     # Redirect back to the page the user was previously on
    return redirect(request.referrer)



@user_interface.route('/remove_from_favorites/<uuid6:artwork_id>', methods=['POST'])
@customer_required
def remove_from_favorites(artwork_id):

    customer = current_user
    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork in customer.favorite_artworks:
        customer.favorite_artworks.remove(artwork)
        db.session.commit()
        flash(f"'{artwork.title}' has been removed from your favorites.", 'success')

    return redirect(request.referrer or url_for('user_interface.customer_home'))




# follow and unfollow artists

@user_interface.route('/follow_artist/<uuid6:artist_id>', methods=['POST'])
@customer_required
def follow_artist(artist_id):

    customer = current_user
    artist = Artist.query.get(artist_id)

    if artist not in customer.followed_artists:
        customer.followed_artists.append(artist)
        db.session.commit()
        flash(f"You are now following '{artist.name}'.", 'success')

    return redirect(request.referrer or url_for('user_interface.customer_home'))



@user_interface.route('/unfollow_artist/<uuid6:artist_id>', methods=['POST'])
@customer_required
def unfollow_artist(artist_id):

    customer = current_user
    artist = Artist.query.get_or_404(artist_id)

    if artist in customer.followed_artists:
        customer.followed_artists.remove(artist)
        db.session.commit()
        flash(f"You have unfollowed '{artist.name}'.", 'success')

    return redirect(request.referrer or url_for('user_interface.customer_home'))


@user_interface.route('/signup_notification/<uuid6:product_id>', methods=['POST'])
@customer_required
def signup_notification(product_id):
    """Sign up a customer for product notifications if no waiting round exists."""
    product = Product.query.get_or_404(product_id)


    # Check if a waiting round already exists
    waiting_round = ProductionRound.query.filter_by(product_id=product_id, stage="waiting").first()
    if waiting_round:
        flash("A production round is already waiting for this product.")
        return redirect(url_for('user_interface.product_public', product_id=product_id))

    # Check if customer already signed up
    existing_signup = ProductNotificationSignup.query.filter_by(customer_id=current_user.id, product_id=product_id).first()
    if existing_signup:
        flash("You are already signed up for this product.")
        return redirect(url_for('user_interface.product_public', product_id=product_id))

    # Add signup
    signup = ProductNotificationSignup(id = uuid6(), customer_id=current_user.id, product_id=product_id)
    db.session.add(signup)
    db.session.commit()

     # Check threshold and notify
    product.check_and_notify_threshold()

    flash("Successfully signed up for notifications!")
    return redirect(url_for('user_interface.product_public', product_id=product_id))



# transaction section for customers, cart, checkout, view orders, view order details, add fund and sandbox payment


@user_interface.route('/add_to_cart/<uuid6:round_id>', methods=['POST'])
@customer_required
def add_to_cart(round_id):
    try:
        customer = current_user

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
@customer_required
def view_cart():
    try:
        # 2) Fetch Customer
        customer = current_user
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
@customer_required
def update_cart_quantity():
    try:

        # 2) Fetch Customer
        customer = current_user

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
@customer_required
def select_checkout_items():
    try:
        # 2) Fetch the customer
        customer = current_user
        if not customer:
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




# Checkout Route
@user_interface.route('/checkout', methods=['GET'])
@customer_required
def checkout():
    """Display checkout page with static subtotal and dynamic options."""

    # 2) Fetch customer

    customer = current_user
    if not customer:
        flash("Customer not found. Please log in again.", "error")
        return redirect(url_for('user_interface.login'))

    # 3) Get checkout items from session
    checkout_items = session.get('checkout_items', {})
    if not checkout_items:
        flash("No items in checkout.", "error")
        return redirect(url_for('user_interface.view_cart'))

    # 4) Calculate subtotal and prepare cart items
    cart_items = []
    subtotal = 0.0
    for prod_round_id_str, qty in checkout_items.items():
        try:
            production_round_id = uuid.UUID(prod_round_id_str)
            cart_item = CartItem.query.filter_by(
                cart_id=customer.cart.id,  # Use customer's cart ID
                production_round_id=production_round_id
            ).first()
            if cart_item and qty > 0:
                item_total = cart_item.unit_price * qty
                subtotal += item_total
                cart_items.append({
                    'name': cart_item.product_name,
                    'quantity': qty,
                    'unit_price': cart_item.unit_price,
                    'total_price': item_total,
                    'product_image_path': cart_item.product_image_path
                })
            else:
                logging.warning(f"Cart item not found or invalid quantity for production_round_id: {prod_round_id_str}")
        except Exception as e:
            logging.exception(f"Error processing checkout item {prod_round_id_str}: {e}")

    # 5) Validate subtotal
    subtotal = round(subtotal, 2)
    if not cart_items or subtotal <= 0:
        flash("Invalid cart subtotal or no valid items.", "error")
        session.pop('checkout_items', None)  # Clear invalid checkout items
        return redirect(url_for('user_interface.view_cart'))

    # 6) Store in session as single source of truth
    session['checkout_subtotal'] = subtotal
    session['checkout_cart_items'] = cart_items

    # 7) Fetch regions
    regions = Region.query.all()
    if not regions:
        flash("No delivery regions available.", "error")
        return redirect(url_for('user_interface.view_cart'))

    # 8) Render checkout page
    logging.debug(f"Checkout prepared: Subtotal={subtotal}, Items={len(cart_items)}")
    return render_template(
        'user/customer/checkout.html',
        cart_items=cart_items,
        subtotal=subtotal,
        regions=regions,
        selected_region=session.get('selected_region', regions[0].id),
        selected_payment_method=session.get('selected_payment_method', 'wallet')
    )



#API for dynamic tax calculation


# API Endpoints for Dynamic Calculations on tax and transaction fee
@user_interface.route('/calculate_tax', methods=['POST'])
def calculate_tax():
    data = request.get_json()
    subtotal = session.get('checkout_subtotal', 0)  # Use session subtotal
    region_id = int(data.get('region', 1))
    region = Region.query.get(region_id)
    tax = round(subtotal * region.tax_rate, 2) if region else 0
    return jsonify({'tax': tax})

@user_interface.route('/calculate_transaction_fee', methods=['POST'])
def calculate_transaction_fee():
    data = request.get_json()
    subtotal = session.get('checkout_subtotal', 0)  # Use session subtotal
    payment_method = data.get('payment_method', 'wallet')
    fee = 1.20 if payment_method == 'wallet' else round(subtotal * 0.03, 2)
    return jsonify({'transaction_fee': fee})
    

# Confirm Checkout Route



@user_interface.route('/confirm_checkout', methods=['POST'])
@customer_required
def confirm_checkout():
    """Create an unpaid order and redirect to the appropriate payment page."""

    # 2) Retrieve session data
    subtotal = session.get('checkout_subtotal')
    checkout_items = session.get('checkout_items')
    cart_items = session.get('checkout_cart_items')
    if not subtotal or not checkout_items or not cart_items:
        flash("Checkout data missing. Please start over.", "error")
        logging.error("Checkout session data missing")
        return redirect(url_for('user_interface.view_cart'))

    # 3) Get form selections
    region_id = request.form.get('region')
    payment_method = request.form.get('payment_method')
    if not region_id or not payment_method:
        flash("Please select a region and payment method.", "error")
        logging.error(f"Form data incomplete: region_id={region_id}, payment_method={payment_method}")
        return redirect(url_for('user_interface.checkout'))

    # 4) Calculate tax and fees
    region = Region.query.get(int(region_id))
    if not region:
        flash("Invalid region selected.", "error")
        logging.error(f"Region not found: {region_id}")
        return redirect(url_for('user_interface.checkout'))
    
    tax = round(subtotal * region.tax_rate, 2)
    transaction_fee = 1.20 if payment_method == 'wallet' else round(subtotal * 0.03, 2) #need update for new payment methods
    total_amount = round(subtotal + tax + transaction_fee, 2)

    # 5) Fetch the customer
    try:
        customer = current_user
        logging.debug(f"Customer queried: {customer}")
        if not customer:
            flash("Customer not found.", "error")
            return redirect(url_for('user_interface.home'))
    except ValueError as e:
        logging.exception(f"Invalid customer_id in session: {session['customer.id']}")
        flash("Invalid customer session. Please log in again.", "error")
        return redirect(url_for('user_interface.login'))

    # 6) Prepare item_list (JSON-compatible)
    item_list = [
        {'production_round_id': prod_round_id, 'quantity': qty}
        for prod_round_id, qty in checkout_items.items()
    ]

    # 7) Create unpaid order and clear cart items
    item_order = ItemOrder(
        customer_id=customer.id,
        payment_status='unpaid',
        total_amount=total_amount,
        region=int(region_id),
        payment_method=payment_method,
        item_list=item_list,
        tax_amount = tax,
        transaction_fee = transaction_fee # prepare for RegionFinancialSummary
    )

    try:
        # Add the order to the session
        db.session.add(item_order)

        # Clear corresponding CartItem entries
        cart_id = customer.cart.id  # Access customer's cart ID
        for prod_round_id_str in checkout_items.keys():
            prod_round_id = uuid.UUID(prod_round_id_str)
            cart_item = CartItem.query.filter_by(cart_id=cart_id, production_round_id=prod_round_id).first()
            if cart_item:
                db.session.delete(cart_item)
                logging.debug(f"Deleted CartItem: cart_id={cart_id}, production_round_id={prod_round_id}")
            else:
                logging.warning(f"CartItem not found for cart_id={cart_id}, production_round_id={prod_round_id}")

        # Commit the transaction (order creation + cart item deletion)
        db.session.commit()
        logging.debug(f"ItemOrder created: {item_order}")

    except Exception as e:
        db.session.rollback()
        logging.exception(f"Failed to create ItemOrder or clear cart items: {e}")
        flash("An error occurred during order creation.", "error")
        return redirect(url_for('user_interface.checkout'))

    # 8) Clear session data
    session.pop('checkout_subtotal', None)
    session.pop('checkout_cart_items', None)
    session.pop('checkout_items', None)

    # 9) Redirect to payment page based on payment_method
    logging.debug(f"Order created: ID={item_order.id}, Payment Method={payment_method}, Total={total_amount}")
    if payment_method == 'wallet':
        return redirect(url_for('user_interface.item_order_process_wallet_payment', order_id=item_order.id))
    elif payment_method == 'credit_card':
        flash("Credit card payment is not yet supported.", "error")
        return redirect(url_for('user_interface.checkout'))
    elif payment_method == 'paypal':
        flash("PayPal payment is not yet supported.", "error")
        return redirect(url_for('user_interface.checkout'))
    else:
        flash("Invalid payment method selected.", "error")
        return redirect(url_for('user_interface.checkout'))








# right now the creation of item order is put on the confirm checkout
# the payment for order/unpaid order is integrated


@user_interface.route('/item_order_process_wallet_payment/<uuid6:order_id>', methods=['GET', 'POST'])
@customer_required
def item_order_process_wallet_payment(order_id):
    """Handles wallet payment processing for both new and unpaid orders."""
    try:
        logging.debug("Entered /process_wallet_payment route")
        customer = current_user

        # Fetch the order and validate it
        item_order = ItemOrder.query.filter_by(id=order_id, customer_id=customer.id).first()

        if not item_order:
            flash("Order not found.")
            return redirect(url_for('user_interface.home'))

        # Ensure only unpaid orders can proceed
        if item_order.payment_status != 'unpaid':
            flash("This order has already been processed.", "error")
            return redirect(url_for('user_interface.home'))

        region = item_order.region

        # Check wallet balance before payment
        if customer.wallet_balance < item_order.total_amount:
            error_message = "Insufficient wallet balance. Please add funds or use a different payment method."
            return redirect(url_for(
                'user_interface.item_order_payment_status',
                order_id=item_order.id,
                message=error_message
            ))

        # Handle POST: Perform wallet payment
        if request.method == 'POST':
            try:
                # Validate production round statuses
                item_order.validate_production_round_status()

                # Deduct wallet balance
                customer.wallet_balance -= item_order.total_amount
                if customer.wallet_balance < 0:
                    raise ValueError("Wallet balance cannot go negative")

                # Mark order as paid
                item_order.mark_as_paid(payment_method="wallet", region=region)

                # Add objects to session
                db.session.add(customer)
                db.session.add(item_order)

                # Update related data
                item_order.update_production_round_totals()
                item_order.register_customer_for_notifications()

                # Commit transaction
                db.session.commit()


                flash("Payment successful!", "success")
                return redirect(url_for('user_interface.item_order_payment_status', order_id=item_order.id))

            except Exception as e:
                db.session.rollback()
                logging.exception(f"Transaction failed for order {order_id}: {e}")
                flash(f"Payment failed: {e}", "error")
                return redirect(url_for('user_interface.item_order_payment_status', order_id=order_id))

        # GET request: Render the payment page
        return render_template(
            'user/customer/item_order_wallet_payment.html',
            item_order=item_order,
            wallet_balance=customer.wallet_balance
        )

    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error in /process_wallet_payment route: {e}")
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('user_interface.view_item_orders'))
    







@user_interface.route('/item_order_payment_status/<uuid6:order_id>', methods=['GET'])
@customer_required
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



# proceed the unpaid item order: add the items to cart


@user_interface.route('/add_order_to_cart/<uuid:order_id>', methods=['POST'])
@customer_required
def add_order_to_cart(order_id):
    # Fetch the order and verify it’s unpaid and belongs to the customer
    order = ItemOrder.query.get_or_404(order_id)
    customer = current_user

    if order.customer_id != customer.id:
        flash("You can only modify your own orders.", "danger")
        return redirect(url_for('user_interface.view_item_orders'))
    if order.payment_status != 'unpaid':
        flash("This order is not eligible for adding back to cart.", "danger")
        return _render_order_detail(order, customer_id=customer.id)

    try:
        # Parse the item_list JSON
        item_list = order.item_list
        if not isinstance(item_list, list):
            raise ValueError("Invalid item_list format in order.")

        # Ensure the customer has a cart
        cart = customer.cart
        if not cart:
            cart = Cart(customer_id=customer.id)
            db.session.add(cart)
            db.session.flush()  # Ensure cart.id is available

        # Process each item in the item_list
        for item in item_list:
            production_round_id = item.get('production_round_id')
            quantity = item.get('quantity', 1)

            # Validate item data
            if not production_round_id or not isinstance(quantity, int) or quantity < 1:
                flash(f"Skipping invalid item: {item}", "warning")
                continue

            # Fetch the ProductionRound
            production_round = ProductionRound.query.get(uuid.UUID(production_round_id))
            if not production_round:
                flash(f"Production round {production_round_id} not found.", "warning")
                continue

            # Use Cart.add_item_to_cart to add or update the item
            cart.add_item_to_cart(production_round, quantity)

        # Delete the unpaid order after successful processing
        db.session.delete(order)
        db.session.commit()
        flash("Items added back to cart successfully!", "success")
        return redirect(url_for('user_interface.view_cart'))  # Updated redirect

    except Exception as e:
        db.session.rollback()
        flash(f"Error adding items to cart: {str(e)}", "danger")
        return _render_order_detail(order, customer.id)

def _render_order_detail(order, customer_id):
    """Helper function to re-render the order detail page with current data."""
    region = Region.query.get(order.region)
    region_name = region.name if region else "Unknown Region"

    order_items = []
    for item in order.item_list:
        production_round = ProductionRound.query.get(uuid.UUID(item["production_round_id"]))
        if production_round and production_round.product:
            order_items.append({
                "production_round_id": item["production_round_id"],
                "quantity": item["quantity"],
                "product_name": production_round.product.name,
                "product_id": production_round.product.id,
            })

    return render_template(
        'user/customer/view_item_order_detail.html',
        item_order=order,
        order_items=order_items,
        region_name=region_name
    )




@user_interface.route('/pay_with_sandbox', methods=['GET', 'POST'])
def pay_with_sandbox():
    # Implement mock or sandbox payment
    pass



# test for refund and transfer

# auto refund, full (in waiting) and partial (sampling, before production)


@user_interface.route('/customer/auto_refund_item/<uuid6:item_id>', methods=['GET'])
@customer_required
def auto_refund_item(item_id):
    """
    Displays refund details for a specific item before processing.
    """

    try:
        customer =  current_user
        if not customer:
            flash("Customer not found.")
            return redirect(url_for('user_interface.login'))

        # Fetch item with production round
        item = ItemOrderItem.query.options(
            joinedload(ItemOrderItem.production_round)
        ).get(item_id)
        if not item or item.item_order.customer_id != customer.id:
            flash("Invalid item selected for refund.")
            return redirect(url_for('user_interface.customer_dashboard'))

        # Check refund eligibility
        if item.item_status != "item":
            flash("This item is not eligible for a refund due to its current status.")
            return redirect(url_for('user_interface.customer_dashboard'))

        production_round = item.production_round
        if not production_round:
            flash("Production round data is missing.")
            return redirect(url_for('user_interface.customer_dashboard'))

        # Determine base refund amount
        if production_round.stage == "waiting":
            base_refund_amount = item.unit_price
            refund_type = "Full Refund"
        elif production_round.stage == "sample" and production_round.partial_refund is not None:
            base_refund_amount = production_round.partial_refund
            refund_type = "Partial Refund"
        else:
            flash("This item is not eligible for a refund.")
            return redirect(url_for('user_interface.customer_dashboard'))

        # Calculate total refund with tax using region relationship
        region = item.region
        if not region or region.tax_rate is None:
            logging.warning(f"No valid region or tax rate for item {item_id}. Using base amount: {base_refund_amount}")
            total_refund_amount = base_refund_amount
            region_name = "Unknown Region"
        else:
            tax_rate = region.tax_rate
            total_refund_amount = base_refund_amount * (1 + tax_rate)  # Base + tax
            region_name = region.name

        # Fetch product and artwork
        product = Product.query.get(production_round.product_id)
        artwork = Artwork.query.get(product.artwork_id) if product else None
        if not product or not artwork:
            flash("Product or artwork details not found.")
            return redirect(url_for('user_interface.customer_dashboard'))

        return render_template(
            'user/customer/auto_refund_item.html',
            item=item,
            refund_amount=total_refund_amount,
            refund_type=refund_type,
            product=product,
            artwork=artwork,
            region_name=region_name
        )

    except Exception as e:
        logging.exception(f"Error in auto_refund_item route: {e}")
        flash("An error occurred while loading the refund page.", "error")
        return redirect(url_for('user_interface.customer_dashboard'))


@user_interface.route('/customer/process_auto_refund_wallet', methods=['POST'])
@customer_required
def process_auto_refund_wallet():
    """
    Processes a wallet refund for an ItemOrderItem.
    """

    try:
        customer = current_user

        item_id = uuid.UUID(request.form.get('item_id'))
        refund_reason = request.form.get('refund_reason', "No reason provided")

        # Fetch and validate item
        item = ItemOrderItem.query.get(item_id)
        if not item or item.item_order.customer_id != customer.id:
            flash("Invalid item selected for refund.")
            return redirect(url_for('user_interface.customer_dashboard'))

        # Check refund eligibility
        if item.item_status != "item":
            flash("This item is already refunded or not eligible.")
            return redirect(url_for('user_interface.customer_dashboard'))

        production_round = item.production_round
        if not production_round:
            flash("Production round data is missing.")
            return redirect(url_for('user_interface.customer_dashboard'))

        # Determine base refund amount
        if production_round.stage == "waiting":
            base_refund_amount = item.unit_price
            refund_type = "auto-full-refund"
        elif production_round.stage == "sample" and production_round.partial_refund is not None:
            base_refund_amount = production_round.partial_refund
            refund_type = "auto-partial-refund"
        else:
            flash("This item is not eligible for a refund.")
            return redirect(url_for('user_interface.customer_dashboard'))

        # Calculate total refund with tax using region relationship
        region = item.region
        if not region or region.tax_rate is None:
            logging.warning(f"No valid region or tax rate for item {item_id}. Using base amount: {base_refund_amount}")
            total_refund_amount = base_refund_amount
        else:
            tax_rate = region.tax_rate
            total_refund_amount = base_refund_amount * (1 + tax_rate)  # Base + tax

        # Create refund record
        refund_order = RefundItemOrder(
            customer_id=customer.id,
            item_order_item_id=item.id,
            is_auto=True,
            reason=str(refund_type,refund_reason),
            refund_method="wallet",
            refund_status="processed",
            refund_amount=total_refund_amount,
            refund_timestamp=datetime.now()
        )
        db.session.add(refund_order)

        # Update item status
        item.item_status = "refunded"
        db.session.add(item)

        # Update wallet balance
        old_balance = customer.wallet_balance
        customer.wallet_balance += total_refund_amount
        logging.info(f"Refunded {total_refund_amount} to customer {customer.id}. Wallet: {old_balance} -> {customer.wallet_balance}")
        db.session.add(customer)

        # Update production round
        production_round.decrement_order_count(customer.id)

        # Notify customer
        Notification.send_notification(
            user_id=customer.id,
            message=f"Your refund of ${total_refund_amount:.2f} for {production_round.product.name} has been processed to your wallet.",
            type="refund"
        )

        db.session.commit()
        flash(f"Refund processed successfully. ${total_refund_amount:.2f} has been added to your wallet.", "success")
        return redirect(url_for('user_interface.customer_dashboard'))

    except ValueError as ve:
        db.session.rollback()
        logging.error(f"Invalid data in process_auto_refund_wallet: {ve}")
        flash("Invalid refund request data.", "error")
        return redirect(url_for('user_interface.customer_dashboard'))
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error in process_auto_refund_wallet: {e}")
        flash("An error occurred while processing the refund.", "error")
        return redirect(url_for('user_interface.customer_dashboard'))

        

@user_interface.route('/mock_transfer_item/<uuid6:item_id>', methods=['GET'])
def mock_transfer_item(item_id):
    # Simulate transfer processing
    return f"Mock Transfer: ItemOrderItem with ID {item_id} has been processed for transfer."



# preview delivery order


# delivery order payment (wallet)


@user_interface.route('/delivery_order_wallet_payment/<uuid6:delivery_order_id>', methods=['GET', 'POST'])
@customer_required
def delivery_order_wallet_payment(delivery_order_id):
    """
    Handles the wallet payment for a newly created, unpaid DeliveryOrder.
    """
    try:
        logging.debug("Entered /delivery_order_wallet_payment route")
        customer = current_user

        # 2) Fetch the DeliveryOrder

        delivery_order = DeliveryOrder.query.filter_by(
            id=delivery_order_id,
            customer_id=customer.id
        ).first()

        if not delivery_order:
            flash("Delivery order not found.", "danger")
            return redirect(url_for('user_interface.preview_delivery_order'))

        if delivery_order.payment_status != 'unpaid':
            flash("This order has already been paid or is invalid for payment.", "info")
            return redirect(url_for('user_interface.delivery_order_payment_status',
                                    delivery_order_id=delivery_order.id))


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
@customer_required
def delivery_order_payment_status(delivery_order_id):
    """
    Shows the payment status (paid/unpaid) of the DeliveryOrder.
    """
    try:
        logging.debug(f"Accessed delivery_order_payment_status with order ID: {delivery_order_id}")

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
@artist_required
def artist_dashboard():
    # current_user is already authenticated and an artist due to the decorator
    unread_notifications_count = Notification.get_unread_notifications_count(current_user.id)
    
    # Retrieve the latest five artworks with the most recent changes in status
    recent_artworks = Artwork.query.filter_by(artist_id=current_user.id).order_by(Artwork.updated_at.desc()).limit(5).all()
    
    # Using the relationship to get products associated with each artwork
    recent_artworks_with_products = [
        {"artwork": artwork, "products": artwork.products} for artwork in recent_artworks
    ]
    
    return render_template(
        'user/artist/artist_dashboard.html',
        artist=current_user,
        wallet_balance=current_user.wallet_balance,
        recent_artworks=recent_artworks_with_products,
        unread_notifications_count=unread_notifications_count
    )


@user_interface.route('/edit_artist_bio', methods=['GET', 'POST'])
@artist_required
def edit_artist_bio():
    # No need to check if current_user exists; @artist_required ensures authentication and role
    artist = current_user  # current_user is the Artist object due to polymorphic loading

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
            return render_template('user/artist/edit_artist_bio.html', artist=artist)

    # Render the form for editing the bio (GET request)
    return render_template('user/artist/edit_artist_bio.html', artist=artist)




# artwork

@user_interface.route('/submit_new_artwork', methods=['GET', 'POST'])
@artist_required
def submit_new_artwork():

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        manufacturing_specs = request.form['manufacturing_specs']
        original_hard_tags = request.form['hard_tags'].strip()
        soft_tags = request.form.get('soft_tags', "").strip()

        # Validate hard tags
        if not original_hard_tags or original_hard_tags == '#' or all(not tag.strip() for tag in original_hard_tags.split('#')):
            flash("Hard tags are required and must contain meaningful tags separated by #.")
            return redirect(request.url)

        # Handle file upload (simplified for brevity)
        file = request.files['image']
        if not file or not file.filename:
            flash("An image file is required.")
            return redirect(request.url)
        filename = secure_filename(file.filename)
        image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        file.save(image_path)
        image_path = f'uploads/{filename}'

        # Normalize tags for tag_approvals
        tags = [Artwork.normalize_tag(tag) for tag in original_hard_tags.split('#') if tag.strip()]

        # Create artwork with original hard_tags and normalized tag_approvals
        artwork = Artwork(
            title=title,
            description=description,
            image_path=image_path,
            manufacturing_specs=manufacturing_specs,
            hard_tags=original_hard_tags,  # Keep original casing
            soft_tags=soft_tags,
            approval_status='Pending',
            artist_id=current_user.id
        )
        artwork.tag_approvals = {tag: 'Pending' for tag in tags}

        try:
            db.session.add(artwork)
            db.session.commit()
            flash("Artwork submitted successfully for approval.")
            return redirect(url_for('user_interface.artwork_upload_success'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error submitting artwork: {str(e)}")
            return redirect(request.url)

    return render_template('user/artist/submit_artwork.html', artist=current_user)
    



@user_interface.route('/artwork_upload_success', methods=['GET'])
@artist_required
def artwork_upload_success():

    # Retrieve the artist's name for display
    artist = current_user

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user_interface.login'))

    return render_template('user/artist/artwork_upload_success.html', artist=artist)


@user_interface.route('/all_artworks', methods=['GET'])
@artist_required
def all_artworks():

    artist = current_user

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user_interface.login'))

    # Retrieve all artworks created by the artist
    all_artworks = Artwork.query.filter_by(artist_id=artist.id).order_by(Artwork.updated_at.desc()).all()

    return render_template('user/artist/all_artworks.html', artist=artist, artworks=all_artworks)





@user_interface.route('/artist_search_artworks', methods=['GET'])
@artist_required
def artist_search_artworks():

    query = request.args.get('query')
    if not query:
        flash("Please enter a search query.")
        return redirect(url_for('user_interface.all_artworks'))


    # Prepare search term
    search_term = f"%{query}%"

    # Search artworks with product details
    artworks = (
        Artwork.query
        .outerjoin(Product, Artwork.id == Product.artwork_id)  # Join with Product
        .filter(
            Artwork.artist_id == current_user.id,  # Limit to artist's artworks
            (
                Artwork.title.ilike(search_term) |
                Artwork.description.ilike(search_term) |
                Artwork.hard_tags.ilike(search_term) |
                Artwork.soft_tags.ilike(search_term) |
                Product.name.ilike(search_term) |
                Product.production_specs.ilike(search_term)
            )
        )
        .options(joinedload(Artwork.products))  # Eager load products
        .distinct(Artwork.id)  # Avoid duplicates
        .all()
    )

    return render_template(
        'user/artist/artist_search_results.html',
        artist=current_user,
        artworks=artworks,
        query=query
    )


# artwork update request


@user_interface.route('/update_artwork/<uuid:artwork_id>', methods=['GET', 'POST'])  # Adjusted uuid6 to uuid
@artist_required
def update_artwork(artwork_id):
    artwork = Artwork.query.get_or_404(artwork_id)
    
    if artwork.artist_id != current_user.id:
        flash("You do not have permission to update this artwork.")
        return redirect(url_for('user_interface.artist_dashboard'))

    if request.method == 'POST':
        proposed_title = request.form.get('title', None)
        proposed_description = request.form.get('description', None)
        proposed_hard_tags = request.form.get('hard_tags', None)
        proposed_soft_tags = request.form.get('soft_tags', None)
        proposed_manufacturing_specs = request.form.get('manufacturing_specs', None)

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

        update_artwork_timestamp(artwork, commit=False)  #update the update time of artwork

        # Initialize tag_approvals for proposed_hard_tags
        if proposed_hard_tags:
            tags = [tag.strip().lower() for tag in proposed_hard_tags.split('#') if tag.strip()]
            new_update.tag_approvals = {tag: "Pending" for tag in tags}

        try:
            db.session.add(new_update)
            db.session.commit()
            flash("Your artwork update request has been submitted for review.")
            return redirect(url_for('user_interface.artist_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error submitting update: {str(e)}", "error")
            return redirect(request.url)

    return render_template('user/artist/update_artwork.html', artwork=artwork)




# product

@user_interface.route('/artist_product_management/<uuid6:product_id>', methods=['GET'])
@artist_required
def artist_product_management(product_id):

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
@artist_required
def toggle_display_status(product_id):

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
@artist_required
def view_artwork_disapproval_reason(artwork_id):

    # Retrieve the artwork directly using the artwork_id passed by the route

    artwork = Artwork.query.get(artwork_id)

    # If artwork not found or the current user is not authorized to view it, flash an error
    if not artwork or artwork.artist_id != current_user.id:
        flash("You are not authorized to view this disapproval reason.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Ensure the artwork has been disapproved before allowing access to disapproval reason
    if artwork.approval_status != 'Disapproved':
        flash("This artwork has not been disapproved.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Render the disapproval reason page with the artwork details
    return render_template('user/artist/view_artwork_disapproval_reason.html', artwork=artwork)



@user_interface.route('/view_product_disapproval_reason/<uuid6:product_id>', methods=['GET'])
@artist_required
def view_product_disapproval_reason(product_id):

    # Retrieve the product directly using the product_id passed by the route
    product = Product.query.get_or_404(product_id)

    # Ensure the product belongs to the current artist via the associated artwork
    if product.artwork.artist_id != current_user.id:
        flash("You are not authorized to view this disapproval reason.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Ensure the product has been disapproved before allowing access to disapproval reason
    if product.production_status != 'Disapproved':
        flash("This product has not been disapproved.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Render the disapproval reason template with the product details
    return render_template('user/artist/view_product_disapproval_reason.html', product=product)



@user_interface.route('/submit_product/<uuid6:artwork_id>', methods=['GET', 'POST'])
@artist_required
def submit_product(artwork_id):
    # Get the artwork using the provided artwork_id
    artwork = Artwork.query.get(artwork_id)

    # Ensure that the artwork belongs to the logged-in artist
    if not artwork or artwork.artist_id != current_user.id:
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
                artist_id=artwork.artist_id,
                production_status='Pending'
            )

            update_artwork_timestamp(artwork, commit=False)   #update the update time of artwork

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
            print(f"Error: {e}")  # For debugging purposes
            return render_template(
                'user/artist/product_submission_status.html',
                success=False,
                redirect_url=url_for('user_interface.artist_dashboard')
            )

    return render_template('user/artist/submit_product.html', artwork=artwork)




# artist choose who would be in control of starting the production round for a product

@user_interface.route('/manage_production_initialization/<uuid6:product_id>', methods=['GET', 'POST'])
@artist_required
def manage_production_initialization(product_id):
    """Manage the initialization control of production rounds for a product."""

    try:
        product = Product.query.get_or_404(product_id)
        if product.artist_id != current_user.id:
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
@artist_required
def artist_initialize_production_round(product_id):
    """Route for the artist to initialize a production round."""

    product = Product.query.get_or_404(product_id)
    if product.artist_id != current_user.id:
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

    artwork = Artwork.query.get(product.artwork_id)
    update_artwork_timestamp(artwork, commit=False)

    db.session.add(new_round)
    db.session.commit()


    # Send a notification to the assigned admin
    admin = ProductionRoundAdmin.query.get(product.assigned_admin_id)
    if not admin:  # Rare case: admin ID exists but no matching record
        flash("Assigned admin not found; notification not sent.", "warning")
    else:
        try:
            Notification.send_notification(
                user_id=admin.id,
                message=f"A new production round for '{product.name}' has been initialized by the artist.",
                type="production_round"
            )
        except Exception as e:
            flash(f"Notification failed: {str(e)}", "error")

    flash("Production round initialized and the admin has been notified.")
    return redirect(url_for('user_interface.artist_product_management', product_id=product_id))




@user_interface.route('/download_file/<uuid6:file_id>')
@artist_required
def download_file(file_id):

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
@artist_required
def artist_active_product_dialog(product_id):
    """Dialog for the current active production round for the artist."""

    # Fetch the active production round
    production_round = ProductionRound.query.filter_by(product_id=product_id, is_active=True).first()
    if not production_round:
        flash("No active production round found for this product.")
        return redirect(url_for('user_interface.artist_dashboard'))

    # Check if the artist is authorized
    if production_round.artist_id != current_user.id:
        flash("Unauthorized access to this dialog.")
        return redirect(url_for('user_interface.artist_dashboard'))

    if request.method == 'POST':
        message = request.form.get('message')
        uploaded_files = request.files.getlist('files')

        # Create and save a new message
        new_message = Dialog(
            production_round_id=production_round.id,
            sender_id=current_user.id,
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
            type='dialog'
        )
        artwork = Artwork.query.get(production_round.product.artwork_id)
        update_artwork_timestamp(artwork, commit=True)

    # Fetch all messages in this dialog
    messages = Dialog.query.filter_by(production_round_id=production_round.id).order_by(Dialog.timestamp).all()

    return render_template('user/artist/product_dialog.html', production_round=production_round, messages=messages)



# archieved information section for inactive production round (information and dialog)


# archived information for a production round: information and dialog

@user_interface.route('/archived_production_rounds/<uuid6:product_id>', methods=['GET'])
@artist_required
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
@artist_required
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
@artist_required
def archived_production_round_details(user_id, round_id):
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
@user_role_required
def view_notifications():
    unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.timestamp.desc()).all()
    current_user_role = current_user.role  # This is already correct

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

    return render_template(
        'user/account/unread_notifications.html',
        categorized_notifications=categorized_notifications,
        current_user_role=current_user_role
    )


@user_interface.route('/mark_notification_read/<uuid6:notification_id>', methods=['POST'])
@user_role_required
def mark_notification_read(notification_id):

    try:
        # Find the notification by ID
        notification = Notification.query.get(notification_id)

        # Ensure the notification belongs to the logged-in user
        if notification.user_id != current_user.id:
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
@user_role_required
def view_read_notifications():

    # Calculate the date 6 months ago
    six_months_ago = datetime.now(timezone.utc) - relativedelta(months=6)

    # Delete read notifications older than 6 months
    Notification.query.filter(
        Notification.user_id == current_user.id,
        Notification.is_read == True,
        Notification.timestamp < six_months_ago
    ).delete()
    db.session.commit()

    # Query remaining read notifications
    read_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=True
    ).order_by(Notification.timestamp.desc()).all()

    # Categorize notifications
    categorized_notifications = {}
    for notification in read_notifications:
        if notification.type not in categorized_notifications:
            categorized_notifications[notification.type] = []
        categorized_notifications[notification.type].append(notification)

    has_read_notifications = bool(read_notifications)

    return render_template('user/account/read_notifications.html', categorized_notifications=categorized_notifications, has_read_notifications=has_read_notifications)




@user_interface.route('/delete_all_read_notifications', methods=['POST'])
@user_role_required
def delete_all_read_notifications():

    # Delete all read notifications for the user
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=True
    ).delete()
    db.session.commit()

    flash("All read notifications have been deleted.")
    return redirect(url_for('user_interface.view_read_notifications'))


# customer service, needs implementation!

# customer service for item order

# customer service for delivery order


@user_interface.route('/customer_service/delivery_created/<uuid6:delivery_order_id>', methods=['GET', 'POST'])
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


@user_interface.route('/customer_service/delivery_delivered/<uuid6:delivery_order_id>', methods=['GET', 'POST'])
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
