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

# Define Models

# User Model
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
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

    def assign_order_management_admin(self, product, order_management_admin):
        product.assigned_admin_id = order_management_admin.id
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

    # Explicit foreign_keys specified to resolve ambiguity
    orders = db.relationship(
        "Order",
        back_populates="customer",
        lazy=True,
        foreign_keys="Order.customer_id"
    )

    wallet = db.relationship("Wallet", uselist=False, back_populates="customer")
    coupon_usages = db.relationship("CouponUsage", back_populates="customer", lazy=True)
    transaction_logs = db.relationship("TransactionLog", back_populates="customer", lazy=True)

    __mapper_args__ = {
        'polymorphic_identity': 'customer',
    }



class Wallet(db.Model):
    __tablename__ = 'wallets'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    balance = db.Column(db.Float, default=0.0)

    customer = db.relationship("Customer", back_populates="wallet")



class Coupon(db.Model):
    __tablename__ = 'coupons'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_amount = db.Column(db.Float, nullable=False)  # Fixed discount amount
    expiration_date = db.Column(db.DateTime, nullable=False)
    usage_limit = db.Column(db.Integer, default=1)  # How many times it can be used per customer
    active = db.Column(db.Boolean, default=True)

    # A relationship that will link each coupon to usage records for tracking
    usage_records = db.relationship("CouponUsage", back_populates="coupon", lazy=True)



class CouponUsage(db.Model):
    __tablename__ = 'coupon_usages'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coupon_id = db.Column(UUID(as_uuid=True), db.ForeignKey('coupons.id'), nullable=False)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    usage_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    coupon = db.relationship("Coupon", back_populates="usage_records")
    customer = db.relationship("Customer", back_populates="coupon_usages")

class TransactionLog(db.Model):
    __tablename__ = 'transaction_logs'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False)  # "pending", "paid", "failed"
    payment_method = db.Column(db.String(50), nullable=False)  # "wallet", "coupon", "sandbox"
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    customer = db.relationship("Customer", back_populates="transaction_logs")



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
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    disapproval_reason = db.Column(db.Text, nullable=True)
    approval_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artwork_approval_admins.id'), nullable=True)  # New attribute for recording approval admin ID
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    # Relationships
    artist = db.relationship("Artist", back_populates="artworks", foreign_keys=[artist_id])
    products = db.relationship("Product", back_populates="artwork", lazy=True)
    favorited_by = db.relationship("Customer", secondary="favorites", back_populates="favorite_artworks")
    

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


# Product model
class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(200), nullable=False)
    production_specs = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    manufacture_type = db.Column(db.String(50), nullable=False)
    production_status = db.Column(db.String(50), nullable=False, default='Pending')
    display_status = db.Column(db.String(50), nullable=False, default='not display')
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    artwork_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artworks.id'), nullable=False)
    assigned_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('order_management_admins.id'), nullable=True)
    introduction = db.Column(db.Text, nullable=True)
    disapproval_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    
    # Relationships
    artwork = db.relationship("Artwork", back_populates="products")
    artist = db.relationship("Artist", back_populates="products", foreign_keys=[artist_id])
    managing_admin = db.relationship("OrderManagementAdmin", back_populates="products_managed", foreign_keys=[assigned_admin_id])
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



class ProductionRound(db.Model):
    __tablename__ = 'production_rounds'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artists.id'), nullable=False)
    admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('order_management_admins.id'), nullable=True)
    estimated_price = db.Column(db.Float, nullable=True) # estimated price of the product, based on the minimum production size. Right now for the product, there is only one payment.
    actual_price = db.Column(db.Float, nullable=True) # final price of the product, based on the actual production size
    min_production_size = db.Column(db.Integer, nullable=False, default=0)
    max_waiting_time = db.Column(db.Integer, nullable=False, default=0)
    production_stage = db.Column(db.String(50), nullable=False, default="minimum production") #production stage attribute, includes "minimum production", sample production", "mass production", flaw checking", "stocking"
    is_published = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(50), nullable=False, default="requested")  # production round is requested by artist, then all the information is confirmed and published by admin
    
    orders = db.relationship("Order", back_populates="production_round", lazy=True)
    dialogs = db.relationship("Dialog", back_populates="production_round", lazy=True, cascade="all, delete-orphan")
    product = db.relationship("Product", back_populates="production_rounds", foreign_keys=[product_id])
    artist = db.relationship("Artist", back_populates="production_rounds", foreign_keys=[artist_id])
    admin = db.relationship("OrderManagementAdmin", back_populates="production_rounds", foreign_keys=[admin_id])

    @property
    def current_order_quantity(self):
        """Calculate the total quantity of orders for this production round that have been confirmed."""
        return sum(order.quantity for order in self.orders if order.cart_status == 'confirmed')



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


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    production_round_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_rounds.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)  # Number of units the customer is buying
    amount_paid = db.Column(db.Float, nullable=False)  # Total payment (quantity * price per unit)
    order_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    status = db.Column(db.String(50), nullable=False, default='pending')  # "pending", "confirmed", "shipped"
    cart_status = db.Column(db.String(50), nullable=True, default='in_cart')  # "in_cart" or "confirmed"
    is_refunded = db.Column(db.Boolean, default=False)
    refund_amount = db.Column(db.Float, nullable=True)  # Amount refunded (None if full refund)
    is_transferred = db.Column(db.Boolean, default=False)
    new_customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=True)  # For transfers

    # Explicit foreign_keys specified to resolve ambiguity
    customer = db.relationship(
        "Customer",
        back_populates="orders",
        foreign_keys=[customer_id]
    )
    new_customer = db.relationship(
        "Customer",
        foreign_keys=[new_customer_id]
    )
    production_round = db.relationship("ProductionRound", back_populates="orders")




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
