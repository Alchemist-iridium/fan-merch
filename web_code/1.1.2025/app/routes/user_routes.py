from flask import request, Blueprint,current_app, render_template, render_template_string, redirect, url_for, session, flash, current_app, send_file, jsonify
from datetime import datetime, timezone, timedelta
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
import re

user_interface = Blueprint('user', __name__)

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
            return redirect(url_for('user.signup'))

        # Check if the artist name is unique if the role is 'artist'
        if role == 'artist' and Artist.query.filter_by(name=name).first():
            flash('Error: Artist name already taken. Please choose a different name.', 'error')
            return redirect(url_for('user.signup'))

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
                return redirect(url_for('user.signup'))

            with current_app.app_context():
                db.session.add(new_user)
                db.session.commit()

            flash('Signup successful! Welcome, {}.'.format(name), 'success')
            return redirect(url_for('user.signup_success', name=name, role=role))

        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('user.signup'))

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
                return redirect(url_for('user.artist_dashboard'))
            elif user.role == 'customer':
                return redirect(url_for('user.customer_home'))
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
    return redirect(url_for('user.home'))


# after login, the customer will be redirected to the customer_home page
@user_interface.route('/customer_home', methods=['GET', 'POST'])
def customer_home():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to access the home page.")
        return redirect(url_for('user.login'))

    try:
        # Convert the user_id from session to UUID before querying
        user_uuid = uuid.UUID(session['user_id'])
        customer = Customer.query.get(user_uuid)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user.login'))

    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user.login'))

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
@user_interface.route('/artist/<uuid:artist_id>')
def artist_public_page(artist_id):
    # Fetch the artist using the provided artist_id
    artist = Artist.query.get_or_404(artist_id)

    # Fetch all approved artworks for the artist
    artworks = Artwork.query.filter_by(artist_id=artist.id, approval_status='Approved').all()

    # Fetch only products that are approved and marked for display
    products = Product.query.filter(
        Product.artwork_id.in_([artwork.id for artwork in artworks]),
        Product.production_status == 'Approved',
        Product.display_status == 'on display'
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


@user_interface.route('/artwork/<uuid:artwork_id>')
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
            display_status='on display'
        ).all()

    # Render the artwork page, passing all necessary data
    return render_template(
        'user/public_search/artwork_page.html',
        work=artwork,
        approved_products=approved_products,
        customer=customer
    )



@user_interface.route('/product_public/<uuid:product_id>')
def product_public(product_id):
    """Display the public product page with details about production round and stage goals."""
    product = Product.query.get(product_id)
    if product and product.production_status == 'Approved' and product.display_status == 'on display':
        # Fetch the published production round
        production_round = (
            ProductionRound.query.filter_by(product_id=product_id, is_published=True)
            .order_by(ProductionRound.created_at.desc())
            .first()
        )

        # Extract stage goals from production_goals JSON if there is a production round
        stage_goals = production_round.stage_goals if production_round else []

        return render_template(
            'user/public_search/product_public.html',
            product=product,
            production_round=production_round,
            stage_goals=stage_goals,
        )
    
    flash("This product is not available for public viewing.")
    return redirect(url_for('user.home'))



# Customer Dashboard: View Orders, Favorite Artworks, Followed Artists, Wallet Balance

@user_interface.route('/customer_dashboard')
def customer_dashboard():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to access the dashboard.")
        return redirect(url_for('user.customer_home'))

    try:
        # Convert the user_id from session to UUID before querying
        user_uuid = uuid.UUID(session['user_id'])
        customer = Customer.query.get(user_uuid)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user.login'))

    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user.login'))

    # Fetch customer's orders, favorite artworks, followed artists, and wallet balance
    orders = customer.orders  # Assuming a relationship `orders` exists on the Customer model
    favorite_artworks = customer.favorite_artworks  # Assuming a relationship `favorite_artworks` exists
    followed_artists = customer.followed_artists  # Assuming a relationship `followed_artists` exists
    wallet_balance = customer.wallet.balance if customer.wallet else 0.0

    return render_template(
        'user/customer/customer_dashboard.html', 
        customer=customer, 
        orders=orders,
        favorite_artworks=favorite_artworks,
        followed_artists=followed_artists,
        wallet_balance=wallet_balance
    )


