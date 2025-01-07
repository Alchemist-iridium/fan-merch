from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
from app.extensions import db
from datetime import datetime, timezone
import uuid
from sqlalchemy.dialects.postgresql import UUID
from flask import url_for, current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.sql import func
import logging
import json
from sqlalchemy.ext.mutable import MutableList

from sqlalchemy.orm import Session


from sqlalchemy import Column, String, Integer, Boolean, Float, DateTime, ForeignKey, Text



# Define Models

# User Model
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)  # Index added
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='unregistered')  # defaut value is unregistered, "customer", "artist", "admin"
    account_balance = db.Column(db.Float, default=0.0)

    artworks = db.relationship("Artwork", back_populates="artist", lazy=True)
    notifications = db.relationship("Notification", back_populates="user", lazy=True)

    __mapper_args__ = {
        'polymorphic_identity': 'user',
        'polymorphic_on': role
    }

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def update_account_balance(self, amount):
        self.account_balance += amount



# Admin Model
class Admin(User):
    __tablename__ = 'admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'admin',
    }


# Artwork Approval Admin Model
class ArtworkApprovalAdmin(Admin):
    __tablename__ = 'artwork_approval_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'artwork_approval_admin',
    }

    def approve_artwork(self, artwork):
        artwork.approval_status = 'Approved'
        db.session.commit()

    def disapprove_artwork(self, artwork, reason):
        artwork.approval_status = 'Disapproved'
        artwork.disapproval_reason = reason
        db.session.commit()


# Order Management Admin Model
class OrderManagementAdmin(Admin):
    __tablename__ = 'order_management_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)
    main_production_species = db.Column(db.String(200), nullable=False, default="general")

    __mapper_args__ = {
        'polymorphic_identity': 'order_management_admin',
    }

    products_managed = db.relationship('Product', back_populates='managing_admin', lazy=True, foreign_keys='Product.assigned_admin_id')
    production_rounds = db.relationship('ProductionRound', back_populates='admin', lazy=True, foreign_keys='ProductionRound.admin_id')


    def get_product_count(self):
        return len(self.products_managed)

    def update_product_status(self, product, status):
        if product.assigned_admin_id != self.id:
            raise PermissionError("This product is not assigned to this admin.")
        product.production_status = status
        db.session.commit()

    def process_refund(self, order, refund_amount=None):
        if refund_amount is None:
            order.is_refunded = True
            order.refund_amount = order.amount_paid
        else:
            if refund_amount > order.amount_paid:
                raise ValueError("Refund amount cannot exceed amount paid.")
            order.is_refunded = True
            order.refund_amount = refund_amount
        db.session.commit()

    def process_order_transfer(self, order, new_customer):
        if order.is_transferred:
            raise ValueError("Order has already been transferred.")
        order.is_transferred = True
        order.new_customer_id = new_customer.id
        # Refund original customer
        order.customer.account_balance += order.amount_paid
        # Charge new customer
        new_customer.account_balance -= order.amount_paid
        db.session.commit()


# Product Approval Admin Model
class ProductApprovalAdmin(Admin):
    __tablename__ = 'product_approval_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'product_approval_admin',
    }

    def approve_product(self, product):
        """Approve a product."""
        product.production_status = 'Approved'
        db.session.commit()

    def disapprove_product(self, product, reason):
        """Disapprove a product with a reason."""
        product.production_status = 'Disapproved'
        product.disapproval_reason = reason
        db.session.commit()

    def pick_product(self, product):
        """Assign the product to the admin's workspace by picking it."""
        product.picked_by_admin_id = self.id
        db.session.commit()

    def unpick_product(self, product):
        """Remove the product from the admin's workspace."""
        product.picked_by_admin_id = None
        db.session.commit()



# Delivery admin, who is going to have the delivery order's package assigned
class DeliveryAdmin(Admin):
    __tablename__ = 'delivery_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'delivery_admin',
    }


    # Relationships
    delivery_orders = db.relationship("DeliveryOrder", back_populates="delivery_admin", lazy=True)

    # Functions
    def assign_packages(self, delivery_order):
        # Implementation for assigning packages to a delivery order
        pass

    def update_delivery_status(self, package_id, status):
        # Implementation for updating delivery status
        pass





