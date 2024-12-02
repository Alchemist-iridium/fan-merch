from flask import request, Blueprint,current_app, render_template, render_template_string, redirect, url_for, session, flash, current_app, send_file, jsonify
from datetime import datetime, timezone
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from models import *
from extensions import db
import uuid
from sqlalchemy.dialects.postgresql import UUID


user_interface = Blueprint('user', __name__)



# Web Routes
@user_interface.route('/')
def home():
    return render_template('home.html')



@user_interface.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role'].lower()  # Either "customer" or "artist"
        
        # Check if the email is already in use
        if User.query.filter_by(email=email).first():
            flash('Email address already registered')
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
                flash('Invalid role selected. Please choose either "Customer" or "Artist".')
                return redirect(url_for('user.signup'))
            
            with current_app.app_context():
                db.session.add(new_user)
                db.session.commit()

            # Redirect to the signup success page instead of login page, mostly for welcome message
            return redirect(url_for('user.signup_success', name=name))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for('user.signup'))

    return render_template('account/signup.html')


@user_interface.route('/signup_success/<string:name>')  # registration successful, welcome page
def signup_success(name):
    return render_template('account/signup_success.html', name=name)



@user_interface.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Query the user from the database
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = str(user.id)
            session['role'] = user.role
            flash("Login successful!")

            # Redirect to the appropriate dashboard based on role
            if user.role == 'artwork_approval_admin':
                return redirect(url_for('user.artwork_approval_admin_dashboard'))
            elif user.role == 'order_management_admin':
                return redirect(url_for('user.order_management_admin_dashboard'))
            elif user.role == 'product_approval_admin':
                return redirect(url_for('user.product_approval_admin_dashboard'))
            elif user.role == 'artist':
                return redirect(url_for('user.artist_dashboard'))
            elif user.role == 'customer':
                return redirect(url_for('user.customer_home'))
        else:
            # If login fails, return to login page with error message
            error = "Wrong email or password"
            return render_template('account/login.html', error=error)
        
    return render_template('account/login.html')

@user_interface.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash("You have been logged out.")
    return redirect(url_for('user.home'))


#The final result should be:
#customer_home and customer_dashboard (view orders and historical purchase record)
#artist_dashboard (check the historical artwork status and product)
#factory_dashboard (add with admin's approval) do we need it??? probably not in this webpages?
#admin_dashboard... There should be subclass on roles. For simplicity, not change the [customer,] For instance, the customer service staff


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

    return render_template('customer/customer_home.html', customer=customer, search_results=search_results)



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
        'customer/customer_dashboard.html', 
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
        'customer/order_detail.html',
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


