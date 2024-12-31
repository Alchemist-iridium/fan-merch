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

    shipping_addresses = db.relationship('ShippingAddress', back_populates='user', lazy=True)
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

    products_managed = relationship('Product', back_populates='managing_admin', lazy=True, foreign_keys='Product.assigned_admin_id')
    production_rounds = relationship('ProductionRound', back_populates='admin', lazy=True, foreign_keys='ProductionRound.admin_id')


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



# Artist model
class Artist(User):
    __tablename__ = 'artists'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)
    bio = db.Column(db.String(500), nullable=True)

    artworks = db.relationship("Artwork", back_populates="artist", lazy=True)
    followers = db.relationship("Customer", secondary="followers", back_populates="followed_artists")
    products = db.relationship("Product", back_populates="artist", lazy=True)
    production_rounds = db.relationship("ProductionRound", back_populates="artist", lazy=True)
   
    __mapper_args__ = {
        'polymorphic_identity': 'artist',
    }



class Customer(User):
    __tablename__ = 'customers'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)

    # Favorite artworks and followed artists
    favorite_artworks = db.relationship("Artwork", secondary="favorites", back_populates="favorited_by")
    followed_artists = db.relationship("Artist", secondary="followers", back_populates="followers")

    # Relationship for owned items
    purchased_items = db.relationship("Item", back_populates="customer", foreign_keys="[Item.customer_id]")

    # Wallet and transactions
    wallet = db.relationship("Wallet", uselist=False, back_populates="customer")
    transaction_logs = db.relationship("TransactionLog", back_populates="customer", lazy=True)

    # Updated transfer relationships
    transfers_outgoing = db.relationship(
        "ItemTransfer", foreign_keys="[ItemTransfer.original_customer_id]", back_populates="original_customer"
    )
    transfers_incoming = db.relationship(
        "ItemTransfer", foreign_keys="[ItemTransfer.new_customer_id]", back_populates="new_customer"
    )

    __mapper_args__ = {
        'polymorphic_identity': 'customer',
    }




class Wallet(db.Model):
    __tablename__ = 'wallets'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    balance = db.Column(db.Float, default=0.0)

    customer = db.relationship("Customer", back_populates="wallet")



class TransactionLog(db.Model):
    __tablename__ = 'transaction_logs'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    item_id = db.Column(UUID(as_uuid=True), db.ForeignKey('items.id'), nullable=True)  # Link to individual item

    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False)  # "pending", "paid", "failed"
    payment_method = db.Column(db.String(50), nullable=False)  # "wallet", "sandbox"
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relationships
    customer = db.relationship("Customer", back_populates="transaction_logs")
    item = db.relationship("Item", back_populates="transactions")  # New relationship for item transactions






# Shipping Address model
class ShippingAddress(db.Model):
    __tablename__ = 'shipping_addresses'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    address = db.Column(db.String(200), nullable=False)

    user = db.relationship('User', back_populates='shipping_addresses')





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
    production_specs = db.Column(db.String(200), nullable=False)
    manufacture_type = db.Column(db.String(50), nullable=False)
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
    production_goals = db.Column(db.Text, nullable=True, default="[]")


    # Relationships
    items = db.relationship("Item", back_populates="production_round", lazy=True, cascade="all, delete-orphan")
    product = db.relationship("Product", back_populates="production_rounds")
    artist = db.relationship("Artist", back_populates="production_rounds")
    admin = db.relationship("OrderManagementAdmin", back_populates="production_rounds")
    dialogs = db.relationship("Dialog", back_populates="production_round", lazy=True, cascade="all, delete-orphan")

    
    @property
    def total_items_ordered(self):
        return sum(item.quantity for item in self.items)

    @property
    def grouped_items_by_customer(self):
        grouped = {}
        for item in self.items:
            if item.customer_id not in grouped:
                grouped[item.customer_id] = []
            grouped[item.customer_id].append(item)
        return grouped

    
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

# the stage goal is like that in the co-fund systems
# the unit cost of product will drop and to attract more customer
# hmm... just to say...
# will be displayed on the production (+round) page and affect the production and stocking (warehouse) system a little bit.








# item is the individual product (of a production round) 
# transfer and refund processes are on the individual items
# each item is connected to the customer id.
# function of transferring the digital ownership of the item could be implemented
# like NFT...? it would be interesting...although the database would "seems" to be redundant
# well I actually came up with the physical merch-NFT idea a few weeks ago...
# but the implementation process is the one that makes it...


class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    production_round_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_rounds.id'), nullable=False)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='purchased')  # "purchased", "refunded", "transferred"
    is_transferred = db.Column(db.Boolean, default=False)
    is_in_transfer_list = db.Column(db.Boolean, default=False)  # Track if item is in transfer list
    transfer_status = db.Column(db.String(50), nullable=True)  # "waiting", "canceled", "completed"
    transfer_timestamp = db.Column(db.DateTime, nullable=True)  # When added to transfer list
    new_customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=True)  # For transfers



    # Relationships
    customer = db.relationship("Customer", foreign_keys=[customer_id])
    new_customer = db.relationship("Customer", foreign_keys=[new_customer_id])
    production_round = db.relationship("ProductionRound", back_populates="items")

    transactions = db.relationship("TransactionLog", back_populates="item", lazy=True)



class ItemTransfer(db.Model):
    __tablename__ = 'item_transfers'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = db.Column(UUID(as_uuid=True), db.ForeignKey('items.id'), nullable=False, unique=True)  # Link to the item
    original_customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    new_customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=True)  # Updated after transfer
    transfer_status = db.Column(db.String(50), nullable=False, default='waiting')  # "waiting", "canceled", "completed"
    transfer_timestamp = db.Column(db.DateTime, default=datetime.now, nullable=False)

    # Relationships
    item = db.relationship("Item", backref="transfer_record")
    original_customer = db.relationship("Customer", foreign_keys="[ItemTransfer.original_customer_id]", back_populates="transfers_outgoing")
    new_customer = db.relationship("Customer", foreign_keys="[ItemTransfer.new_customer_id]", back_populates="transfers_incoming")

    def mark_as_completed(self, new_customer_id):
        """Mark the transfer as completed."""
        self.transfer_status = 'completed'
        self.new_customer_id = new_customer_id
        self.item.is_transferred = True
        self.item.customer_id = new_customer_id  # Change item ownership
        db.session.commit()

    def cancel_transfer(self):
        """Cancel the transfer process."""
        self.transfer_status = 'canceled'
        self.item.is_in_transfer_list = False
        db.session.commit()






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
