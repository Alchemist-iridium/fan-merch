from flask import request, Blueprint,current_app, render_template, render_template_string, redirect, url_for, session, flash, current_app, send_file
import datetime
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from models import User, Artist, Customer, Artwork, Product, ArtworkApprovalAdmin, OrderManagementAdmin, SuperAdmin, DesignFile
from extensions import db


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

    return render_template('signup.html')


@user_interface.route('/signup_success/<string:name>')  # registration successful, welcome page
def signup_success(name):
    return render_template('signup_success.html', name=name)



@user_interface.route('/login', methods=['GET', 'POST'])
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
            if user.role == 'artwork_approval_admin':
                return redirect(url_for('user.artwork_approval_admin_dashboard'))
            elif user.role == 'order_management_admin':
                return redirect(url_for('user.order_management_admin_dashboard'))
            elif user.role == 'super_admin':
                return redirect(url_for('user.super_admin_dashboard'))
            elif user.role == 'artist':
                return redirect(url_for('user.artist_dashboard'))
            elif user.role == 'customer':
                return redirect(url_for('user.customer_home'))
        else:
            # If login fails, return to login page with error message
            error = "Wrong email or password"
            return render_template('login.html', error=error)
        
    return render_template('login.html')

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

    # Retrieve customer from database using session user_id
    customer = Customer.query.get(session['user_id'])

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

    return render_template('customer_home.html', customer=customer, search_results=search_results)

#The final result should be:
#customer_dashboard (view orders and historical purchase record)
#artist_dashboard (sign up)(check the historical artwork status and product)
#factory_dashboard (add with admin's approval) do we need it???
#admin_dashboard... There should be subclass on roles. For simplicity, not change the [customer,] For instance, the customer service staff

# Customer Dashboard
@user_interface.route('/customer_dashboard')
def customer_dashboard():
    if 'user_id' not in session or session['role'] != 'customer':
        flash("You need to be logged in as a Customer to access the dashboard.")
        return redirect(url_for('user.customer_home'))

    customer = Customer.query.get(session['user_id'])
    # Assuming you want to display orders and historical purchases
    orders = []  # Fetch customer's orders from the database here
    return render_template('customer_dashboard.html', customer=customer, orders=orders)


@user_interface.route('/artist_dashboard', methods=['GET', 'POST'])
def artist_dashboard():
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to access the dashboard.")
        return redirect(url_for('user.login'))

    artist = Artist.query.get(session['user_id'])
    
    # Handle submitting artwork (existing functionality)
    if request.method == 'POST':
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
                hard_tags=hard_tags_str,
                soft_tags=soft_tags_str,
                approval_status='Pending',
                artist_id=artist.id
            )
            db.session.add(new_artwork)
            db.session.commit()
            flash("Artwork submitted successfully for approval.")
        except ValueError as e:
            flash(str(e))

        return redirect(url_for('user.artist_dashboard'))

    # Retrieve artworks and products for displaying in the artist dashboard
    artworks = Artwork.query.filter_by(artist_id=artist.id).all()
    products = Product.query.filter(Product.artwork_id.in_([artwork.id for artwork in artworks])).all()

    return render_template('artist_dashboard.html', artist=artist, artworks=artworks, products=products)




# Artwork Approval Admin Dashboard
@user_interface.route('/artwork_approval_admin_dashboard', methods=['GET', 'POST'])
def artwork_approval_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'artwork_approval_admin':
        flash("You need to be logged in as an Artwork Approval Admin to access this dashboard.")
        return redirect(url_for('user.login'))

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
                    return redirect(url_for('user.artwork_approval_admin_dashboard'))
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
                    return redirect(url_for('user.artwork_approval_admin_dashboard'))

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
    return render_template('artwork_approval_admin_dashboard.html', artworks=artworks_info, search_results=search_results)

@user_interface.route('/order_management_admin_dashboard', methods=['GET'])
def order_management_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'order_management_admin':
        flash("You need to be logged in as an Order Management Admin to access this dashboard.")
        return redirect(url_for('user.login'))

    products = Product.query.filter_by(assigned_admin_id=session['user_id'], production_status='Approved').all()
    
    return render_template('order_management_admin_dashboard.html', products=products)



@user_interface.route('/super_admin_dashboard', methods=['GET', 'POST'])
def super_admin_dashboard():
    if 'user_id' not in session or session['role'] != 'super_admin':
        flash("You need to be logged in as a Super Admin to access this dashboard.")
        return redirect(url_for('user.login'))

    # Fetch all products with status 'Pending' for approval
    pending_products = Product.query.filter_by(production_status='Pending').all()

    # If no pending products, flash a message
    if not pending_products:
        flash("No products are currently pending approval.")

    return render_template('super_admin_dashboard.html', pending_products=pending_products)



@user_interface.route('/artist/<int:artist_id>')
def artist_public_page(artist_id):
    artist = User.query.get(artist_id)
    if artist and artist.role == 'artist':
        artworks = Artwork.query.filter_by(artist_id=artist.id, approval_status='Approved').all()
        return render_template('artist_public_page.html', artist=artist, artworks=artworks)
    return redirect(url_for('user.home'))