# Follow an artist
@user_interface.route('/follow_artist/<uuid:artist_id>', methods=['POST'])
def follow_artist(artist_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to follow an artist.")
        return redirect(url_for('user.login'))

    customer = Customer.query.get(uuid.UUID(session['user_id']))
    artist = Artist.query.get(artist_id)

    if artist not in customer.followed_artists:
        customer.followed_artists.append(artist)
        db.session.commit()
        flash(f"You are now following '{artist.name}'.")

     # Redirect back to the page the user was previously on
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

    return render_template('customer/favorite_artworks.html', favorite_artworks=favorite_artworks)


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

    return render_template('customer/followed_artists.html', followed_artists=followed_artists)


# transaction section for customers, cart, checkout, view orders, view order details, add fund and sandbox payment


@user_interface.route('/add_to_cart/<uuid:round_id>', methods=['GET', 'POST'])
def add_to_cart(round_id):
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to add to cart.")
        return redirect(url_for('user.login'))

    production_round = ProductionRound.query.get(round_id)
    if not production_round or not production_round.is_published:
        flash("Invalid production round.")
        return redirect(url_for('user.home'))

    if request.method == 'POST':
        try:
            quantity = int(request.form['quantity'])
            if quantity < 1:
                raise ValueError("Quantity must be at least 1")

            estimated_price = production_round.estimated_price
            amount_paid = estimated_price * quantity

            # Create a new order and mark it as "in_cart"
            new_order = Order(
                customer_id=uuid.UUID(session['user_id']),
                production_round_id=production_round.id,
                quantity=quantity,
                amount_paid=amount_paid,
                status='pending',
                cart_status='in_cart'  # This indicates that it hasn't been finalized/paid yet
            )
            db.session.add(new_order)
            db.session.commit()

            flash(f"Added {quantity} item(s) of '{production_round.product.name}' to your cart.")
            return redirect(url_for('user.view_cart'))

        except ValueError:
            flash("Invalid quantity. Please enter a valid number.")

    return render_template('add_to_cart.html', production_round=production_round)




@user_interface.route('/view_cart', methods=['GET', 'POST'])
def view_cart():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to view your cart.")
        return redirect(url_for('user.login'))

    customer_id = uuid.UUID(session['user_id'])
    cart_orders = Order.query.filter_by(customer_id=customer_id, cart_status='in_cart').all()

    if not cart_orders:
        flash("Your cart is empty.")
        return render_template('customer/empty_cart.html')

    if request.method == 'POST':
        # Collect selected orders
        selected_order_ids = request.form.getlist('selected_orders')
        if not selected_order_ids:
            flash("Please select at least one product to proceed to checkout.")
            return redirect(url_for('user.view_cart'))

        session['selected_orders'] = selected_order_ids

        return redirect(url_for('user.checkout'))

    return render_template('customer/view_cart.html', cart_orders=cart_orders)





@user_interface.route('/update_cart_quantity', methods=['POST'])
def update_cart_quantity():
    if 'user_id' not in session or session['role'] != 'customer':
        print("[DEBUG] Unauthorized request: user not logged in or wrong role.")
        return jsonify({"error": "Unauthorized"}), 403

    try:
        data = request.get_json()
        order_id_str = data.get('order_id')
        new_quantity = int(data.get('quantity'))

        if new_quantity < 1:
            print("[DEBUG] Invalid quantity received:", new_quantity)
            return jsonify({"error": "Invalid quantity"}), 400

        # Convert order_id from string to UUID
        try:
            order_id = uuid.UUID(order_id_str)  # Corrected import and usage
        except ValueError:
            print("[DEBUG] Invalid order_id format received:", order_id_str)
            return jsonify({"error": "Invalid order ID format"}), 400

        # Find the order and validate that it belongs to the logged-in customer
        customer_id = uuid.UUID(session['user_id'])
        order = Order.query.get(order_id)

        if not order:
            print("[DEBUG] Order not found:", order_id)
            return jsonify({"error": "Order not found"}), 404

        if order.customer_id != customer_id:
            print("[DEBUG] Unauthorized access: Order customer_id does not match session customer_id.")
            return jsonify({"error": "Unauthorized access to the order"}), 403

        # Update the quantity
        order.quantity = new_quantity
        db.session.commit()
        print(f"[DEBUG] Successfully updated order quantity to {new_quantity} for order ID {order_id}.")
        return jsonify({"message": f"Quantity updated to {new_quantity} for '{order.production_round.product.name}'"}), 200

    except Exception as e:
        print(f"[DEBUG] An error occurred: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500




@user_interface.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to checkout.")
        return redirect(url_for('user.login'))

    customer_id = uuid.UUID(session['user_id'])
    selected_order_ids = session.get('selected_orders', [])

    # Retrieve only the selected orders for checkout
    selected_orders = []
    if selected_order_ids:
        try:
            for order_id_str in selected_order_ids:
                order_id = uuid.UUID(order_id_str)
                order = Order.query.get(order_id)
                if order and order.customer_id == customer_id and order.cart_status == 'in_cart':
                    selected_orders.append(order)
                else:
                    print(f"[DEBUG] Order with ID {order_id} not found or invalid.")
        except ValueError as e:
            flash("Invalid order ID format.")
            print(f"[DEBUG] ValueError encountered: {e}")
            return redirect(url_for('user.view_cart'))
    else:
        flash("No items selected for checkout.")
        return redirect(url_for('user.view_cart'))

    # Calculate the total amount for the selected items
    try:
        total_amount = sum(order.quantity * order.production_round.estimated_price for order in selected_orders)
    except Exception as e:
        # Add more debugging to trace issues with the calculation
        print(f"[DEBUG] Exception occurred while calculating total_amount: {e}")
        total_amount = 0.0

    # Debugging: Ensure total_amount is correct
    print("[DEBUG] Selected Orders:", selected_orders)
    for order in selected_orders:
        print(f"[DEBUG] Order Details: ID={order.id}, Quantity={order.quantity}, Estimated Price={order.production_round.estimated_price}")
    print("[DEBUG] Total Amount Calculated:", total_amount)

    if request.method == 'POST' and 'confirm_checkout' in request.form:
        # Store selected order ids and total amount in session for later use
        session['selected_orders'] = [str(order.id) for order in selected_orders]
        session['total_amount'] = total_amount

        # Debugging: Check session storage
        print("[DEBUG] Session Data Saved - selected_orders:", session['selected_orders'])
        print("[DEBUG] Session Data Saved - total_amount:", session['total_amount'])

        # Redirect to the select payment method page
        return redirect(url_for('user.select_payment_method'))

    # Render the checkout page with selected orders and total amount
    return render_template(
        'customer/checkout.html',
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
        'customer/select_payment_method.html',
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

    # Debugging: Print selected order IDs and total amount
    print("[DEBUG] Selected Orders:", selected_order_ids)
    print("[DEBUG] Total Amount:", total_amount)

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
        'customer/pay_with_wallet.html',
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

    return render_template('add_funds.html')



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

    return render_template('customer/orders_list.html', orders=orders, category=category)




# Artist Dashboard: Submit Artwork and Products, View Disapproval Reasons for artwork and product
# if the product is artist arranged, the artist can edit the product introduction (need implementation for product that is platform arranged)
# the artist can also toggle the display status of the product
# for both artist and platform arranged products, their details is only going to be changed by the order management admin
# However, for artist arranged products, the artist can submit the request for the change (need implementation)

@user_interface.route('/artist_dashboard', methods=['GET', 'POST'])
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
        # Handle invalid UUID format
        flash("Invalid user ID format.")
        return redirect(url_for('user.login'))

    if not artist:
        flash("Artist not found.")
        return redirect(url_for('user.login'))

    # Handle submitting artwork (existing functionality)
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        manufacturing_specs = request.form['manufacturing_specs']
        hard_tags = request.form['hard_tags']
        soft_tags = request.form.get('soft_tags', "")

        # Handle file upload
        if 'image' not in request.files:
            flash("No file part")
            return redirect(request.url)
        file = request.files['image']
        if file.filename == '':
            flash("No selected file")
            return redirect(request.url)
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        else:
            image_path = ''

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
        except ValueError as e:
            flash(str(e))

        return redirect(url_for('user.artwork_upload_success'))

    # Retrieve the latest five artworks with the most recent changes in status
    recent_artworks = Artwork.query.filter_by(artist_id=artist.id).order_by(Artwork.updated_at.desc()).limit(5).all()

    # Using the relationship to get products associated with each artwork
    recent_artworks_with_products = []
    for artwork in recent_artworks:
        artwork_dict = {
            "artwork": artwork,
            "products": artwork.products  # using the relationship to get associated products
        }
        recent_artworks_with_products.append(artwork_dict)

    return render_template('artist/artist_dashboard.html', artist=artist, recent_artworks=recent_artworks_with_products, unread_notifications_count=unread_notifications_count)


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
    return render_template('artist/edit_artist_bio.html', artist=artist)


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
        if 'image' not in request.files:
            flash("No file part")
            return redirect(request.url)
        file = request.files['image']
        if file.filename == '':
            flash("No selected file")
            return redirect(request.url)
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        else:
            image_path = ''

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
        except ValueError as e:
            flash(str(e))

        return redirect(url_for('user.artwork_upload_success'))

    return render_template('artist/submit_artwork.html', artist=artist)


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

    return render_template('artist/artwork_upload_success.html', artist=artist)


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

    return render_template('artist/all_artworks.html', artist=artist, artworks=all_artworks)


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

    return render_template('artist/artist_search_results.html', artist=artist, artworks=artworks, query=query)



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

    return render_template('artist/artist_product_management.html', product=product)




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
    return render_template('artist/view_artwork_disapproval_reason.html', artwork=artwork)



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
    return render_template('artist/view_product_disapproval_reason.html', product=product)



@user_interface.route('/edit_product/<uuid:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to edit the product.")
        return redirect(url_for('user.login'))

    product = Product.query.get(product_id)

    flash_message = None  # Initialize as None, used to pass context to the HTML

    if request.method == 'POST':
        # Get the edited introduction from the form
        introduction = request.form['introduction']

        # Update product introduction
        product.introduction = introduction

        # Commit changes to the database
        db.session.commit()

        # Set the flash message to pass to the template
        flash_message = "Introduction successfully uploaded."

    return render_template('artist/edit_product.html', product=product, flash_message=flash_message)




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
        description = request.form['description']
        manufacture_type = request.form['manufacture_type']

        try:
            # Create product with Pending status for Product Approval Admin approval
            new_product = Product(
                name=name,
                production_specs=production_specs,
                description=description,
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
                'artist/product_submission_status.html',
                success=True,
                redirect_url=url_for('user.artist_dashboard')
            )

        except Exception as e:
            # Handle any unexpected exceptions
            print(f"Error: {e}")  # For debugging purposes
            # Redirect to the submission status page with failure
            return render_template(
                'artist/product_submission_status.html',
                success=False,
                redirect_url=url_for('user.artist_dashboard')
            )

    return render_template('artist/submit_product.html', artwork=artwork)



@user_interface.route('/request_production_round/<uuid:product_id>', methods=['POST'])
def request_production_round(product_id):
    # Check if the user is logged in as an artist
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to request a production round.")
        return redirect(url_for('user.login'))

    try:
        # Retrieve the product by ID and ensure it belongs to the logged-in artist
        product = Product.query.get(product_id)
        if not product or product.artist_id != uuid.UUID(session['user_id']):
            flash("Unauthorized access or invalid product.")
            return redirect(url_for('user.artist_dashboard'))

        # Check if there's already an existing production round for this product
        # Need adjustment for multiple production rounds, only open one for display
        existing_round = ProductionRound.query.filter_by(product_id=product.id).first()
        if existing_round:
            flash("A production round already exists for this product.")
            return redirect(url_for('user.artist_dashboard'))

        # Ensure the product has been assigned an Order Management Admin
        if not product.assigned_admin_id:
            flash("This product has not yet been assigned an Order Management Admin.")
            return redirect(url_for('user.artist_dashboard'))
        
        # send notification to the assigned admin
        product_admin = product.assigned_admin_id
        if product_admin:
            message = f"New production round request for the product '{product.name}'."
            Notification.send_notification(user_id=product.assigned_admin_id, message=message)
        

        # Create a new production round with status 'requested'
        new_round = ProductionRound(
            product_id=product.id,
            artist_id=product.artist_id,
            admin_id=product.assigned_admin_id,  # Link the assigned admin to the production round
            status='requested'
        )
        db.session.add(new_round)
        db.session.commit()

        # Redirect to the confirmation page
        return render_template('artist/production_round_request_confirmation.html', product=product)

    except Exception as e:
        # Handle any unexpected errors that may occur
        flash(f"An error occurred while processing your request: {str(e)}")
        return redirect(url_for('user.artist_dashboard'))




# Artwork Approval Admin Dashboard, disapprove artwork, approve artwork
@user_interface.route('/artwork_approval_admin_dashboard', methods=['GET', 'POST'])
def artwork_approval_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access this dashboard.")
        return redirect(url_for('user.login'))

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
                    return redirect(url_for('user.artwork_approval_admin_dashboard'))

        elif 'disapprove_id' in request.form:
            artwork_id = request.form['disapprove_id']
            if artwork_id and artwork_id.isdigit():
                return redirect(url_for('user.disapprove_artwork', artwork_id=artwork_id))

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

    return render_template('artwork_approval_admin/artwork_approval_admin_dashboard.html', artworks=artworks_info, search_results=search_results)




@user_interface.route('/approve_artwork/<uuid:artwork_id>', methods=['POST'])
def approve_artwork(artwork_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to approve artworks.")
        return redirect(url_for('user.login'))

    artwork = Artwork.query.get(artwork_id)
    if not artwork or artwork.approval_status != 'Pending':
        flash("Invalid artwork or it is not pending approval.")
        return redirect(url_for('user.artwork_approval_admin_dashboard'))

    # Update artwork status to approved
    artwork.approval_status = 'Approved'
    db.session.commit()
    
    # Send notification to the artist about approval
    artist_id = artwork.artist_id
    message = f"Your artwork '{artwork.title}' has been approved."
    Notification.send_notification(user_id=artist_id, message=message)

    flash(f"Artwork '{artwork.title}' has been approved.")
    return redirect(url_for('user.artwork_approval_admin_dashboard'))



@user_interface.route('/disapprove_artwork/<uuid:artwork_id>', methods=['GET', 'POST'])
def disapprove_artwork(artwork_id):
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to disapprove artworks.")
        return redirect(url_for('user.login'))

    artwork = Artwork.query.get_or_404(artwork_id)

    if request.method == 'POST':
        # Make sure the field `disapprove_reason` exists in the form submission
        reason = request.form.get('disapprove_reason', None)
        if reason:
            # Update artwork status to disapproved with reason
            artwork.approval_status = 'Disapproved'
            artwork.disapproval_reason = reason
            db.session.commit()

            # Send notification to the artist about disapproval
            artist_id = artwork.artist_id
            message = f"Your artwork '{artwork.title}' has been disapproved. Reason: {reason}"
            link = url_for('user.view_artwork_disapproval_reason', artwork_id=artwork.id, _external=True)  # Link to view disapproval reason
            Notification.send_notification(user_id=artist_id, message=message, link=link)

            flash(f"Artwork '{artwork.title}' has been disapproved.")
            return redirect(url_for('user.artwork_approval_admin_dashboard'))
        else:
            flash("Please provide a reason for disapproval.")
            return render_template('artwork_approval_admin/disapprove_artwork.html', artwork=artwork)

    # GET request - render the form
    return render_template('artwork_approval_admin/disapprove_artwork.html', artwork=artwork)


# order management admin dashboard, update product status

@user_interface.route('/order_management_admin_dashboard', methods=['GET'])
def order_management_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dashboard.")
        return redirect(url_for('user.login'))

    # Convert session user ID to UUID
    try:
        admin_id = uuid.UUID(session['user_id'])
        unread_notifications_count = Notification.get_unread_notifications_count(admin_id)
    except ValueError:
        flash("Invalid session user ID.")
        return redirect(url_for('user.login'))

    # Get products assigned to the logged-in admin
    products = Product.query.filter_by(assigned_admin_id=admin_id).all()

    # Get all production rounds requested but not finalized yet
    production_rounds = ProductionRound.query.filter_by(admin_id=admin_id, status='requested').all()

    return render_template('order_management_admin/order_management_admin_dashboard.html', products=products, production_rounds=production_rounds,unread_notifications_count=unread_notifications_count)


@user_interface.route('/production_round/<uuid:round_id>', methods=['GET', 'POST'])
def handle_production_round(round_id):
    # Check if the user is logged in
    if 'user_id' not in session:
        flash("You need to be logged in as an Order Management Admin to manage production rounds.")
        return redirect(url_for('user.login'))

    # Check if the user has the correct role
    if session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to manage production rounds.")
        return redirect(url_for('user.login'))

    # Attempt to retrieve the production round by ID
    production_round = ProductionRound.query.get(round_id)
    if not production_round:
        flash("Invalid production round.")
        return redirect(url_for('user.order_management_admin_dashboard'))

    # Check if the current user is the admin assigned to this production round
    if production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access or invalid production round.")
        return redirect(url_for('user.order_management_admin_dashboard'))

    # Handle POST request to modify production round details
    if request.method == 'POST':
        try:
            # Fetch production round details from the form
            production_round.estimated_price = float(request.form['estimated_price'])
            production_round.min_production_size = int(request.form['min_production_size'])
            production_round.max_waiting_time = int(request.form['max_waiting_time'])
            
            # Handle optional actual price
            actual_price_str = request.form.get('actual_price')
            if actual_price_str:
                production_round.actual_price = float(actual_price_str)
            else:
                production_round.actual_price = None  # Reset or leave unchanged

            # Update the status if needed (if this is the initial setup)
            if production_round.status == 'requested':
                production_round.status = 'in_progress'

            # Handle optional publishing status
            production_round.is_published = request.form.get('is_published') == 'on'

            # Commit changes to the database
            db.session.commit()
            flash(f"Production round for product '{production_round.product.name}' has been updated successfully.")
            return redirect(url_for('user.order_management_admin_dashboard'))
        except ValueError:
            flash("Invalid input. Please ensure all fields are filled out correctly.")

    # Render the appropriate template for managing the production round
    return render_template('order_management_admin/manage_production_round.html', production_round=production_round)




@user_interface.route('/publish_production_round/<uuid:round_id>', methods=['POST'])
def publish_production_round(round_id):
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to publish this production round.")
        return redirect(url_for('user.login'))

    production_round = ProductionRound.query.get(round_id)
    if not production_round or production_round.admin_id != uuid.UUID(session['user_id']):
        flash("Unauthorized access or invalid production round.")
        return redirect(url_for('user.order_management_admin_dashboard'))

    # Mark production round as published
    production_round.is_published = True
    db.session.commit()
    flash(f"Production round for product '{production_round.product.name}' has been published.")

    return redirect(url_for('user.order_management_admin_dashboard'))



# Product Approval Admin Dashboard, download design file, approve product, disapprove product, assign product to order management admin
@user_interface.route('/product_approval_admin_dashboard', methods=['GET', 'POST'])
def product_approval_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to access this dashboard.")
        return redirect(url_for('user.login'))

    if request.method == 'POST':
        # Approve Product
        if 'approve_id' in request.form:
            product_id_str = request.form['approve_id']
            try:
                product_id = UUID(product_id_str)
            except ValueError:
                flash("Invalid product ID.")
                return redirect(url_for('user.product_approval_admin_dashboard'))

            product = Product.query.get(product_id)

            if product and product.production_status == 'Pending':
                # Product is still pending, but we now direct to assign an Order Management Admin
                flash(f"Product '{product.name}' is approved for assignment. Please assign an Order Management Admin.")
                return redirect(url_for('user.assign_order_management_admin', product_id=product_id))

        # Handle disapproval request
        elif 'disapprove_id' in request.form:
            product_id_str = request.form['disapprove_id']
            try:
                product_id = UUID(product_id_str)
            except ValueError:
                flash("Invalid product ID.")
                return redirect(url_for('user.product_approval_admin_dashboard'))

            return redirect(url_for('user.disapprove_product', product_id=product_id))

    # Fetch all pending products
    pending_products = Product.query.filter_by(production_status='Pending').all()

    return render_template('product_approval_admin/product_approval_admin_dashboard.html', pending_products=pending_products)




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


from flask import flash, redirect, url_for, session, request, render_template
from datetime import datetime, timezone
from models import Product, Notification, db, User

@user_interface.route('/approve_product/<uuid:product_id>', methods=['POST'])
def approve_product(product_id):
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to approve products.")
        return redirect(url_for('user.login'))

    # Fetch the product from the database
    product = Product.query.get_or_404(product_id)

    # If the product is pending, redirect to assignment page without changing the status
    if product and product.production_status == 'Pending':
        flash(f"Product '{product.name}' approval initiated. Now, please assign an Order Management Admin.")
        
        # Send notification to the artist
        artist = product.artist  # Assuming there's a relationship between Product and User for the artist
        if artist:
            message = f"Your product '{product.name}' has been approved."
            Notification.send_notification(user_id=artist.id, message=message)

        # Redirect to assign the Order Management Admin page
        return redirect(url_for('user.assign_order_management_admin', product_id=product.id))
    else:
        flash("Product not found or it is not pending approval.")

    return redirect(url_for('user.product_approval_admin_dashboard'))



@user_interface.route('/disapprove_product/<uuid:product_id>', methods=['GET', 'POST'])
def disapprove_product(product_id):
    # Check if the user is logged in and has the correct role
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to disapprove a product.")
        return redirect(url_for('user.login'))

    # Fetch the product using its UUID
    product = Product.query.get_or_404(product_id)

    # Ensure the product is in the pending state for disapproval
    if product.production_status != 'Pending':
        flash("Invalid product or product is not pending.")
        return redirect(url_for('user.product_approval_admin_dashboard'))

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
                Notification.send_notification(user_id=artist.id, message=message)

            flash(f"Product '{product.name}' has been disapproved with reason: {reason}")
            return redirect(url_for('user.product_approval_admin_dashboard'))
        else:
            flash("Disapproval reason is required.")

    # GET request - render the form for disapproval
    return render_template('product_approval_admin/disapprove_product.html', product=product)



@user_interface.route('/assign_order_management_admin/<uuid:product_id>', methods=['GET', 'POST'])
def assign_order_management_admin(product_id):
    # Check if the user is logged in and has the correct role
    if 'user_id' not in session or session['role'] != 'product_approval_admin':
        flash("You need to be logged in as a Product Approval Admin to assign an Order Management Admin.")
        return redirect(url_for('user.login'))

    # Get the product based on the UUID
    product = Product.query.get(product_id)
    if not product or product.production_status != 'Pending':
        flash("Invalid product or product is not ready for admin assignment.")
        return redirect(url_for('user.product_approval_admin_dashboard'))

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
                    return redirect(url_for('user.product_approval_admin_dashboard'))
                else:
                    flash("Selected Order Management Admin does not exist.")
            except ValueError:
                flash("Invalid Order Management Admin ID format.")

    # Send notification to the artist
            order_admin = product.assigned_admin_id  # Assuming there's a relationship between Product and User for the artist
            if order_admin:
                message = f"A new product '{product.name}' has been assigned to you."
                Notification.send_notification(user_id=order_admin, message=message)

    # Render the template for assigning an admin to the product
    return render_template('product_approval_admin/assign_order_management_admin.html', product=product, order_management_admins=order_management_admins)


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
        customer = Customer.query.get(uuid.UUID(session['user_id']))

    # Render the public artist page, passing all necessary data
    return render_template(
        'public_search/artist_public_page.html', 
        artist=artist, 
        artworks=artworks, 
        products=products, 
        customer=customer
    )


@user_interface.route('/artwork/<uuid:artwork_id>')
def artwork_page(artwork_id):
    # Fetch the artwork from the database
    work = Artwork.query.get(artwork_id)
    customer = None

    # Check if user is logged in and has 'customer' role
    if 'customer_id' in session and session['role'] == 'customer':
        customer = Customer.query.get(session['customer_id'])
    
    if work and work.approval_status == 'Approved':
        # Fetch only approved products that are marked for display
        approved_products = Product.query.filter_by(
            artwork_id=work.id, 
            production_status='Approved', 
            display_status='on display'
        ).all()

        return render_template(
            'public_search/artwork_page.html', 
            work=work, 
            approved_products=approved_products,
            customer=customer
        )
    
    return redirect(url_for('user.home'))




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

    return render_template('public_search/public_search.html', search_results=search_results)



@user_interface.route('/product_public/<uuid:product_id>')
def product_public(product_id):
    product = Product.query.get(product_id)
    if product and product.production_status == 'Approved' and product.display_status == 'on display':
        return render_template('public_search/product_public.html', product=product)
    flash("This product is not available for public viewing.")
    return redirect(url_for('user.home'))


@user_interface.route('/production_round/<uuid:round_id>', methods=['GET'])
def production_round_page(round_id):
    if 'user_id' not in session:
        flash("You need to be logged in to view this production round.")
        return redirect(url_for('user.login'))

    try:
        production_round_uuid = uuid.UUID(str(round_id))
    except ValueError:
        flash("Invalid production round ID.")
        return redirect(url_for('user.home'))

    production_round = ProductionRound.query.get(production_round_uuid)

    if not production_round or not production_round.is_published:
        flash("Production round not found or not yet published.")
        return redirect(url_for('user.home'))

    related_rounds = ProductionRound.query.filter_by(product_id=production_round.product_id).all()

    return render_template('production_round_page.html', production_round=production_round, related_rounds=related_rounds)



# View notifications for the logged-in user, unread ones in first page, the read ones are displayed in a separate page
@user_interface.route('/view_notifications', methods=['GET', 'POST'])

def view_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('user.login'))

    user_id = uuid.UUID(session['user_id'])
    unread_notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.timestamp.desc()).all()

    # Mark notifications as read if requested
    if request.method == 'POST':
        for notification in unread_notifications:
            notification.is_read = True
        db.session.commit()
        flash("All notifications marked as read.")

    return render_template('unread_notifications.html', notifications=unread_notifications)


@user_interface.route('/view_read_notifications', methods=['GET'])
def view_read_notifications():
    if 'user_id' not in session:
        flash("You need to be logged in to view your notifications.")
        return redirect(url_for('user.login'))

    user_id = uuid.UUID(session['user_id'])
    read_notifications = Notification.query.filter_by(user_id=user_id, is_read=True).order_by(Notification.timestamp.desc()).all()

    return render_template('read_notifications.html', notifications=read_notifications)



@user_interface.route('/dialog/<uuid:round_id>', methods=['GET', 'POST'])
def dialog(round_id):
    if 'user_id' not in session:
        flash("You need to be logged in to access the dialog.")
        return redirect(url_for('user.login'))

    production_round = ProductionRound.query.get(round_id)
    if not production_round:
        flash("Invalid production round.")
        return redirect(url_for('user.home'))

    # Verify if the user is authorized to access the dialog
    user_id = uuid.UUID(session['user_id'])
    if (session['role'] == 'artist' and production_round.artist_id != user_id) or \
       (session['role'] == 'order_management_admin' and production_round.admin_id != user_id):
        flash("Unauthorized access to this dialog.")
        return redirect(url_for(f'user.{session["role"]}_dashboard'))

    if request.method == 'POST':
        message = request.form.get('message')
        uploaded_file = request.files.get('file')  # Handle file upload
        file_path = None

        if uploaded_file:
            filename = secure_filename(uploaded_file.filename)
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(file_path)

        if not message and not uploaded_file:
            flash("Message cannot be empty.")
        else:
            new_message = Dialog(
                production_round_id=production_round.id,
                sender_id=user_id,
                message=message if message else '[File Attached]',
                file_path=file_path if file_path else None,
                timestamp=datetime.now(timezone.utc)
            )
            db.session.add(new_message)
            db.session.commit()
            flash("Message sent.")

            # Determine the recipient of the notification
            recipient_id = production_round.artist_id if session['role'] == 'order_management_admin' else production_round.admin_id

            # Generate the dialog link
            dialog_link = url_for('user.dialog', round_id=production_round.id, _external=True)

            # Send a notification to the recipient with a link to the dialog
            Notification.send_notification(
                user_id=recipient_id,
                message=f"You have a new message in the production round for '{production_round.product.name}'.",
                link=dialog_link
            )

    # Fetch all messages in this dialog
    messages = Dialog.query.filter_by(production_round_id=production_round.id).order_by(Dialog.timestamp).all()

    return render_template('dialog.html', production_round=production_round, messages=messages)