# View Order Detail Page
@user_interface.route('/order_detail/<uuid:order_id>', methods=['GET'])
def order_detail(order_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to view your orders.")
        return redirect(url_for('user.login'))

    try:
        # Ensure the order ID is a valid UUID
        order = Order.query.get(order_id)
        customer_id = uuid.UUID(session['user_id'])
    except ValueError:
        flash("Invalid order ID format.")
        return redirect(url_for('user.customer_dashboard'))

    # Ensure the order belongs to the logged-in customer
    if not order or order.customer_id != customer_id:
        flash("Unauthorized access to order details.")
        return redirect(url_for('user.customer_dashboard'))

    # Fetch additional order details
    product = order.production_round.product
    production_round = order.production_round
    amount_paid = order.amount_paid
    order_date = order.order_date

    return render_template(
        'user/customer/order_detail.html',
        order=order,
        product=product,
        production_round=production_round,
        amount_paid=amount_paid,
        order_date=order_date
    )


# Add artwork to favorites

@user_interface.route('/add_to_favorites/<uuid:artwork_id>', methods=['POST'])
def add_to_favorites(artwork_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to add to favorites.")
        return redirect(url_for('user.login'))

    customer = Customer.query.get(uuid.UUID(session['user_id']))
    artwork = Artwork.query.get(artwork_id)

    if artwork not in customer.favorite_artworks:
        customer.favorite_artworks.append(artwork)
        db.session.commit()
        flash(f"'{artwork.title}' has been added to your favorites.")

     # Redirect back to the page the user was previously on
    return redirect(request.referrer)


@user_interface.route('/remove_from_favorites/<uuid:artwork_id>', methods=['POST'])
def remove_from_favorites(artwork_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to remove from favorites.")
        return redirect(url_for('user.login'))

    customer = Customer.query.get(uuid.UUID(session['user_id']))
    artwork = Artwork.query.get_or_404(artwork_id)

    if artwork in customer.favorite_artworks:
        customer.favorite_artworks.remove(artwork)
        db.session.commit()
        flash(f"'{artwork.title}' has been removed from your favorites.", 'success')

    return redirect(request.referrer or url_for('user.customer_home'))



@user_interface.route('/favorite_artworks', methods=['GET'])
def favorite_artworks():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to view your favorite artworks.")
        return redirect(url_for('user.login'))

    # Convert the user_id from the session to a UUID before querying
    try:
        user_id = uuid.UUID(session['user_id'])
        customer = Customer.query.get(user_id)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user.login'))

    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user.login'))

    favorite_artworks = customer.favorite_artworks

    return render_template('user/customer/favorite_artworks.html', favorite_artworks=favorite_artworks)



# follow and unfollow artists

@user_interface.route('/follow_artist/<uuid:artist_id>', methods=['POST'])
def follow_artist(artist_id):
    if 'user_id' not in session:
        flash("You need to login or sign up to follow an artist.", 'error')
        return redirect(url_for('user.login'))

    if session['role'] != 'customer':
        flash("Only customers can follow an artist.", 'error')
        return redirect(url_for('user.home'))

    customer = Customer.query.get(uuid.UUID(session['user_id']))
    artist = Artist.query.get(artist_id)

    if artist not in customer.followed_artists:
        customer.followed_artists.append(artist)
        db.session.commit()
        flash(f"You are now following '{artist.name}'.", 'success')

    return redirect(request.referrer or url_for('user.customer_home'))



@user_interface.route('/unfollow_artist/<uuid:artist_id>', methods=['POST'])
def unfollow_artist(artist_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to unfollow an artist.", 'error')
        return redirect(url_for('user.login'))

    customer = Customer.query.get(uuid.UUID(session['user_id']))
    artist = Artist.query.get_or_404(artist_id)

    if artist in customer.followed_artists:
        customer.followed_artists.remove(artist)
        db.session.commit()
        flash(f"You have unfollowed '{artist.name}'.", 'success')

    return redirect(request.referrer or url_for('user.customer_home'))


@user_interface.route('/followed_artists', methods=['GET'])
def followed_artists():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to view the artists you follow.")
        return redirect(url_for('user.login'))

    # Convert the user_id from the session to a UUID before querying
    try:
        user_id = uuid.UUID(session['user_id'])
        customer = Customer.query.get(user_id)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user.login'))

    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user.login'))

    followed_artists = customer.followed_artists

    return render_template('user/customer/followed_artists.html', followed_artists=followed_artists)


# transaction section for customers, cart, checkout, view orders, view order details, add fund and sandbox payment

@user_interface.route('/add_to_cart/<uuid:round_id>', methods=['GET', 'POST'])
def add_to_cart(round_id):
    if 'user_id' not in session or session['role'] != 'customer':
        return redirect(url_for('user.login_required', action='add this item to your cart'))

    production_round = ProductionRound.query.get_or_404(round_id)
    if not production_round.is_published:
        flash("Invalid production round.")
        return redirect(url_for('user.home'))

    if request.method == 'POST':
        try:
            quantity = int(request.form['quantity'])
            if quantity < 1:
                raise ValueError("Quantity must be at least 1")

            price = production_round.price
            amount_paid = price * quantity

            # Create a new order and mark it as "in_cart"
            new_order = Order(
                customer_id=uuid.UUID(session['user_id']),
                production_round_id=production_round.id,
                quantity=quantity,
                amount_paid=amount_paid,
                status='pending',
                cart_status='in_cart'
            )
            db.session.add(new_order)
            db.session.commit()

            flash(f"Added {quantity} item(s) of '{production_round.product.name}' to your cart.", 'success')
            return redirect(url_for('user.view_cart'))

        except ValueError:
            flash("Invalid quantity. Please enter a valid number.", 'error')

    return render_template('user/customer/add_to_cart.html', production_round=production_round)




@user_interface.route('/view_cart', methods=['GET', 'POST'])
def view_cart():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to view your cart.")
        return redirect(url_for('user.login'))

    customer_id = uuid.UUID(session['user_id'])
    cart_orders = Order.query.filter_by(customer_id=customer_id, cart_status='in_cart').all()

    if not cart_orders:
        flash("Your cart is empty.")
        return render_template('user/customer/empty_cart.html')

    if request.method == 'POST':
        # Collect selected orders
        selected_order_ids = request.form.getlist('selected_orders')
        if not selected_order_ids:
            flash("Please select at least one product to proceed to checkout.")
            return redirect(url_for('user.view_cart'))

        session['selected_orders'] = selected_order_ids

        return redirect(url_for('user.checkout'))

    return render_template('user/customer/view_cart.html', cart_orders=cart_orders)





@user_interface.route('/update_cart_quantity', methods=['POST'])
def update_cart_quantity():
    if 'user_id' not in session or session['role'] != 'customer':
        return jsonify({"error": "Unauthorized"}), 403

    try:
        data = request.get_json()
        order_id_str = data.get('order_id')
        new_quantity = int(data.get('quantity'))

        if new_quantity < 1:
            return jsonify({"error": "Invalid quantity"}), 400

        # Convert order_id from string to UUID
        try:
            order_id = uuid.UUID(order_id_str)  # Corrected import and usage
        except ValueError:
            return jsonify({"error": "Invalid order ID format"}), 400

        # Find the order and validate that it belongs to the logged-in customer
        customer_id = uuid.UUID(session['user_id'])
        order = Order.query.get(order_id)

        if not order:
            return jsonify({"error": "Order not found"}), 404

        if order.customer_id != customer_id:
            return jsonify({"error": "Unauthorized access to the order"}), 403

        # Update the quantity
        order.quantity = new_quantity
        db.session.commit()
        return jsonify({"message": f"Quantity updated to {new_quantity} for '{order.production_round.product.name}'"}), 200

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500




@user_interface.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to checkout.")
        return redirect(url_for('user.login'))

    customer_id = uuid.UUID(session['user_id'])
    selected_order_ids = session.get('selected_orders', [])

    if not selected_order_ids:
        flash("No items selected for checkout.")
        return redirect(url_for('user.view_cart'))

    # Retrieve the selected orders
    selected_orders = Order.query.filter(Order.id.in_(selected_order_ids), Order.customer_id == customer_id, Order.cart_status == 'in_cart').all()

    # Calculate the total amount
    total_amount = sum(order.quantity * order.production_round.price for order in selected_orders)

    if request.method == 'POST' and 'confirm_checkout' in request.form:
        for order in selected_orders:
            # Create individual Item records for each unit in the order
            for _ in range(order.quantity):
                new_item = Item(
                    order_id=order.id,
                    customer_id=customer_id,
                    production_round_id=order.production_round_id
                )
                db.session.add(new_item)

            # Mark the order as confirmed
            order.cart_status = 'confirmed'
            order.status = 'confirmed'

        db.session.commit()
        flash("Checkout successful! Your items have been purchased.", 'success')
        return redirect(url_for('user.customer_dashboard'))

    return render_template(
        'user/customer/checkout.html',
        cart_orders=selected_orders,
        total_amount=total_amount
    )


@user_interface.route('/select_payment_method', methods=['GET', 'POST'])
def select_payment_method():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to proceed with the payment.")
        return redirect(url_for('user.login'))

    # Retrieve the selected orders and total amount from the session
    selected_order_ids = session.get('selected_orders', [])
    total_amount = session.get('total_amount', 0.0)



    if not selected_order_ids:
        flash("No items selected for payment.")
        return redirect(url_for('user.view_cart'))

    # Render payment selection
    if request.method == 'POST':
        payment_method = request.form.get('payment_method')

        if payment_method == 'wallet':
            return redirect(url_for('user.pay_with_wallet'))
        elif payment_method == 'sandbox':
            return redirect(url_for('user.pay_with_sandbox'))
        else:
            flash("Invalid payment method selected.")
            return redirect(url_for('user.select_payment_method'))

    return render_template(
        'user/customer/select_payment_method.html',
        total_amount=total_amount
    )


# payment with wallet or sandbox

@user_interface.route('/pay_with_wallet', methods=['GET', 'POST'])
def pay_with_wallet():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to make a payment.")
        return redirect(url_for('user.login'))

    # Retrieve customer ID and selected orders from session
    customer_id = uuid.UUID(session['user_id'])
    selected_order_ids = session.get('selected_orders', [])
    total_amount = session.get('total_amount', 0.0)


    # Retrieve customer's wallet information
    customer = Customer.query.get(customer_id)
    wallet = customer.wallet

    if not wallet:
        flash("You do not have a wallet set up.")
        return redirect(url_for('user.select_payment_method'))

    # Handle POST request - When the user confirms wallet payment
    if request.method == 'POST':
        if wallet.balance >= total_amount:
            # Deduct from wallet balance
            wallet.balance -= total_amount

            # Log the transaction as successful
            transaction = TransactionLog(
                customer_id=customer_id,
                amount=total_amount,
                status='paid',
                payment_method='wallet'
            )
            db.session.add(transaction)

            # Confirm all selected orders and change their status to confirmed
            for order_id_str in selected_order_ids:
                order_id = uuid.UUID(order_id_str)
                order = Order.query.get(order_id)
                if order and order.customer_id == customer_id and order.cart_status == 'in_cart':
                    order.cart_status = 'confirmed'
                    order.status = 'confirmed'

            # Commit all changes to the database
            db.session.commit()

            flash("Your payment was successful! The items have been purchased.")
            return redirect(url_for('user.customer_dashboard'))

        else:
            flash("Insufficient balance in your wallet. Please choose another payment method.")
            return redirect(url_for('user.select_payment_method'))

    # Render wallet payment confirmation page
    return render_template(
        'user/customer/pay_with_wallet.html',
        total_amount=total_amount,
        wallet_balance=wallet.balance
    )




@user_interface.route('/add_funds', methods=['GET', 'POST'])
def add_funds():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to add funds.")
        return redirect(url_for('user.login'))

    if request.method == 'POST':
        try:
            amount = float(request.form['amount'])
            if amount <= 0:
                raise ValueError("Amount must be positive.")

            customer = Customer.query.get(uuid.UUID(session['user_id']))
            wallet = customer.wallet or Wallet(customer_id=customer.id, balance=0.0)
            wallet.balance += amount

            db.session.add(wallet)
            db.session.commit()

            # Log the transaction
            transaction = TransactionLog(
                customer_id=customer.id,
                amount=amount,
                status='paid',
                payment_method='wallet'
            )
            db.session.add(transaction)
            db.session.commit()

            flash(f"${amount} has been added to your wallet.")
            return redirect(url_for('user.customer_dashboard'))
        except ValueError:
            flash("Invalid amount. Please enter a positive number.")

    return render_template('user/add_funds.html')



@user_interface.route('/orders_list/<string:category>', methods=['GET'])
def orders_list(category):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to access your orders.")
        return redirect(url_for('user.login'))

    try:
        # Convert the user_id from session to UUID before querying
        user_uuid = uuid.UUID(session['user_id'])
        customer = Customer.query.get(user_uuid)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user.login'))

    if not customer:
        flash("Customer not found.")
        return redirect(url_for('user.login'))

    # Filter orders based on category
    if category == 'all':
        orders = customer.orders
    elif category == 'unpaid':
        orders = [order for order in customer.orders if order.status == 'pending']
    elif category == 'paid':
        orders = [order for order in customer.orders if order.status == 'confirmed']
    elif category == 'in_process':
        in_process_stages = ['minimum production', 'sample production', 'mass production', 'flaw checking']
        orders = [order for order in customer.orders if order.production_round.production_stage in in_process_stages]
    elif category == 'stocking':
        orders = [order for order in customer.orders if order.production_round.production_stage == 'stocking']
    else:
        flash("Invalid category specified.")
        return redirect(url_for('user.customer_dashboard'))

    return render_template('user/customer/orders_list.html', orders=orders, category=category)


# item transfer an refund.

@user_interface.route('/transfer_item/<uuid:item_id>', methods=['POST'])
def transfer_item(item_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to transfer items.")
        return redirect(url_for('user.login'))

    item = Item.query.get_or_404(item_id)
    if item.customer_id != uuid.UUID(session['user_id']):
        flash("You are not authorized to transfer this item.")
        return redirect(url_for('user.view_cart'))

    new_customer_email = request.form['new_customer_email']
    new_customer = Customer.query.filter_by(email=new_customer_email).first()
    if not new_customer:
        flash("Recipient customer not found.")
        return redirect(request.referrer)

    item.is_transferred = True
    item.new_customer_id = new_customer.id
    db.session.commit()

    flash(f"Item transferred to {new_customer.email}.")
    return redirect(url_for('user.view_cart'))


@user_interface.route('/refund_item/<uuid:item_id>', methods=['POST'])
def refund_item(item_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to request a refund.")
        return redirect(url_for('user.login'))

    item = Item.query.get_or_404(item_id)
    if item.customer_id != uuid.UUID(session['user_id']):
        flash("You are not authorized to refund this item.")
        return redirect(url_for('user.view_cart'))

    item.status = 'refunded'
    db.session.commit()

    flash("Item has been refunded successfully.")
    return redirect(url_for('user.view_cart'))



# Artist Dashboard: Submit Artwork and Products, View Disapproval Reasons for artwork and product
# if the product is artist arranged, the artist can edit the product introduction (need implementation for product that is platform arranged)
# the artist can also toggle the display status of the product
# for both artist and platform arranged products, their details is only going to be changed by the order management admin
# However, for artist arranged products, the artist can submit the request for the change (need implementation)


@user_interface.route('/artist_dashboard', methods=['GET'])
def artist_dashboard():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access the dashboard.")
        return redirect(url_for('user.login'))

    try:
        # Convert the user_id from session to UUID before querying
        user_uuid = uuid.UUID(session['user_id'])
        artist = Artist.query.get(user_uuid)
        unread_notifications_count = Notification.get_unread_notifications_count(user_uuid)
    except ValueError:
        flash("Invalid user ID format.")
        return redirect(url_for('user.login'))

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user.login'))

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
        return redirect(url_for('user.login'))

    # Fetch the current logged-in artist
    artist = Artist.query.get(uuid.UUID(session['user_id']))

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user.login'))

    if request.method == 'POST':
        # Get the bio from the form submission
        new_bio = request.form.get('bio')
        if new_bio:
            # Update the artist's bio
            artist.bio = new_bio
            db.session.commit()
            flash("Your bio has been successfully updated.")
            return redirect(url_for('user.artist_dashboard'))
        else:
            flash("Bio cannot be empty.")

    # Render the form for editing the bio (GET request)
    return render_template('user/artist/edit_artist_bio.html', artist=artist)




# artwork

@user_interface.route('/submit_new_artwork', methods=['GET', 'POST'])
def submit_new_artwork():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access this page.")
        return redirect(url_for('user.login'))

    # Convert the user_id from session to UUID before querying
    user_uuid = uuid.UUID(session['user_id'])
    artist = Artist.query.get(user_uuid)
    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user.login'))

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

        return redirect(url_for('user.artwork_upload_success'))

    return render_template('user/artist/submit_artwork.html', artist=artist)



@user_interface.route('/artwork_upload_success', methods=['GET'])
def artwork_upload_success():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to view this page.")
        return redirect(url_for('user.login'))

    # Retrieve the artist's name for display
    user_uuid = uuid.UUID(session['user_id'])
    artist = Artist.query.get(user_uuid)

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user.login'))

    return render_template('user/artist/artwork_upload_success.html', artist=artist)


@user_interface.route('/all_artworks', methods=['GET'])
def all_artworks():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to view this page.")
        return redirect(url_for('user.login'))

    try:
        user_uuid = uuid.UUID(session['user_id'])
        artist = Artist.query.get(user_uuid)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user.login'))

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user.login'))

    # Retrieve all artworks created by the artist
    all_artworks = Artwork.query.filter_by(artist_id=artist.id).all()

    return render_template('user/artist/all_artworks.html', artist=artist, artworks=all_artworks)


@user_interface.route('/artist_search_artworks', methods=['GET'])
def artist_search_artworks():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to perform a search.")
        return redirect(url_for('user.login'))

    query = request.args.get('query')
    if not query:
        flash("Please enter a search query.")
        return redirect(url_for('user.all_artworks'))

    try:
        user_uuid = uuid.UUID(session['user_id'])
        artist = Artist.query.get(user_uuid)
    except ValueError:
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user.login'))

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user.login'))

    # Search for artworks and associated products
    search_term = f"%{query}%"
    artworks = Artwork.query.filter(
        Artwork.artist_id == artist.id,
        (Artwork.title.ilike(search_term)) | (Artwork.description.ilike(search_term)) | (Artwork.hard_tags.ilike(search_term)) | (Artwork.soft_tags.ilike(search_term))
    ).all()

    return render_template('user/artist/artist_search_results.html', artist=artist, artworks=artworks, query=query)



# product

@user_interface.route('/artist_product_management/<uuid:product_id>', methods=['GET'])
def artist_product_management(product_id):
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access this page.")
        return redirect(url_for('user.login'))

    # Convert product_id from URL to UUID and fetch the product
    try:
        product_uuid = uuid.UUID(str(product_id))
        product = Product.query.get(product_uuid)
    except ValueError:
        flash("Invalid product ID format.")
        return redirect(url_for('user.artist_dashboard'))

    if not product:
        flash("Product not found.")
        return redirect(url_for('user.artist_dashboard'))

    return render_template('user/artist/artist_product_management.html', product=product)



# this might need to be deleted?


@user_interface.route('/toggle_display_status/<uuid:product_id>', methods=['POST'])
def toggle_display_status(product_id):
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to change product display status.")
        return redirect(url_for('user.login'))

    product = Product.query.get(product_id)

    # Ensure product belongs to the artist and is approved
    if product and product.production_status == 'Approved':
        product.toggle_display_status()
        flash(f"Display status for '{product.name}' updated to '{product.display_status}'.")
    else:
        flash("Invalid product or product is not approved.")

    return redirect(url_for('user.artist_dashboard'))

# product series, for display
# need rebuild for the artist to manage the series
# the series should be independent of what artwork it belongs to
# just a collection of products that the artist wants to group together





@user_interface.route('/view_artwork_disapproval_reason/<uuid:artwork_id>')
def view_artwork_disapproval_reason(artwork_id):
    # Ensure the user is logged in as an artist
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to view the disapproval reason.")
        return redirect(url_for('user.login'))

    # Retrieve the artwork directly using the artwork_id passed by the route
    artwork = Artwork.query.get(artwork_id)

    # If artwork not found or the current user is not authorized to view it, flash an error
    if not artwork or str(artwork.artist_id) != session['user_id']:
        flash("You are not authorized to view this disapproval reason.")
        return redirect(url_for('user.artist_dashboard'))

    # Ensure the artwork has been disapproved before allowing access to disapproval reason
    if artwork.approval_status != 'Disapproved':
        flash("This artwork has not been disapproved.")
        return redirect(url_for('user.artist_dashboard'))

    # Render the disapproval reason page with the artwork details
    return render_template('user/artist/view_artwork_disapproval_reason.html', artwork=artwork)



@user_interface.route('/view_product_disapproval_reason/<uuid:product_id>', methods=['GET'])
def view_product_disapproval_reason(product_id):
    # Ensure the user is logged in as an artist
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to view the disapproval reason.")
        return redirect(url_for('user.login'))

    # Retrieve the product directly using the product_id passed by the route
    product = Product.query.get_or_404(product_id)

    # Ensure the product belongs to the current artist via the associated artwork
    if str(product.artwork.artist_id) != session['user_id']:
        flash("You are not authorized to view this disapproval reason.")
        return redirect(url_for('user.artist_dashboard'))

    # Ensure the product has been disapproved before allowing access to disapproval reason
    if product.production_status != 'Disapproved':
        flash("This product has not been disapproved.")
        return redirect(url_for('user.artist_dashboard'))

    # Render the disapproval reason template with the product details
    return render_template('user/artist/view_product_disapproval_reason.html', product=product)




@user_interface.route('/submit_product/<uuid:artwork_id>', methods=['GET', 'POST'])
def submit_product(artwork_id):
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to submit a product.", 'error')
        return redirect(url_for('user.login'))

    # Get the artwork using the provided artwork_id
    artwork = Artwork.query.get(artwork_id)

    # Ensure that the artwork belongs to the logged-in artist
    if not artwork or artwork.artist_id != uuid.UUID(session['user_id']):
        flash("You are not authorized to submit a product for this artwork.", 'error')
        return redirect(url_for('user.artist_dashboard'))

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
                redirect_url=url_for('user.artist_dashboard')
            )

        except Exception as e:
            # Handle any unexpected exceptions
            print(f"Error: {e}")  # For debugging purposes
            # Redirect to the submission status page with failure
            return render_template(
                'user/artist/product_submission_status.html',
                success=False,
                redirect_url=url_for('user.artist_dashboard')
            )

    return render_template('user/artist/submit_product.html', artwork=artwork)


# artist choose who would be in control of starting the production round for a product

@user_interface.route('/manage_production_initialization/<uuid:product_id>', methods=['GET', 'POST'])
def manage_production_initialization(product_id):
    """Manage the initialization control of production rounds for a product."""
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to manage production initialization.")
        return redirect(url_for('user.login'))

    try:
        product = Product.query.get_or_404(product_id)
        if product.artist_id != uuid.UUID(session['user_id']):
            flash("Unauthorized access to this product.")
            return redirect(url_for('user.artist_dashboard'))

        if request.method == 'POST':
            # Toggle the artist-controlled flag
            product.toggle_control()
            flash(
                "Production round initialization is now "
                + ("controlled by the artist." if product.artist_controlled else "controlled by the admin.")
            )
            return redirect(url_for('user.manage_production_initialization', product_id=product.id))

        return render_template(
            'user/artist/manage_production_initialization.html',
            product=product
        )

    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('user.artist_dashboard'))



# route for the situation where the artist is in control of the production round initialization


@user_interface.route('/artist_initialize_production_round/<uuid:product_id>', methods=['POST'])
def artist_initialize_production_round(product_id):
    """Route for the artist to initialize a production round."""
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to initialize a production round.")
        return redirect(url_for('user.login'))

    product = Product.query.get_or_404(product_id)
    if product.artist_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access to this product.")
        return redirect(url_for('user.artist_dashboard'))

    if not product.artist_controlled:
        flash("You do not have control over initializing production rounds for this product.")
        return redirect(url_for('user.artist_dashboard'))

    # Check if an active production round already exists
    existing_round = ProductionRound.query.filter_by(product_id=product.id, is_active=True).first()
    if existing_round:
        flash("An in-progress production round already exists. You cannot initialize a new one.")
        return redirect(url_for('user.artist_dashboard'))

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
    return redirect(url_for('user.artist_dashboard'))




@user_interface.route('/download_file/<uuid:file_id>')
def download_file(file_id):
    if 'user_id' not in session:
        flash("You need to be logged in to download files.")
        return redirect(url_for('user.login'))

    design_file = DesignFile.query.get(file_id)
    if not design_file:
        flash("File not found.")
        return redirect(request.referrer or url_for('user.home'))

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
# historical dialog collection and the dialog for previous dialogs



@user_interface.route('/product_dialog/<uuid:product_id>', methods=['GET', 'POST'])
def artist_active_product_dialog(product_id):
    """Dialog for the current active production round for the artist."""
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access this dialog.")
        return redirect(url_for('user.login'))

    # Fetch the active production round
    production_round = ProductionRound.query.filter_by(product_id=product_id, is_active=True).first()
    if not production_round:
        flash("No active production round found for this product.")
        return redirect(url_for('user.artist_dashboard'))

    # Check if the artist is authorized
    if production_round.artist_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access to this dialog.")
        return redirect(url_for('user.artist_dashboard'))

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


@user_interface.route('/historical_dialog_collection/<uuid:product_id>', methods=['GET'])
def artist_historical_dialog_collection(product_id):
    """List historical dialogs for a product for the artist."""
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to view historical dialogs.")
        return redirect(url_for('user.login'))

    # Fetch all historical production rounds for the given product
    historical_rounds = ProductionRound.query.filter_by(product_id=product_id, is_active=False).all()

    if not historical_rounds:
        flash("No historical production rounds found for this product.")
        return redirect(url_for('user.artist_dashboard'))

    product = Product.query.get(product_id)

    return render_template(
        'user/artist/historical_dialog_collection.html',
        product=product,
        historical_rounds=historical_rounds
    )




@user_interface.route('/historical_dialog/<uuid:round_id>', methods=['GET'])
def artist_historical_product_dialog(round_id):
    """Read-only dialog for a historical production round for the artist."""
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access this dialog.")
        return redirect(url_for('user.login'))

    # Fetch the historical production round
    production_round = ProductionRound.query.filter_by(id=round_id, is_active=False).first()
    if not production_round:
        flash("No historical production round found.")
        return redirect(url_for('user.artist_dashboard'))

    # Check if the artist is authorized
    if production_round.artist_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access to this dialog.")
        return redirect(url_for('user.artist_dashboard'))

    # Fetch all messages in this dialog
    messages = Dialog.query.filter_by(production_round_id=production_round.id).order_by(Dialog.timestamp).all()

    return render_template('user/artist/historical_dialog.html', production_round=production_round, messages=messages)






# Notifications Viewing System for Artists and Customers

@user_interface.route('/view_notifications', methods=['GET', 'POST'])
def view_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('user.login'))

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


@user_interface.route('/mark_notification_read/<uuid:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    # Ensure the user is logged in
    if 'user_id' not in session:
        flash("You need to be logged in to mark a notification as read.")
        return redirect(url_for('user.login'))

    try:
        # Find the notification by ID
        notification = Notification.query.get(notification_id)

        # Ensure the notification belongs to the logged-in user
        user_id = uuid.UUID(session['user_id'])
        if notification.user_id != user_id:
            flash("You are not authorized to mark this notification as read.")
            return redirect(url_for('user.view_notifications'))

        # Mark the notification as read
        notification.is_read = True
        db.session.commit()
        flash("Notification has been marked as read.")

    except Exception as e:
        flash("An error occurred while trying to mark the notification as read.")

    return redirect(url_for('user.view_notifications'))




@user_interface.route('/view_read_notifications', methods=['GET', 'POST'])
def view_read_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('user.login'))

    user_id = uuid.UUID(session['user_id'])
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=True).order_by(Notification.timestamp.desc()).all()

    # Categorize notifications
    categorized_notifications = {}
    for notification in unread_notifications:
        if notification.type not in categorized_notifications:
            categorized_notifications[notification.type] = []
        categorized_notifications[notification.type].append(notification)

    return render_template('user/account/read_notifications.html', categorized_notifications=categorized_notifications)