@user_interface.route('/artwork/<int:artwork_id>')
def artwork_page(artwork_id):
    work = Artwork.query.get(artwork_id)
    if work and work.approval_status == 'Approved':
        # Get all approved products for this artwork
        approved_products = Product.query.filter_by(artwork_id=artwork_id, production_status='Approved').all()

        return render_template('artwork_page.html', work=work, approved_products=approved_products)
    return redirect(url_for('user.home'))


@user_interface.route('/public_search', methods=['GET', 'POST'], endpoint='public_search')
def public_search():
    search_results = []
    user_role = session.get('role', None)

    if request.method == 'POST':
        keyword = request.form['keyword'].lower()

        # Base query for searching approved artworks based on the keyword
        base_query = Artwork.query.options(joinedload(Artwork.artist)).filter(
            (Artwork.approval_status == 'Approved') &
            (
                (Artwork.title.ilike(f"%{keyword}%")) |
                (Artwork.description.ilike(f"%{keyword}%")) |
                (Artwork.hard_tags.ilike(f"%{keyword}%")) |
                (Artwork.soft_tags.ilike(f"%{keyword}%"))
            )
        )
        search_results = base_query.all()  # Execute the query and store the results
        # public search is only going to be used by the public (unregistered users, customers and artists)
        # so we don't need to check for the user's role here
        # therefore, only approved artworks will be shown

    return render_template('public_search.html', search_results=search_results)

@user_interface.route('/update_product_status/<int:product_id>', methods=['POST'])
def update_product_status(product_id):
    if 'user_id' not in session or session.get('role') != 'order_management_admin':
        return redirect(url_for('user.login'))

    product = Product.query.get(product_id)
    if not product or product.assigned_admin_id != session['user_id']:
        flash("Unauthorized access.")
        return redirect(url_for('user.order_management_admin_dashboard'))

    new_status = request.form['status']
    if new_status in ["make_sample", "production", "detect_flaw", "stock delivery"]:
        product.status = new_status
        db.session.commit()
    return redirect(url_for('user.order_management_admin_dashboard'))


@user_interface.route('/admin_assign_product/<int:product_id>', methods=['POST'])
def admin_assign_product(product_id):
    if 'user_id' not in session or session.get('role') != 'super_admin':
        return redirect(url_for('user.login'))

    product = Product.query.get(product_id)
    admin_id = request.form['admin_id']
    admin = OrderManagementAdmin.query.get(admin_id)

    if product and admin:
        product.assigned_admin_id = admin_id
        db.session.commit()
        flash(f"Product ID {product_id} has been assigned to admin ID {admin_id}.")
    return redirect(url_for('user.super_admin_dashboard'))

@user_interface.route('/submit_product/<int:artwork_id>', methods=['GET', 'POST'])
def submit_product(artwork_id):
    if 'user_id' not in session or session['role'] != 'artist':
        flash("You need to be logged in as an Artist to submit a product.", 'error')
        return redirect(url_for('user.login'))

    artwork = Artwork.query.get(artwork_id)

    if request.method == 'POST':
        name = request.form['name']
        production_specs = request.form['production_specs']
        description = request.form['description']
        manufacture_type = request.form['manufacture_type']

        # Validate production_specs to be in artwork's manufacturing_specs
        valid_specs = artwork.manufacturing_specs.split(',')
        if production_specs not in valid_specs:
            # Redirect to the submission status page with failure
            return render_template(
                'submission_status.html',
                success=False,
                redirect_url=url_for('user.artist_dashboard')
            )

        try:
            # Create product with Pending status for Super Admin approval
            new_product = Product(
                name=name,
                production_specs=production_specs,
                description=description,
                manufacture_type=manufacture_type,
                artwork_id=artwork.id,
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
                'product_submission_status.html',
                success=True,
                redirect_url=url_for('user.artist_dashboard')
            )

        except Exception as e:
            # Handle any unexpected exceptions
            print(f"Error: {e}")  # For debugging purposes
            # Redirect to the submission status page with failure
            return render_template(
                'product_submission_status.html',
                success=False,
                redirect_url=url_for('user.artist_dashboard')
            )

    return render_template('submit_product.html', artwork=artwork)


@user_interface.route('/download_file/<int:file_id>')
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



@user_interface.route('/approve_product/<int:product_id>', methods=['POST'])
def approve_product(product_id):
    if 'user_id' not in session or session['role'] != 'super_admin':
        flash("You need to be logged in as a Super Admin to approve products.")
        return redirect(url_for('user.login'))

    product = Product.query.get(product_id)
    if product:
        product.production_status = 'Approved'  # Update status to approved
        db.session.commit()
        flash(f"Product ID {product.id} has been approved.")
    else:
        flash("Product not found.")

    return redirect(url_for('user.super_admin_dashboard'))

@user_interface.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
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

    return render_template('edit_product.html', product=product, flash_message=flash_message)


@user_interface.route('/product_public/<int:product_id>')
def product_public(product_id):
    product = Product.query.get(product_id)

    if not product or product.production_status != 'Approved':
        flash("Product is not available for public viewing.")
        return redirect(url_for('user.home'))

    return render_template('product_public.html', product=product)