# Artist model
class Artist(User):
    __tablename__ = 'artists'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)
    bio = db.Column(db.String(500), nullable=True)

    artworks = db.relationship("Artwork", back_populates="artist", lazy=True)
    followers = db.relationship("Customer", secondary="followers", back_populates="followed_artists")
    products = db.relationship("Product", back_populates="artist", lazy=True)
    production_rounds = db.relationship("ProductionRound", back_populates="artist", lazy=True)

    wallet_balance = db.Column(db.Float, default=0.0)
    # wallet balance is only for testing and development
    # in business level it is too risky...

    payouts = db.relationship("Payout", back_populates="artist", lazy=True)
    
    __mapper_args__ = {
        'polymorphic_identity': 'artist',
    }



class Customer(User):
    __tablename__ = 'customers'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)

    # wallet balance is for testing/development only
    wallet_balance = db.Column(db.Float, default=0.0)


    cart = db.relationship(
        "Cart",
        back_populates="customer",
        uselist=False,  # Ensures one-to-one relationship
        cascade="all, delete-orphan"  # Automatically handles cart lifecycle
    )

    # Relationships
    items = db.relationship("Item", back_populates="customer", lazy=True)
    delivered_items = db.relationship("DeliveredItem", back_populates="customer", lazy=True)

    # Updated to point to your new approach


    orders = db.relationship("ItemOrder", back_populates="customer", lazy="dynamic")  # For ItemOrder
    refund_item_orders = db.relationship("RefundItemOrder", back_populates="customer", lazy="dynamic")  # For RefundItemOrder
    transfer_item_orders_outgoing = db.relationship(
        "TransferItemOrder",
        foreign_keys="[TransferItemOrder.from_customer_id]",
        back_populates="from_customer_relationship",
        lazy="dynamic"
    )
    transfer_item_orders_incoming = db.relationship(
        "TransferItemOrder",
        foreign_keys="[TransferItemOrder.to_customer_id]",
        back_populates="to_customer_relationship",
        lazy="dynamic"
    )
    delivery_orders = db.relationship("DeliveryOrder", back_populates="customer", lazy="dynamic")  # For DeliveryOrder


    # Removed payments and refund_transactions relationships since 
    # we store payment/refund fields directly on orders now.

    # Optional: favorite_artworks, followed_artists remain as is
    favorite_artworks = db.relationship("Artwork", secondary="favorites", back_populates="favorited_by")
    followed_artists = db.relationship("Artist", secondary="followers", back_populates="followers")

    __mapper_args__ = {
        'polymorphic_identity': 'customer',
    }

    # -------------------------------------------------------------------
    # FUNCTIONS
    # -------------------------------------------------------------------

    def create_item_order(self, cart_items, payment_method):
        """
        Creates an ItemOrder (with its own payment info) for the customer.
        
        :param cart_items: Dictionary {production_round_id: quantity}
        :param payment_method: String for the payment method (e.g., "wallet", "credit_card")
        :return: The created & paid ItemOrder instance
        """
        from sqlalchemy.orm import Session

        session = Session.object_session(self)

        # Calculate total amount based on ProductionRound prices
        total_amount = 0
        for production_round_id, quantity in cart_items.items():
            production_round = ProductionRound.query.get(production_round_id)
            if not production_round or not production_round.is_published:
                raise ValueError(f"Invalid production round: {production_round_id}")
            total_amount += production_round.price * quantity

        # Create an ItemOrder (assumes ItemOrder has columns: payment_method, payment_status, etc.)
        item_order = ItemOrder(
            customer_id=self.id,
            total_amount=total_amount,
            payment_method=payment_method,
            payment_status="unpaid",  # we'll set it to "paid" once we confirm
        )
        session.add(item_order)

        # Create actual Items and ItemOrderItems
        for production_round_id, quantity in cart_items.items():
            production_round = ProductionRound.query.get(production_round_id)
            for _ in range(quantity):
                # Create the Item (base polymorphic: type="item")
                item = Item(
                    production_round_id=production_round_id,
                    customer_id=self.id
                )
                session.add(item)

                # Link Item to the order via ItemOrderItem
                item_order_item = ItemOrderItem(
                    order=item_order,
                    item=item,
                    item_type="item",
                    production_round_id=production_round_id,
                    product_name=production_round.product.name
                )
                session.add(item_order_item)

        # Now handle payment on the order itself
        self._pay_for_item_order(item_order, total_amount, payment_method)

        # Commit all changes
        session.commit()
        return item_order

    def _pay_for_item_order(self, item_order, total_amount, payment_method):
        """
        Internal helper to finalize payment on the ItemOrder itself.
        Writes to item_order.payment_* fields, 
        and optionally adjusts Customer wallet if 'wallet' is used.
        """
        from sqlalchemy.orm import Session
        session = Session.object_session(self)

        if payment_method == "wallet":
            if self.wallet_balance < total_amount:
                raise ValueError("Insufficient wallet balance.")
            self.wallet_balance -= total_amount
            session.add(self)

        # Mark the order as paid
        item_order.payment_status = "paid"
        item_order.payment_timestamp = datetime.now()
        session.add(item_order)

        session.flush()  # or commit at this point if desired

    @property
    def all_order_items(self):
        """
        Convenience property to list all order line-items 
        (ItemOrderItem) from all of this customer's orders.
        """
        return [ioi for o in self.item_orders for ioi in o.order_items]

    def request_refund(self, items):
        """
        Implementation for requesting a refund, if you have a RefundItemOrder approach 
        or linking items to AbandonedItem. 
        This is just a placeholder.
        """
        pass

    def create_delivery_order(self, items, address):
        """
        Implementation for creating a DeliveryOrder (which also has 
        payment columns if you store them there).
        """
        pass


    




