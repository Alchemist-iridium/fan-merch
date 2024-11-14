from flask import Flask, request, render_template, render_template_string, redirect, url_for, session, flash
import datetime
from main import db, User, Artwork, create_user
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload

# Define Flask app
app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///art_platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database with SQLAlchemy
db.init_app(app)

# Default stocking period
DEFAULT_STOCKING_PERIOD_DAYS = 30

# Web Routes
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']  # Either "Customer" or "Artist"
        
        # Check if the email is already in use
        if User.query.filter_by(email=email).first():
            flash('Email address already registered')
            return redirect(url_for('signup'))

        try:
            # Hash the password before storing it in the database
            password_hash = generate_password_hash(password)
            
            # Create and add the user to the database
            new_user = User(name=name, email=email, password_hash=password_hash, role=role)
            db.session.add(new_user)
            db.session.commit()

            flash('Account successfully created! Please log in.')
            return redirect(url_for('login'))
        except ValueError as e:
            flash(str(e))
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Query the user from the database
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = user.role
            flash("Login successful!")

            # Redirect to the appropriate dashboard based on role
            if user.role == 'Admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'Artist':
                return redirect(url_for('artist_dashboard'))
            elif user.role == 'Customer':
                return redirect(url_for('home'))
        else:
            flash("Invalid email or password.")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash("You have been logged out.")
    return redirect(url_for('home'))

#the dashboard part. Right now there are dashboard for artist and admin.
#The final result should be customer_dashboard (sign up)(view orders and historical purchase record)
#artist_dashboard (sign up)(check the historical artwork status and product)
#factory_dashboard (add with admin's approval)
#admin_dashboard... There should be subclass on roles. For simplicity, not change the [customer,] For instance, the customer service staff



@app.route('/artist_dashboard', methods=['GET', 'POST'])
def artist_dashboard():
    if 'user_id' not in session or session['role'] != 'Artist':
        flash("You need to be logged in as an Artist to access the dashboard.")
        return redirect(url_for('login'))

    artist = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        # Artist uploads artwork for approval
        title = request.form['title']
        description = request.form['description']
        manufacturing_specs = request.form['manufacturing_specs']
        hard_tags_raw = request.form['hard_tags']
        soft_tags_raw = request.form.get('soft_tags', "")

        # Split the tags by '#', remove empty tags, and strip whitespace
        hard_tags = [tag.strip() for tag in hard_tags_raw.split('#') if tag.strip()]
        soft_tags = [tag.strip() for tag in soft_tags_raw.split('#') if tag.strip()]

        # Convert the lists to strings for storage
        hard_tags_str = '#'.join(hard_tags)
        soft_tags_str = '#'.join(soft_tags)

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
        
        # Create new artwork
        try:
            new_artwork = Artwork(
                title=title,
                description=description,
                image_path=image_path,
                manufacturing_specs=manufacturing_specs,
                hard_tags=hard_tags_str,    # Store the string representation of hard tags
                soft_tags=soft_tags_str,    # Store the string representation of soft tags
                approval_status='Pending',
                artist_id=artist.id
            )
            db.session.add(new_artwork)
            db.session.commit()
            flash("Artwork submitted successfully for approval.")
        except ValueError as e:
            flash(str(e))

        return redirect(url_for('artist_dashboard'))

    artworks = Artwork.query.filter_by(artist_id=artist.id).all()
    return render_template('artist_dashboard.html', artist=artist, artworks=artworks)


@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'Admin':
        flash("You need to be logged in as an Admin to access the dashboard.")
        return redirect(url_for('login'))
    
    search_results = []
    if request.method == 'POST':
        # Check if an artwork approval is being requested
        if 'id' in request.form:
            artwork_id = request.form['id']
            
            # Validate if artwork_id is not empty and is a digit
            if artwork_id and artwork_id.isdigit():
                artwork_id = int(artwork_id)
                artwork = Artwork.query.get(artwork_id)
                
                if artwork and artwork.approval_status == 'Pending':
                    artwork.approval_status = 'Approved'
                    db.session.commit()
                    flash(f"Artwork with ID {artwork_id} has been approved.")
                    return redirect(url_for('admin_dashboard'))
            else:
                flash("Invalid artwork ID. Please try again.")

        # Handle artwork disapproval
        elif 'disapprove_id' in request.form:
            artwork_id = request.form['disapprove_id']
            
            # Validate if artwork_id is not empty and is a digit
            if artwork_id and artwork_id.isdigit():
                artwork_id = int(artwork_id)
                reason = request.form['disapprove_reason']
                artwork = Artwork.query.get(artwork_id)
                if artwork and artwork.approval_status == 'Pending':
                    artwork.approval_status = 'Disapproved'
                    artwork.disapproval_reason = reason
                    db.session.commit()
                    flash(f"Artwork with ID {artwork_id} has been disapproved for the following reason: {reason}")
                    return redirect(url_for('admin_dashboard'))

        # Handle search request for artworks (all statuses)
        elif 'keyword' in request.form:
            keyword = request.form['keyword'].lower()
            search_results = Artwork.query.options(joinedload(Artwork.artist)).filter(
                (Artwork.title.ilike(f"%{keyword}%")) |
                (Artwork.description.ilike(f"%{keyword}%")) |
                (Artwork.hard_tags.ilike(f"%{keyword}%")) |
                (Artwork.soft_tags.ilike(f"%{keyword}%"))
            ).all()

    # Get all artworks for admin approval (only pending ones)
    artworks_info = Artwork.query.filter_by(approval_status='Pending').all()
    return render_template('admin_dashboard.html', artworks=artworks_info, search_results=search_results)

