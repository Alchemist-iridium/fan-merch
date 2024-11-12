from flask import Flask, request, render_template, render_template_string, redirect, url_for, session, flash
import datetime
from main import Customer, Artist, PlatformAdministrator, Factory
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Define Flask app
app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Create example users, artists, factory, and admin
customer1 = Customer(user_id=1, name="Alice", email="alice@example.com")
customer1.password_hash = generate_password_hash("password123")
artist1 = Artist(user_id=2, name="Bob", email="bob@example.com")
artist1.password_hash = generate_password_hash("artistpass")
admin1 = PlatformAdministrator(user_id=3, name="Carol", email="carol@example.com")
admin1.password_hash = generate_password_hash("adminpass")
factory1 = Factory(factory_id=1, name="Best Factory", contact_info="factory@example.com")

# Set initial account balances
customer1.update_account_balance(500.0)

# Default stocking period
DEFAULT_STOCKING_PERIOD_DAYS = 30

# Web Routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/customers')
def view_customers():
    if 'user_id' not in session or session['role'] != 'Admin':
        flash("You need to be logged in as an Admin to view customers.")
        return redirect(url_for('login'))
    customers_info = [customer1]
    return render_template('customers.html', customers=customers_info)

@app.route('/artist_dashboard', methods=['GET', 'POST'])
def artist_dashboard():
    if 'user_id' not in session or session['role'] != 'Artist':
        flash("You need to be logged in as an Artist to access the dashboard.")
        return redirect(url_for('login'))
    artist = artist1  # In real scenario, use session user_id to fetch the artist

    if request.method == 'POST':
        # Artist uploads artwork for approval
        work_id = len(artist.works) + 1
        title = request.form['title']
        description = request.form['description']
        manufacturing_specs = request.form['manufacturing_specs']
        hard_tags = request.form['hard_tags'].split('#')
        soft_tags = request.form['soft_tags'].split('#') if request.form['soft_tags'] else []
        
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
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        else:
            image_path = ''
        
        # Add artist_id and artist_name to the submitted work dictionary
        new_work = artist.submit_work(
            work_id=work_id,
            title=title,
            description=description,
            manufacturing_specs=manufacturing_specs,
            hard_tags=hard_tags,
            soft_tags=soft_tags
        )
        new_work['image_path'] = image_path
        new_work['artist_id'] = artist.user_id
        new_work['artist_name'] = artist.name

        return redirect(url_for('artist_dashboard'))

    return render_template('artist_dashboard.html', artist=artist)


@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'Admin':
        flash("You need to be logged in as an Admin to access the dashboard.")
        return redirect(url_for('login'))

    search_results = []
    if request.method == 'POST':
        # Check if an artwork approval is being requested
        if 'work_id' in request.form:
            work_id = int(request.form['work_id'])
            for work in artist1.works:
                if work['work_id'] == work_id:
                    admin1.request_approval(work)
                    flash(f"Artwork with ID {work_id} has been approved.")
                    return redirect(url_for('admin_dashboard'))

        # Handle artwork disapproval
        elif 'disapprove_work_id' in request.form:
            work_id = int(request.form['disapprove_work_id'])
            reason = request.form['disapprove_reason']
            for work in artist1.works:
                if work['work_id'] == work_id:
                    work['approval_status'] = 'Disapproved'
                    work['disapproval_reason'] = reason
                    flash(f"Artwork with ID {work_id} has been disapproved for the following reason: {reason}")
                    return redirect(url_for('admin_dashboard'))

        # Handle search request for artworks (all statuses)
        elif 'keyword' in request.form:
            keyword = request.form['keyword'].lower()
            search_results = [work for work in artist1.works if
                              (keyword in work['title'].lower() or
                               keyword in work['description'].lower() or
                               any(keyword in tag.lower() for tag in work['hard_tags']) or
                               any(keyword in tag.lower() for tag in work['soft_tags']) or
                               keyword in artist1.name.lower() or
                               keyword in artist1.email.lower())]

    # Get all artworks for admin approval (only pending ones)
    artworks_info = [work for work in artist1.works if work['approval_status'] == 'Pending']
    return render_template('admin_dashboard.html', artworks=artworks_info, search_results=search_results)



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = None
        role = None

        # Identify user type
        if email == customer1.email and check_password_hash(customer1.password_hash, password):
            user = customer1
            role = 'Customer'
        elif email == artist1.email and check_password_hash(artist1.password_hash, password):
            user = artist1
            role = 'Artist'
        elif email == admin1.email and check_password_hash(admin1.password_hash, password):
            user = admin1
            role = 'Admin'

        if user:
            session['user_id'] = user.user_id
            session['role'] = role
            flash("Login successful!")

            # Redirect to the appropriate dashboard based on role
            if role == 'Admin':
                return redirect(url_for('admin_dashboard'))
            elif role == 'Artist':
                return redirect(url_for('artist_dashboard'))
            elif role == 'Customer':
                return redirect(url_for('home'))
        else:
            flash("Invalid email or password.")

    return render_template('login.html')

