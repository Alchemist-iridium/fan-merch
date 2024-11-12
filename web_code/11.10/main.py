import datetime

class User:
    def __init__(self, user_id, name, email, role):
        self.user_id = user_id
        self.name = name
        self.email = email
        self.role = role
        self.account_balance = 0.0
        self.shipping_addresses = []

    def add_shipping_address(self, address):
        self.shipping_addresses.append(address)

    def update_account_balance(self, amount):
        self.account_balance += amount


class Customer(User):
    def __init__(self, user_id, name, email):
        super().__init__(user_id, name, email, role='Customer')
        self.orders = []
        self.delivery_orders = []
        self.notifications = []
        self.stocked_products = []

    def place_pre_order(self, artist_work, quantity, process_option, country):
        pre_order = {
            'work_id': artist_work['work_id'],
            'quantity': quantity,
            'process_option': process_option,
            'country': country,
            'status': 'Active',
            'stocking_start_date': None
        }
        self.orders.append(pre_order)
        return pre_order

    def place_delivery_order(self, order_ids, address):
        combined_order = {
            'order_ids': order_ids,
            'address': address,
            'status': 'Pending'
        }
        self.delivery_orders.append(combined_order)
        return combined_order

    def withdraw_order(self, pre_order_id):
        for order in self.orders:
            if order['work_id'] == pre_order_id and order['status'] == 'Active':
                order['status'] = 'Withdrawn'
                return True
        return False

    def receive_notification(self, message):
        self.notifications.append(message)

    def stock_product(self, product, stocking_period_days):
        product['stocking_start_date'] = datetime.datetime.now()
        product['stocking_period'] = stocking_period_days
        self.stocked_products.append(product)

    def check_stocking_periods(self):
        current_date = datetime.datetime.now()
        for product in list(self.stocked_products):
            stocking_end_date = product['stocking_start_date'] + datetime.timedelta(days=product['stocking_period'])
            grace_period_end_date = stocking_end_date + datetime.timedelta(days=7)  # Grace period of 7 days
            if current_date >= stocking_end_date and current_date < grace_period_end_date:
                self.receive_notification(f"Stocking period expired for product {product['work_id']}. You have until {grace_period_end_date} to buy it back with a penalty.")
            elif current_date >= grace_period_end_date:
                self.stocked_products.remove(product)
                self.receive_notification(f"Product {product['work_id']} has been deleted from the system after grace period.")

    def buy_back_product_with_penalty(self, product_id, penalty_fee):
        for product in self.stocked_products:
            if product['work_id'] == product_id:
                total_cost = penalty_fee
                if self.account_balance >= total_cost:
                    self.update_account_balance(-total_cost)
                    self.receive_notification(f"You have successfully bought back product {product_id} with a penalty fee of {penalty_fee}.")
                    self.stocked_products.remove(product)
                    return True
                else:
                    self.receive_notification(f"Insufficient funds to buy back product {product_id}.")
                    return False
        return False


class Artist(User):
    def __init__(self, user_id, name, email):
        super().__init__(user_id, name, email, role='Artist')
        self.works = []

    def submit_work(self, work_id, title, description, manufacturing_specs):
        work = {
            'work_id': work_id,
            'title': title,
            'description': description,
            'manufacturing_specs': manufacturing_specs,
            'approval_status': 'Pending'
        }
        self.works.append(work)
        return work

    def publish_work(self, work_id):
        for work in self.works:
            if work['work_id'] == work_id and work['approval_status'] == 'Approved':
                return f"Work {work_id} has been published for sale."
        return f"Work {work_id} cannot be published as it is not approved."

    def receive_notification(self, message):
        print(f"Notification for Artist {self.name}: {message}")

    def update_customers(self, customers, update_message):
        for customer in customers:
            customer.receive_notification(update_message)


class Factory:
    def __init__(self, factory_id, name, contact_info):
        self.factory_id = factory_id
        self.name = name
        self.contact_info = contact_info
        self.orders = []
        self.product_types = {}

    def add_product_type(self, product_type, base_price):
        self.product_types[product_type] = base_price

    def provide_pricing(self, manufacturing_requirements, product_type):
        if product_type in self.product_types:
            base_price = self.product_types[product_type]
        else:
            base_price = 10  # Default base price if product type is unknown
        price_per_unit = base_price * (1 + len(manufacturing_requirements.split(',')) * 0.05)
        return price_per_unit

    def produce_sample(self, order_details):
        # Produce sample product based on order details
        sample_status = "Sample produced successfully"
        return sample_status

    def communicate_progress(self, admin, progress_message):
        admin.receive_factory_update(progress_message)


class PlatformAdministrator(User):
    def __init__(self, user_id, name, email):
        super().__init__(user_id, name, email, role='Admin')
        self.orders = []
        self.factory_updates = []

    def manage_order(self, order):
        self.orders.append(order)
        return "Order has been managed by the platform administrator."

    def receive_factory_update(self, update_message):
        self.factory_updates.append(update_message)

    def oversee_payment(self, customer, amount):
        if customer.account_balance >= amount:
            customer.update_account_balance(-amount)
            return True
        return False

    def facilitate_communication(self, artist, customers, message):
        artist.update_customers(customers, message)

    def request_approval(self, work):
        # Simulate contacting IP company and getting approval
        work['approval_status'] = 'Approved'
        return f"Work {work['work_id']} has been approved."

    def send_approval_result(self, artist, work):
        artist.receive_notification(f"Work {work['work_id']} approval status: {work['approval_status']}")
