from flask import Flask, request, render_template_string, redirect, url_for
import datetime
from main import Customer, Artist, PlatformAdministrator, Factory

# Define Flask app
app = Flask(__name__)

# Create example users, artists, factory, and admin
customer1 = Customer(user_id=1, name="Alice", email="alice@example.com")
artist1 = Artist(user_id=2, name="Bob", email="bob@example.com")
admin1 = PlatformAdministrator(user_id=3, name="Carol", email="carol@example.com")
factory1 = Factory(factory_id=1, name="Best Factory", contact_info="factory@example.com")

# Set initial account balances
customer1.update_account_balance(500.0)

# Default stocking period
DEFAULT_STOCKING_PERIOD_DAYS = 30

# Web Routes
@app.route('/')
def home():
    return render_template_string('''
        <h1>Welcome to the Fan Merch Platform</h1>
        <a href="{{ url_for('view_customers') }}">View Customers</a><br>
        <a href="{{ url_for('view_artists') }}">View Artists</a><br>
        <a href="{{ url_for('place_pre_order') }}">Place Pre-Order</a><br>
        <a href="{{ url_for('view_notifications') }}">View Notifications</a><br>
        <a href="{{ url_for('view_orders') }}">View Orders</a><br>
        <a href="{{ url_for('manage_stock') }}">Manage Stock</a><br>
        <a href="{{ url_for('approve_artwork') }}">Approve Artwork</a><br>
    ''')

@app.route('/customers')
def view_customers():
    customers_info = ""
    for customer in [customer1]:
        customers_info += f"<p>{customer.name} - Balance: ${customer.account_balance}</p>"
    return render_template_string('''
        <h1>Customers</h1>
        {{ customers_info|safe }}
        <a href="{{ url_for('home') }}">Back to Home</a>
    ''', customers_info=customers_info)

@app.route('/artists', methods=['GET', 'POST'])
def view_artists():
    if request.method == 'POST':
        # Artist uploads artwork for approval
        work_id = len(artist1.works) + 1
        title = request.form['title']
        description = request.form['description']
        manufacturing_specs = request.form['manufacturing_specs']
        new_work = artist1.submit_work(work_id=work_id, title=title, description=description, manufacturing_specs=manufacturing_specs)
        return redirect(url_for('view_artists'))

    artists_info = ""
    for artist in [artist1]:
        artists_info += f"<p>{artist.name}</p>"
    return render_template_string('''
        <h1>Artists</h1>
        {{ artists_info|safe }}
        <h2>Upload Artwork for Approval</h2>
        <form method="post">
            Title: <input type="text" name="title" required><br>
            Description: <input type="text" name="description" required><br>
            Manufacturing Specs: <input type="text" name="manufacturing_specs" required><br>
            <input type="submit" value="Upload Artwork">
        </form>
        <a href="{{ url_for('home') }}">Back to Home</a>
    ''', artists_info=artists_info)

@app.route('/approve_artwork', methods=['GET', 'POST'])
def approve_artwork():
    if request.method == 'POST':
        # Admin approves artwork
        work_id = int(request.form['work_id'])
        for work in artist1.works:
            if work['work_id'] == work_id:
                admin1.request_approval(work)
                return redirect(url_for('approve_artwork'))

    artworks_info = ""
    for work in artist1.works:
        artworks_info += f"<p>Work ID: {work['work_id']}, Title: {work['title']}, Status: {work['approval_status']}</p>"
    return render_template_string('''
        <h1>Approve Artwork</h1>
        {{ artworks_info|safe }}
        <h2>Approve an Artwork</h2>
        <form method="post">
            Work ID to Approve: <input type="text" name="work_id" required><br>
            <input type="submit" value="Approve Artwork">
        </form>
        <a href="{{ url_for('home') }}">Back to Home</a>
    ''', artworks_info=artworks_info)

@app.route('/place_pre_order', methods=['GET', 'POST'])
def place_pre_order():
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

    return render_template_string('''
        <h1>Place Pre-Order</h1>
        <form method="post">
            <label for="work_id">Select Artwork:</label>
            <select name="work_id" id="work_id" required>
                {% for work in available_works %}
                    <option value="{{ work['work_id'] }}">{{ work['title'] }}</option>
                {% endfor %}
            </select><br>
            Quantity: <input type="text" name="quantity" required><br>
            Country: <input type="text" name="country" required><br>
            <input type="submit" value="Place Order">
        </form>
        <a href="{{ url_for('home') }}">Back to Home</a>
    ''', available_works=available_works)

@app.route('/view_notifications')
def view_notifications():
    notifications = ""
    for notification in customer1.notifications:
        notifications += f"<p>{notification}</p>"
    return render_template_string('''
        <h1>Notifications</h1>
        {{ notifications|safe }}
        <a href="{{ url_for('home') }}">Back to Home</a>
    ''', notifications=notifications)

@app.route('/view_orders')
def view_orders():
    orders_info = ""
    for order in customer1.orders:
        orders_info += f"<p>Order for work ID {order['work_id']} - Quantity: {order['quantity']} - Status: {order['status']}</p>"
    return render_template_string('''
        <h1>Orders</h1>
        {{ orders_info|safe }}
        <a href="{{ url_for('home') }}">Back to Home</a>
    ''', orders_info=orders_info)

@app.route('/manage_stock', methods=['GET', 'POST'])
def manage_stock():
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
    return render_template_string('''
        <h1>Manage Stock</h1>
        <form method="post">
            <input type="submit" value="Manage Stock">
        </form>
        <a href="{{ url_for('home') }}">Back to Home</a>
    ''')

if __name__ == '__main__':
    app.run(debug=True)