# Artwork model
class Artwork(db.Model):
    __tablename__ = 'artworks'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    image_path = db.Column(db.String(300), nullable=False)
    manufacturing_specs = db.Column(db.String(300), nullable=True)
    hard_tags = db.Column(db.String(300), nullable=False)
    soft_tags = db.Column(db.String(300), nullable=True)
    approval_status = db.Column(db.String(50), nullable=False, default='Pending')
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False, index=True)  # Index added
    disapproval_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    approval_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artwork_approval_admins.id'), nullable=True)  # New attribute for recording approval admin ID
    picked_by_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artwork_approval_admins.id'), nullable=True)  # New field for picking

    

    # Relationships
    artist = db.relationship("Artist", back_populates="artworks", foreign_keys=[artist_id])
    products = db.relationship("Product", back_populates="artwork", lazy=True)
    favorited_by = db.relationship("Customer", secondary="favorites", back_populates="favorite_artworks")

    # Relationship on who is working on the artwork approval process
    picked_by_admin = db.relationship("ArtworkApprovalAdmin", foreign_keys=[picked_by_admin_id])

    # Relationship to access the admin who approved/disapproved the artwork
    approval_admin = db.relationship("ArtworkApprovalAdmin", foreign_keys=[approval_admin_id], backref="approved_artworks", lazy=True)

    # Association tables for many-to-many relationships
favorites = db.Table(
    'favorites',
    db.Column('customer_id', UUID(as_uuid=True), db.ForeignKey('customers.id')),
    db.Column('artwork_id', UUID(as_uuid=True), db.ForeignKey('artworks.id'))
)

followers = db.Table(
    'followers',
    db.Column('customer_id', UUID(as_uuid=True), db.ForeignKey('customers.id')),
    db.Column('artist_id', UUID(as_uuid=True), db.ForeignKey('artists.id'))
)




# Product Model
class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(200), nullable=False)
    production_specs = db.Column(db.String(200), nullable=False)    #manufacture type
    manufacture_type = db.Column(db.String(50), nullable=False) # artist/platform arrange
    production_status = db.Column(db.String(50), nullable=False, default='Pending')
    display_status = db.Column(db.String(50), nullable=False, default='not display')
    
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    artwork_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artworks.id'), nullable=False, index=True)  # Index added
    assigned_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('order_management_admins.id'), nullable=True)
    product_approval_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_approval_admins.id'), nullable=True)
    picked_by_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_approval_admins.id'), nullable=True)

    introduction = db.Column(db.Text, nullable=True)
    disapproval_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    artist_controlled = db.Column(db.Boolean, default=True)  # Determines who initiates production rounds


    # Relationships
    artwork = db.relationship("Artwork", back_populates="products")
    artist = db.relationship("Artist", back_populates="products", foreign_keys=[artist_id])
    managing_admin = db.relationship("OrderManagementAdmin", back_populates="products_managed", foreign_keys=[assigned_admin_id])
    product_approval_admin = db.relationship("ProductApprovalAdmin", foreign_keys=[product_approval_admin_id])
    picked_by_admin = db.relationship("ProductApprovalAdmin", foreign_keys=[picked_by_admin_id])
    production_rounds = db.relationship("ProductionRound", back_populates="product", lazy=True)

    design_files = db.relationship("DesignFile", back_populates="product", cascade="all, delete-orphan")

    # Method to toggle the display status of the product
    def toggle_display_status(self):
        """Toggle the display status between 'on display' and 'not display'."""
        if self.display_status == "not display":
            self.display_status = "on display"
        else:
            self.display_status = "not display"
        db.session.commit()
        return f"Product {self.id} display status updated to {self.display_status}"
    
    def toggle_control(self):
        """Toggle the production control mechanism."""
        self.artist_controlled = not self.artist_controlled
        db.session.commit()