@app.route('/customers')    #should be a function in the customer_service_dashboard, not implemented yet
def view_customers():
    if 'user_id' not in session or session['role'] != 'Admin':
        flash("You need to be logged in as an Admin to view customers.")
        return redirect(url_for('login'))
    
    customers_info = User.query.filter_by(role='Customer').all()
    return render_template('customers.html', customers=customers_info)


@app.route('/place_pre_order', methods=['GET', 'POST'])
def place_pre_order():
    if 'user_id' not in session or session['role'] != 'Customer':
        flash("You need to be logged in as a Customer to place a pre-order.")
        return redirect(url_for('login'))

    customer = User.query.get(session['user_id'])
    available_works = Artwork.query.filter_by(approval_status='Approved').all()

    if request.method == 'POST':
        artwork_id = request.form['id']
        
        # Validate if artwork_id is not empty and is a digit
        if artwork_id and artwork_id.isdigit():
            artwork_id = int(artwork_id)
            quantity = int(request.form['quantity'])
            country = request.form['country']
            selected_work = Artwork.query.get(artwork_id)

            if selected_work and selected_work.approval_status == 'Approved':
                # Simulate placing an order (example implementation, you might need to expand this)
                flash(f"Pre-order placed for artwork ID {artwork_id}.")
                return redirect(url_for('view_orders'))
        
        flash("Invalid artwork ID. Please try again.")
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

    customer = User.query.get(session['user_id'])
    notifications = customer.notifications  # Assuming `notifications` is a relationship or an attribute
    return render_template('notifications.html', notifications=notifications)

@app.route('/view_orders')
def view_orders():
    if 'user_id' not in session or session['role'] != 'Customer':
        flash("You need to be logged in as a Customer to view orders.")
        return redirect(url_for('login'))

    customer = User.query.get(session['user_id'])
    orders_info = customer.orders  # Assuming `orders` is a relationship or an attribute
    return render_template('orders.html', orders=orders_info)

@app.route('/manage_stock', methods=['GET', 'POST'])
def manage_stock():
    if 'user_id' not in session or session['role'] != 'Admin':
        flash("You need to be logged in as an Admin to manage stock.")
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Simulating managing stock for the customer's first order
        customer = User.query.filter_by(role='Customer').first()
        if customer and len(customer.orders) > 0:
            customer.stock_product(customer.orders[0], stocking_period_days=DEFAULT_STOCKING_PERIOD_DAYS)
            db.session.commit()
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

        # Only search through approved artworks
        search_results = Artwork.query.options(joinedload(Artwork.artist)).filter(
            (Artwork.approval_status == 'Approved') &
            (
                (Artwork.title.ilike(f"%{keyword}%")) |
                (Artwork.description.ilike(f"%{keyword}%")) |
                (Artwork.hard_tags.ilike(f"%{keyword}%")) |
                (Artwork.soft_tags.ilike(f"%{keyword}%"))
            )
        ).all()

    return render_template('public_search.html', search_results=search_results)



@app.route('/artist/<int:artist_id>')
def artist_public_page(artist_id):
    artist = User.query.get(artist_id)
    if artist and artist.role == 'Artist':
        artworks = Artwork.query.filter_by(artist_id=artist.id, approval_status='Approved').all()
        return render_template('artist_public_page.html', artist=artist, artworks=artworks)
    return redirect(url_for('home'))

@app.route('/artwork/<int:artwork_id>')
def artwork_page(artwork_id):
    work = Artwork.query.get(artwork_id)
    if work and work.approval_status == 'Approved':
        return render_template('artwork_page.html', work=work)
    return redirect(url_for('home'))


# Main Method to Run Flask
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
        # Uncomment to initialize with some sample data
        # initialize_sample_data()
    app.run(debug=True)