@app.route('/approve_artwork', methods=['GET', 'POST'])
def approve_artwork():
    if 'user_id' not in session or session['role'] != 'Admin':
        flash("You need to be logged in as an Admin to approve artwork.")
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Admin approves artwork
        work_id = int(request.form['work_id'])
        for work in artist1.works:
            if work['work_id'] == work_id:
                admin1.request_approval(work)
                flash(f"Artwork with ID {work_id} has been approved.")
                return redirect(url_for('approve_artwork'))

    # Fetch artworks that are pending approval
    artworks_info = artist1.works
    return render_template('admin_dashboard.html', artworks=artworks_info)


    artworks_info = artist1.works
    return render_template('admin_dashboard.html', artworks=artworks_info)


@app.route('/place_pre_order', methods=['GET', 'POST'])
def place_pre_order():
    if 'user_id' not in session or session['role'] != 'Customer':
        flash("You need to be logged in as a Customer to place a pre-order.")
        return redirect(url_for('login'))
    available_works = [work for work in artist1.works if work['approval_status'] == 'Approved']

    if request.method == 'POST':
        work_id = int(request.form['work_id'])
        quantity = int(request.form['quantity'])
        country = request.form['country']
        selected_work = next((work for work in available_works if work['work_id'] == work_id), None)
        if selected_work:
            pre_order = customer1.place_pre_order(artist_work=selected_work, quantity=quantity, process_option='Option A', country=country)
            return redirect(url_for('view_orders'))
        else:
            return render_template_string("""
                <p>No approved works available for pre-order</p>
                <a href="{{ url_for('home') }}">Back to Home</a>
            """)

    return render_template('place_pre_order.html', available_works=available_works)

@app.route('/view_notifications')
def view_notifications():
    if 'user_id' not in session or session['role'] != 'Customer':
        flash("You need to be logged in as a Customer to view notifications.")
        return redirect(url_for('login'))
    notifications = customer1.notifications
    return render_template('notifications.html', notifications=notifications)

@app.route('/view_orders')
def view_orders():
    if 'user_id' not in session or session['role'] != 'Customer':
        flash("You need to be logged in as a Customer to view orders.")
        return redirect(url_for('login'))
    orders_info = customer1.orders
    return render_template('orders.html', orders=orders_info)

@app.route('/manage_stock', methods=['GET', 'POST'])
def manage_stock():
    if 'user_id' not in session or session['role'] != 'Admin':
        flash("You need to be logged in as an Admin to manage stock.")
        return redirect(url_for('login'))
    if request.method == 'POST':
        # Simulating managing stock for customer1's first order
        if len(customer1.orders) > 0:
            customer1.stock_product(customer1.orders[0], stocking_period_days=DEFAULT_STOCKING_PERIOD_DAYS)
            return redirect(url_for('view_notifications'))
        else:
            return render_template_string("""
                <p>No orders to manage stock for</p>
                <a href="{{ url_for('home') }}">Back to Home</a>
            """)
    return render_template('manage_stock.html')

@app.route('/public_search', methods=['GET', 'POST'])
def public_search():
    search_results = []
    if request.method == 'POST':
        keyword = request.form['keyword'].lower()

        # Only search through approved artworks, including artist name and email
        search_results = [
            work for work in artist1.works
            if work['approval_status'] == 'Approved' and
               (keyword in work['title'].lower() or
                keyword in work['description'].lower() or
                any(keyword in tag.lower() for tag in work['hard_tags']) or
                any(keyword in tag.lower() for tag in work['soft_tags']) or
                keyword in artist1.name.lower() or
                keyword in artist1.email.lower())
        ]

    return render_template('public_search.html', search_results=search_results)




@app.route('/artist/<int:artist_id>')
def artist_public_page(artist_id):
    artist = next((a for a in [artist1] if a.user_id == artist_id), None)
    if artist:
        return render_template('artist_public_page.html', artist=artist)
    return redirect(url_for('home'))

@app.route('/product/<int:work_id>')
def product_page(work_id):
    work = next((w for w in artist1.works if w['work_id'] == work_id), None)
    if work:
        return render_template('product.html', work=work)
    return redirect(url_for('home'))


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash("You have been logged out.")
    return redirect(url_for('home'))

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