# transactional system have a common model
# although I'm still not quite sure why we need this?


# The active production round has the stage of ["initialize", "waiting", "sample", "production"]
# The not active production round has the stage of ["stocking", "abandon"].



    # Stores production stage goals as a JSON string
    # the stage goal is like that in the co-fund systems
    # the unit cost of product will drop and to attract more customer
    # hmm... just to say...
    # will be displayed on the production (+round) page and affect the production and stocking (warehouse) system a little bit.


class ProductionRound(db.Model):
    __tablename__ = 'production_rounds'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False, index=True)
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artists.id'), nullable=False)
    admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('order_management_admins.id'), nullable=True)

    price = db.Column(db.Float, nullable=True)
    min_production_size = db.Column(db.Integer, nullable=False, default=0)
    max_waiting_time = db.Column(db.DateTime, nullable=False)
    is_published = db.Column(db.Boolean, default=False)

    delivery_point = db.Column(db.Integer, nullable=False, default=1)
    # to calculate the cost for the delivery order, different item could have different value
    # need update to the display and modification

    stage = db.Column(
        db.String(50),
        nullable=False,
        default="initialize"
    )

    is_active = db.Column(db.Boolean, default=True)
    # The active production round has the stage of ["initialize", "waiting", "sample", "production"]
    # The not active production round has the stage of ["stocking", "abandon"].


    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    # Stores production stage goals as a JSON string
    # the stage goal is like that in the co-fund systems
    # the unit cost of product will drop and to attract more customer
    # hmm... just to say...
    # will be displayed on the production (+round) page and affect the production and stocking (warehouse) system a little bit.

    production_goals = db.Column(db.Text, nullable=True, default="[]")

    # Relationships
    cart_items = db.relationship("CartItem", back_populates="production_round", lazy="dynamic")
    items = db.relationship("Item", back_populates="production_round", lazy=True, cascade="all, delete-orphan")
    product = db.relationship("Product", back_populates="production_rounds")
    artist = db.relationship("Artist", back_populates="production_rounds")
    admin = db.relationship("OrderManagementAdmin", back_populates="production_rounds")
    dialogs = db.relationship("Dialog", back_populates="production_round", lazy=True, cascade="all, delete-orphan")
    payouts = db.relationship("Payout", back_populates="production_round", lazy=True)

    item_order_items = db.relationship(
        "ItemOrderItem",
        back_populates="production_round",
        lazy=True
    )

    
    @property
    def total_items_ordered(self):
        return sum(item.quantity for item in self.items)

    
    def toggle_display_status(self):
        """Toggle the display status of the production round."""
        self.is_published = not self.is_published
        db.session.commit()
        return f"Display status updated to {'published' if self.is_published else 'unpublished'}."
    
    def transition_stage(self, new_stage):
        """
        Transition the production round to a new stage.
        Automatically updates `is_active` based on the new stage.
        """
        valid_stages = ["initialize", "waiting", "sample", "production", "stocking", "abandon"]
        if new_stage not in valid_stages:
            raise ValueError(f"Invalid stage: {new_stage}")

        if self.stage == "initialize" and new_stage not in ["waiting", "abandon"]:
            raise ValueError("Can only transition to 'waiting' or 'abandon' from 'initialize'.")
        if self.stage == "waiting" and new_stage not in ["sample", "abandon"]:
            raise ValueError("Can only transition to 'sample' or 'abandon' from 'waiting'.")

        # Update stage and is_active
        self.stage = new_stage
        self.is_active = new_stage in ["initialize", "waiting", "sample", "production"]
        db.session.commit()
        return f"Production round transitioned to '{new_stage}'."
    
    
    def __repr__(self):
        return f"<ProductionRound id={self.id} product_id={self.product_id}>"

    @property
    def stage_goals(self):
        """
        Returns the production goals as a structured list.
        The list is sorted by `quantity` in ascending order.
        """
        try:
            goals = json.loads(self.production_goals)
            return sorted(goals, key=lambda goal: goal['quantity'])
        except (ValueError, TypeError) as e:
            logging.error(f"Error parsing production goals for ProductionRound {self.id}: {e}")
            return []

    @stage_goals.setter
    def stage_goals(self, goals_data):
        """
        Sets the production goals. Input should be a list of dictionaries with `quantity` and `gift`.
        """
        try:
            # Validate input
            if not isinstance(goals_data, list):
                raise ValueError("Production goals must be a list of dictionaries.")

            normalized_goals = []
            for goal in goals_data:
                # Normalize key names to `quantity` and `gift`
                quantity = goal.get('quantity') or goal.get('target_quantity')
                gift = goal.get('gift')

                if quantity is None or gift is None:
                    raise ValueError("Each goal must include 'quantity' (or 'target_quantity') and 'gift' keys.")
                if not isinstance(quantity, int) or quantity <= 0:
                    raise ValueError(f"Invalid quantity: {quantity}")

                normalized_goals.append({'quantity': quantity, 'gift': gift.strip()})

            # Store as JSON string
            self.production_goals = json.dumps(normalized_goals)
        except Exception as e:
            logging.error(f"Error setting production goals for ProductionRound {self.id}: {e}")
            raise



    # need notification system


# transaction section: item order (purchased & transfer) & delivery order

# item is the individual product (of a production round) 
# transfer and refund processes are on the individual items
# each item is connected to the customer id.
# function of transferring the digital ownership of the item could be implemented
# like NFT...? it would be interesting...although the database would "seems" to be redundant
# well I actually came up with the physical merch-NFT idea a few weeks ago...
# but the implementation process is the one that makes it...



# there are two kinds of order: item and delivery

# a base item to define common attribute
# Three kinds of item to increase data efficiency
# delivered item: hold those item that are delivered to the customer (for verification and virtual ownership)
# abandoned item: hold the item that are fully/partially refunded or in an abandoned production round.
# item: hold the items that are active in the platform


class BaseItem(db.Model):
    __tablename__ = 'base_items'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # Use Python's uuid4
    production_round_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_rounds.id'), nullable=False)
    type = db.Column(String(50), nullable=False)  # Polymorphic type

    production_round = db.relationship("ProductionRound", back_populates="items")

    __mapper_args__ = {
        'polymorphic_identity': 'base_item',
        'polymorphic_on': type
    }

class Item(BaseItem):
    __tablename__ = 'items'

    id = db.Column(UUID(as_uuid=True), db.ForeignKey('base_items.id'), primary_key=True)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=True)
    is_in_transfer_list = db.Column(Boolean, default=False) #for the item for transfer for the item

    customer = db.relationship("Customer", back_populates="items")
    item_orders = db.relationship("ItemOrderItem", back_populates="item", lazy=True)

    __mapper_args__ = {
        'polymorphic_identity': 'item',
    }

    def transition_to_delivered(self, delivery_date=None):
        delivered_item = DeliveredItem(
            id=self.id,
            production_round_id=self.production_round_id,
            customer_id=self.customer_id,
            in_delivery=True,
            delivered_at=delivery_date or datetime.now()
        )
        return delivered_item


    def transition_to_abandoned(self, refund_amount=None):

        abandoned_item = AbandonedItem(
            id=self.id,
            production_round_id=self.production_round_id,
            refund_amount=refund_amount,
            abandoned_at=datetime.now()
        )
        return abandoned_item



class DeliveredItem(BaseItem):
    __tablename__ = 'delivered_items'

    id = db.Column(UUID(as_uuid=True), db.ForeignKey('base_items.id'), primary_key=True)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=True)
    delivered_at = db.Column(DateTime, default=datetime.now, nullable=False)
    in_delivery = db.Column(Boolean, default=False)
    is_in_transfer_list = db.Column(Boolean, default=False) #for the item for transfer for the delivered item

    customer = db.relationship("Customer", foreign_keys=[customer_id], back_populates="delivered_items")
    delivery_order_items = db.relationship("DeliveryOrderItem", back_populates="delivered_item", lazy=True)

    __mapper_args__ = {
        'polymorphic_identity': 'delivered_item',
    }

    def mark_delivery_complete(self):
        self.in_delivery = False




class AbandonedItem(BaseItem):
    __tablename__ = 'abandoned_items'

    id = db.Column(UUID(as_uuid=True), db.ForeignKey('base_items.id'), primary_key=True)
    refund_amount = db.Column(Float, nullable=True)
    abandoned_at = db.Column(DateTime, default=datetime.now, nullable=False)
    refund_item_order = relationship(
        "RefundItemOrder",
        back_populates="abandoned_item",
        uselist=False
    )

    __mapper_args__ = {
        'polymorphic_identity': 'abandoned_item',
    }

# cart and cart item

class Cart(db.Model):
    __tablename__ = "carts"
    id = db.Column(UUID, primary_key=True, default=uuid.uuid4)
    customer_id = db.Column(UUID, db.ForeignKey('customers.id'), nullable=False)

    customer = db.relationship("Customer", back_populates="cart")
    cart_items = db.relationship("CartItem", back_populates="cart", lazy=True, cascade="all, delete-orphan")

    def add_item_to_cart(self, production_round, quantity):
        """Add or increment a CartItem for the given production_round."""
        existing_cart_item = CartItem.query.filter_by(
            cart_id=self.id,
            production_round_id=production_round.id
        ).first()

        if existing_cart_item:
            existing_cart_item.quantity += quantity
        else:
            new_cart_item = CartItem(
                cart_id=self.id,
                production_round_id=production_round.id,
                quantity=quantity
            )
            # Populate snapshot fields
            new_cart_item.populate_snapshot(production_round)
            db.session.add(new_cart_item)

    def update_item_quantity(self, production_round_id, new_quantity):
        """Update the quantity for a specific CartItem (or remove if zero)."""
        cart_item = CartItem.query.filter_by(
            cart_id=self.id,
            production_round_id=production_round_id
        ).first()
        if not cart_item:
            return  # No item to update

        if new_quantity <= 0:
            db.session.delete(cart_item)
        else:
            cart_item.quantity = new_quantity

    def remove_item_from_cart(self, production_round_id):
        """Remove an item from the cart entirely."""
        cart_item = CartItem.query.filter_by(
            cart_id=self.id,
            production_round_id=production_round_id
        ).first()
        if cart_item:
            db.session.delete(cart_item)

    def calculate_total(self):
        """Calculate the sum of all cart_items' quantity * unit_price."""
        total = 0
        for ci in self.cart_items:
            total += ci.quantity * ci.unit_price
        return total

    def is_empty(self):
        """Return True if the cart is empty (has no cart_items), else False."""
        return len(self.cart_items) == 0





class CartItem(db.Model):
    __tablename__ = "cart_items"

    cart_id = db.Column(UUID, db.ForeignKey('carts.id'), primary_key=True)
    production_round_id = db.Column(UUID, db.ForeignKey('production_rounds.id'), primary_key=True)
    quantity = db.Column(db.Integer, default=1)

    # Snapshot fields
    unit_price = db.Column(db.Float, nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    product_image_path = db.Column(db.String(255), nullable=False)


    cart = db.relationship("Cart", back_populates="cart_items")
    production_round = db.relationship("ProductionRound", back_populates="cart_items")  # if needed

    def populate_snapshot(self, production_round):
        """
        Populate the snapshot fields using data from the ProductionRound and associated Product.
        """
        self.unit_price = production_round.price
        self.product_name = production_round.product.name
        self.product_image_path = production_round.product.artwork.image_path





# ItemOrder holds references to the customer who is placing the order and an overall total or status.
# Each order can have many order-line items (OrderItem / ItemOrderItem).

class ItemOrder(db.Model):
    __tablename__ = 'orders'  # Ensure this matches the foreign key reference

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    total_amount = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Payment-related columns
    payment_method = db.Column(db.String(50), nullable=True)  # e.g., "credit_card", "paypal"
    payment_status = db.Column(db.String(50), default='unpaid')  # e.g., "unpaid", "paid", "failed"
    payment_timestamp = db.Column(db.DateTime, nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)

    customer = db.relationship("Customer", back_populates="orders")
    order_items = db.relationship("ItemOrderItem", back_populates="item_order", lazy=True)

    def pay(self, method, reference=None):
        """
        Simulate processing payment for this order.
        """
        self.payment_method = method
        self.payment_status = 'paid'
        self.payment_timestamp = datetime.now()
        self.payment_reference = reference
        self.status = True
        db.session.commit()

    def __repr__(self):
        return f"<ItemOrder {self.id} status={self.status} amount={self.total_amount}>"





class ItemOrderItem(db.Model):
    __tablename__ = "item_order_items"

    item_order_id = db.Column(UUID, db.ForeignKey('orders.id'), primary_key=True)  # Match with ItemOrder's __tablename__
    production_round_id = db.Column(UUID, db.ForeignKey('production_rounds.id'), primary_key=True)
    item_id = db.Column(UUID, db.ForeignKey('items.id'), nullable=True)
    item_type = db.Column(db.String(50), default="item")  # "abandoned", "delivered"

    # Snapshot fields
    unit_price = db.Column(db.Float, nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    product_image_path = db.Column(db.String(255), nullable=False)

    item_order = db.relationship("ItemOrder", back_populates="order_items")
    item = db.relationship("Item", back_populates="item_orders")
    production_round = db.relationship("ProductionRound", back_populates="item_order_items")

    def populate_snapshot(self, production_round):
        """
        Populate the snapshot fields using data from the ProductionRound and associated Product.
        """
        self.unit_price = production_round.price
        self.product_name = production_round.product.name
        self.product_image_path = production_round.product.artwork.image_path




class RefundItemOrder(db.Model):
    __tablename__ = 'refund_item_orders'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    reason = db.Column(db.String(100), default='refund')
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Refund-specific fields
    refund_method = db.Column(db.String(50), nullable=True)  # e.g., "credit_card", "paypal"
    refund_status = db.Column(db.String(50), default="pending")  # "pending", "processed"
    refund_timestamp = db.Column(db.DateTime, nullable=True)
    refund_reference = db.Column(db.String(100), nullable=True)
    refund_amount = db.Column(db.Float, nullable=True)

    # Foreign key relationships
    abandoned_item_id = db.Column(UUID, db.ForeignKey("abandoned_items.id"), nullable=False, unique=True)

    # Relationships
    customer = db.relationship("Customer", back_populates="refund_item_orders")
    abandoned_item = db.relationship("AbandonedItem", back_populates="refund_item_order", uselist=False)

    def process_refund(self, method, reference=None):
        """
        Process the refund and update refund metadata.
        """
        self.refund_method = method
        self.refund_status = 'processed'
        self.refund_timestamp = datetime.now()
        self.refund_reference = reference
        self.status = 'completed'
        db.session.commit()

    def __repr__(self):
        return f"<RefundItemOrder {self.id} reason={self.reason} status={self.status}>"






# transfer and order
# two types of transfer: item transfer and delivered item transfer
# item transfer is for the item (when it is still in the platform)
# delivered item is for the item that has been delivered to the customer
#   collection showcase for customer
#   transaction (but the implementation level... maybe open later?)

# two types of order: item order and delivery order



class TransferItemOrder(db.Model):
    __tablename__ = 'transfer_item_orders'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    to_customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(50), default="initiated")

    # Link to either Item or DeliveredItem (one or both can be null if you store them in a single column)
    item_id = db.Column(UUID(as_uuid=True), db.ForeignKey('items.id'), nullable=True)
    delivered_item_id = db.Column(UUID(as_uuid=True), db.ForeignKey('delivered_items.id'), nullable=True)

    # Payment columns (the buyer pays)
    transfer_price = db.Column(db.Float, default=0.0)
    payment_method = db.Column(db.String(50), nullable=True)  
    payment_status = db.Column(db.String(50), default='unpaid')
    payment_timestamp = db.Column(db.DateTime, nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)

    # Refund columns (auto refund from the system?)
    refund_method = db.Column(db.String(50), nullable=True)  
    refund_status = db.Column(db.String(50), default='none')  # e.g. 'none', 'pending', 'completed'
    refund_timestamp = db.Column(db.DateTime, nullable=True)
    refund_reference = db.Column(db.String(100), nullable=True)
    refund_amount = db.Column(db.Float, default=0.0)

    # Relationships
    from_customer_relationship = db.relationship(
        "Customer",
        foreign_keys=[from_customer_id],
        back_populates="transfer_item_orders_outgoing"
    )
    to_customer_relationship = db.relationship(
        "Customer",
        foreign_keys=[to_customer_id],
        back_populates="transfer_item_orders_incoming"
    )
    item = db.relationship("Item", foreign_keys=[item_id])
    delivered_item = db.relationship("DeliveredItem", foreign_keys=[delivered_item_id])


    def process_payment(self, method, reference=None):
        # For the buyer to pay the seller
        self.payment_method = method
        self.payment_status = 'paid'
        self.payment_timestamp = datetime.now()
        self.payment_reference = reference
        db.session.commit()

    def process_auto_refund(self, method, reference=None, amount=0.0):
        # Auto refund triggered by the system
        self.refund_method = method
        self.refund_status = 'completed'
        self.refund_timestamp = datetime.now()
        self.refund_reference = reference
        self.refund_amount = amount
        db.session.commit()

    def __repr__(self):
        return f"<TransferItemOrder {self.id} from={self.from_customer_id} to={self.to_customer_id}>"






class DeliveryOrder(db.Model):
    __tablename__ = 'delivery_orders'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    delivery_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('delivery_admins.id'), nullable=True)
    shipping_address = db.Column(db.String(255), nullable=False)
    delivery_cost = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="created")
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Payment columns (one payment only)
    payment_method = db.Column(db.String(50), nullable=True)
    payment_status = db.Column(db.String(50), default='unpaid')
    payment_timestamp = db.Column(db.DateTime, nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)

    # Relationships
    customer = db.relationship("Customer", back_populates="delivery_orders")
    delivery_admin = db.relationship("DeliveryAdmin", back_populates="delivery_orders")
    packages = db.relationship("DeliveryPackage", back_populates="delivery_order", lazy=True)


    # Functions
    def create_packages(self):
        # Implementation for creating packages
        pass

    def mark_as_delivered(self):
        # Implementation for marking the order as delivered
        pass

    def pay_delivery_cost(self, method, reference=None):
        self.payment_method = method
        self.payment_status = 'paid'
        self.payment_timestamp = datetime.now()
        self.payment_reference = reference
        db.session.commit()

    def __repr__(self):
        return f"<DeliveryOrder {self.id} status={self.status} cost={self.delivery_cost}>"




class DeliveryPackage(db.Model):
    __tablename__ = 'delivery_packages'
    package_number = db.Column(db.String(100), unique=True, nullable=False,primary_key=True)
    delivery_order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('delivery_orders.id'), nullable=False)


    # Relationships
    delivery_order = db.relationship("DeliveryOrder", back_populates="packages")
    items = db.relationship("DeliveryOrderItem", back_populates="delivery_package", lazy=True)



# Delivery Order Items Table
class DeliveryOrderItem(db.Model):
    __tablename__ = 'delivery_order_items'

    delivery_package_id = db.Column(db.String(100), db.ForeignKey('delivery_packages.package_number'), primary_key=True)
    delivered_item_id = db.Column(UUID(as_uuid=True), db.ForeignKey('delivered_items.id'), primary_key=True)
    delivery_status = db.Column(db.String(50), nullable=False, default="pending")

    delivery_package = db.relationship("DeliveryPackage", back_populates="items")
    delivered_item = db.relationship("DeliveredItem", back_populates="delivery_order_items")


# money and transaction section

# transaction log is based on items
# payment is based on the inflow of money
# refund transaction is based on the outflow of money

# payment is the record of transaction, whic has two types: item & delivery
# item has two types of source: purchased and transferred







# artist incentive, need update

class Payout(db.Model):
    __tablename__ = 'payouts'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artists.id'), nullable=False)
    production_round_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_rounds.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)  # Total amount paid to the artist
    status = db.Column(db.String(50), nullable=False, default="pending")  # "pending", "completed"
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relationships
    artist = db.relationship("Artist", back_populates="payouts")
    production_round = db.relationship("ProductionRound", back_populates="payouts")





# Dialog Model to Track Messages Between Artist and Order Management Admin
# Update Dialog model to support rich content and multiple files
class Dialog(db.Model):
    __tablename__ = 'dialogs'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    production_round_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_rounds.id'), nullable=False)
    sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=True)  # Nullable to allow file-only dialogs
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relationships
    production_round = db.relationship("ProductionRound", back_populates="dialogs")
    sender = db.relationship("User")
    files = db.relationship("DialogFile", back_populates="dialog", lazy=True, cascade="all, delete-orphan")




# DialogFile model to handle file uploads
class DialogFile(db.Model):
    __tablename__ = 'dialog_files'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dialog_id = db.Column(UUID(as_uuid=True), db.ForeignKey('dialogs.id'), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(200), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relationships
    dialog = db.relationship("Dialog", back_populates="files")





# Design File Model
class DesignFile(db.Model):
    __tablename__ = 'design_files'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = db.Column(db.String(300), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    product = db.relationship("Product", back_populates="design_files")






# Notification model with updated type attribute
class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(500), nullable=True)  # URL for the notification action
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    is_read = db.Column(db.Boolean, default=False)
    type = db.Column(db.String(50), nullable=False)  # Category of the notification (e.g., 'order_update', 'approval', 'promotion')

    user = db.relationship("User", back_populates="notifications")

    @classmethod
    def get_unread_notifications_count(cls, user_id):
        return cls.query.filter_by(user_id=user_id, is_read=False).count()

    @classmethod
    def get_unread_notifications(cls, user_id):
        return cls.query.filter_by(user_id=user_id, is_read=False).all()

    @classmethod
    def send_notification(cls, user_id, message, type, link=None):
        """Class method to send a notification to a specific user."""
        new_notification = cls(
            user_id=user_id,
            message=message,
            link=link,
            is_read=False,
            timestamp=datetime.now(timezone.utc),
            type=type  # Add the notification type here
        )
        db.session.add(new_notification)
        db.session.commit()




