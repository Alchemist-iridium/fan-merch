from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from datetime import datetime, timezone
from uuid6 import uuid6
from sqlalchemy.dialects.postgresql import UUID, JSON

import logging
import json

from sqlalchemy.orm import validates

from flask_login import UserMixin

import uuid
import re



# Define Models

# User Model
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)  # Index added
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='unregistered')  # defaut value is unregistered, "customer", "artist" and admin's role name

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

    # Approve a specific artwork update
    def approve_update(self, artwork_update):
        artwork = artwork_update.artwork
        if artwork_update.proposed_title:
            artwork.title = artwork_update.proposed_title
        if artwork_update.proposed_description:
            artwork.description = artwork_update.proposed_description
        if artwork_update.proposed_manufacturing_specs:
            artwork.manufacturing_specs = artwork_update.proposed_manufacturing_specs
        if artwork_update.proposed_hard_tags:
            artwork.hard_tags = artwork_update.proposed_hard_tags
        if artwork_update.proposed_soft_tags:
            artwork.soft_tags = artwork_update.proposed_soft_tags

        artwork_update.status = 'Approved'
        artwork_update.reviewed_at = datetime.now()
        artwork.approval_status = 'Approved'
        artwork.approval_admin_id = self.id
        db.session.commit()

    # Disapprove a specific artwork update
    def disapprove_update(self, artwork_update, reason):
        artwork_update.status = 'Disapproved'
        artwork_update.disapproval_reason = reason
        artwork_update.reviewed_at = datetime.now()
        db.session.commit()

    # Optional: Pick up an update for review
    def pick_up_update(self, artwork_update):
        artwork_update.approval_admin_id = self.id
        db.session.commit()


# Production Round Admin Model
class ProductionRoundAdmin(Admin):
    __tablename__ = 'production_round_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)
    main_production_species = db.Column(db.String(200), nullable=False, default="general")

    __mapper_args__ = {
        'polymorphic_identity': 'production_round_admin',
    }

    products_managed = db.relationship('Product', back_populates='managing_admin', lazy=True, foreign_keys='Product.assigned_admin_id')
    production_rounds = db.relationship('ProductionRound', back_populates='admin', lazy=True, foreign_keys='ProductionRound.admin_id')


    def get_product_count(self):
        return len(self.products_managed)



# Product Approval Admin Model
class ProductApprovalAdmin(Admin):
    __tablename__ = 'product_approval_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'product_approval_admin',
    }

    def pick_product(self, product):
        """Assign the product to the admin's workspace by picking it."""
        product.picked_by_admin_id = self.id
        db.session.commit()

    def unpick_product(self, product):
        """Remove the product from the admin's workspace."""
        product.picked_by_admin_id = None
        db.session.commit()


class WarehouseAdmin(Admin):
    __tablename__ = 'warehouse_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'warehouse_admin',
    }

    # Relationships
    managed_records = db.relationship("WarehouseRecord", back_populates="warehouse_admin")





# Delivery admin, who is going to have the delivery order's package assigned

class DeliveryAdmin(Admin):
    __tablename__ = 'delivery_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)

    __mapper_args__ = {
        'polymorphic_identity': 'delivery_admin',
    }

    # Relationships
    delivery_orders = db.relationship("DeliveryOrder", back_populates="delivery_admin", lazy=True)
    warehouse = db.relationship("Warehouse", back_populates="delivery_admins")  # Add backref to Warehouse


class FinanceAdmin(Admin):
    __tablename__ = 'finance_admins'
    id = db.Column(db.UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)

    # Single relationship to AccountingTransaction
    transactions = db.relationship("AccountingTransaction", back_populates="finance_admin", lazy=True)
    
    __mapper_args__ = {
        'polymorphic_identity': 'finance_admin',
    }



class InfoAdmin(Admin):
    __tablename__ = 'info_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'info_admin',
    }


# tracking record for all the operations of info admin

class ModificationLog(db.Model):
    __tablename__ = 'modification_logs'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('info_admins.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # e.g., "add", "update"
    entity_type = db.Column(db.String(50), nullable=False)  # e.g., "region"
    entity_id = db.Column(db.String(36), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, nullable=False)

    admin = db.relationship("InfoAdmin", backref="modification_logs")

    @classmethod
    def log_modification(cls, admin_id, action, entity_type, entity_id=None, details=None):
        """Log an InfoAdmin modification action."""
        log = cls(
            admin_id=admin_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details
        )
        db.session.add(log)
        db.session.commit()
        return log  # Optional: return the log instance for potential use




class CustomerServiceAdmin(Admin):
    __tablename__ = 'customer_service_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'customer_service_admin',
    }


# Artist model
class Artist(User):
    __tablename__ = 'artists'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)
    bio = db.Column(db.String(500), nullable=True)

    artworks = db.relationship("Artwork", back_populates="artist", lazy=True)
    artwork_updates = db.relationship("ArtworkUpdate", back_populates="artist", lazy=True)
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

    #sign up for the notification of a new production round
    notification_signups = db.relationship("ProductNotificationSignup", back_populates="customer", lazy=True)

    # Removed payments and refund_transactions relationships since 
    # we store payment/refund fields directly on orders now.

    # Optional: favorite_artworks, followed_artists remain as is
    favorite_artworks = db.relationship("Artwork", secondary="favorites", back_populates="favorited_by")
    followed_artists = db.relationship("Artist", secondary="followers", back_populates="followers")

    __mapper_args__ = {
        'polymorphic_identity': 'customer',
    }



    

# Artwork model
class Artwork(db.Model):
    __tablename__ = 'artworks'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    image_path = db.Column(db.String(300), nullable=False)
    manufacturing_specs = db.Column(db.String(300), nullable=True)
    hard_tags = db.Column(db.String(300), nullable=False)
    tag_approvals = db.Column(JSON, default=lambda: {}, nullable=False)  # New field for tag approvals
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

    # update information of the artwork submitted by the artist
    updates = db.relationship("ArtworkUpdate", back_populates="artwork", lazy=True, cascade="all, delete-orphan")


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

    @property
    def has_pending_update(self):
        """Check if there are any pending updates for this artwork."""
        return any(update.status == 'Pending' for update in self.updates)
    
    def is_fully_approved(self):
        """Check if all tags in tag_approvals are 'Approved'."""
        return all(status == 'Approved' for status in self.tag_approvals.values())
    
    def normalize_tag(tag):
        return tag.strip().lower()
    
    def sanitize_filename(name):
        return re.sub(r'[^\w\-]', '_', name)



class ArtworkUpdate(db.Model):
    __tablename__ = 'artwork_updates'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    artwork_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artworks.id'), nullable=False, index=True)
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    proposed_title = db.Column(db.String(200), nullable=True)
    proposed_description = db.Column(db.String(500), nullable=True)
    proposed_manufacturing_specs = db.Column(db.String(300), nullable=True)
    proposed_hard_tags = db.Column(db.String(300), nullable=True)
    tag_approvals = db.Column(JSON, default=lambda: {}, nullable=False)  # New field for tag approvals
    proposed_soft_tags = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(50), nullable=False, default='Pending')  # e.g., Pending, Approved, Disapproved
    approval_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artwork_approval_admins.id'), nullable=True)
    picked_by_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artwork_approval_admins.id'), nullable=True)
    disapproval_reason = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    artwork = db.relationship("Artwork", back_populates="updates")
    artist = db.relationship("Artist", back_populates="artwork_updates")
    
    # Relationship on who is working on the artwork update approval process
    picked_by_admin = db.relationship("ArtworkApprovalAdmin", foreign_keys=[picked_by_admin_id])

    # Relationship to access the admin who approved/disapproved the artwork update
    approval_admin = db.relationship("ArtworkApprovalAdmin", foreign_keys=[approval_admin_id], backref="reviewed_artwork_updates", lazy=True)


# Product Model
class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    name = db.Column(db.String(200), nullable=False)
    production_specs = db.Column(db.String(200), nullable=False)    #manufacture type
    manufacture_type = db.Column(db.String(50), nullable=False) # artist/platform arrange
    production_status = db.Column(db.String(50), nullable=False, default='Pending')
    display_status = db.Column(db.Boolean, default=True)   #should be true???
    
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    artwork_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artworks.id'), nullable=False, index=True)  # Index added
    assigned_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_round_admins.id'), nullable=True)
    product_approval_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_approval_admins.id'), nullable=True)
    picked_by_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_approval_admins.id'), nullable=True)

    introduction = db.Column(db.Text, nullable=True)
    disapproval_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    artist_controlled = db.Column(db.Boolean, default=True)  # Determines who initiates production rounds
    trigger_threshold = db.Column(db.Integer, nullable=False, default=2) # for testing, 2


    # Relationships
    artwork = db.relationship("Artwork", back_populates="products")
    artist = db.relationship("Artist", back_populates="products", foreign_keys=[artist_id])
    managing_admin = db.relationship("ProductionRoundAdmin", back_populates="products_managed", foreign_keys=[assigned_admin_id])
    product_approval_admin = db.relationship("ProductApprovalAdmin", foreign_keys=[product_approval_admin_id])
    picked_by_admin = db.relationship("ProductApprovalAdmin", foreign_keys=[picked_by_admin_id])

    transfer_requests = db.relationship(
        "ProductManageTransferRequest",
        back_populates="product",
        lazy=True,
        cascade="all, delete-orphan"
    )

    production_rounds = db.relationship("ProductionRound", back_populates="product", lazy=True)

    design_files = db.relationship("DesignFile", back_populates="product", cascade="all, delete-orphan")

    notification_signups = db.relationship("ProductNotificationSignup", back_populates="product", lazy=True)

    # Method to toggle the display status of the product
    def toggle_display_status(self):
        """Toggle the display status between 'on display' and 'not display'."""
        if self.display_status == False:
            self.display_status = True
        else:
            self.display_status = False
        db.session.commit()
        return f"Product {self.id} display status updated to {self.display_status}"
    
    def toggle_control(self):
        """Toggle the production control mechanism."""
        self.artist_controlled = not self.artist_controlled
        db.session.commit()


    def notify_customers_on_waiting_round(self):
        """Notify all signed-up customers and clear the list when a waiting round starts."""
        signups = ProductNotificationSignup.query.filter_by(product_id=self.id).all()
        if not signups:
            return

        for signup in signups:
            Notification.send_notification(
                user_id=signup.customer_id,
                message=f" {self.name} is open for pre-order now! ",
                type="purchase_notification",
            )

        # Clear signups
        ProductNotificationSignup.query.filter_by(product_id=self.id).delete()
        db.session.commit()

    
    def check_and_notify_threshold(self):
        """Notify artist and/or admin when signup threshold is reached or doubled, with tailored messages."""
        signup_count = ProductNotificationSignup.query.filter_by(product_id=self.id).count()
        if signup_count < self.trigger_threshold:
            return

        # Original notifications when threshold is reached
        if self.artist_controlled:
            # Only notify artist if artist-controlled
            if self.artist_id:
                Notification.send_notification(
                    user_id=self.artist_id,
                    message=f"{signup_count} customers want {self.name}. Would you like to start a production round?",
                    type="production_round_prompt"
                )
        else:
            # Notify both artist and admin if not artist-controlled
            if self.artist_id:
                Notification.send_notification(
                    user_id=self.artist_id,
                    message=f"{signup_count} customers want {self.name}. A new production round will start soon!",
                    type="production_round_prompt"
                )
            if self.assigned_admin_id:
                Notification.send_notification(
                    user_id=self.assigned_admin_id,
                    message=f"Threshold reached ({signup_count}/{self.trigger_threshold}) for {self.name}. Start a new production round.",
                    type="production_round_prompt"
                )

        # Additional notifications if signup count is at least twice the threshold
        double_threshold = 2 * self.trigger_threshold
        if signup_count >= double_threshold:
            if self.artist_controlled:
                # Artist-controlled: Remind artist, inform admin to contact artist
                if self.artist_id:
                    Notification.send_notification(
                        user_id=self.artist_id,
                        message=f"Reminder: {signup_count} customers (over {double_threshold}) want {self.name}! Please start a production round soon.",
                        type="production_round_prompt"
                    )
                if self.assigned_admin_id:
                    Notification.send_notification(
                        user_id=self.assigned_admin_id,
                        message=f"High demand: {signup_count} signups (over {double_threshold}) for {self.name}. Contact the artist to initiate a production round.",
                        type="production_round_prompt"
                    )
            else:
                # Admin-controlled: Inform artist admin is notified, remind admin
                if self.artist_id:
                    Notification.send_notification(
                        user_id=self.artist_id,
                        message=f"{signup_count} customers (over {double_threshold}) want {self.name}. The admin has been notified to start a production round.",
                        type="production_round_prompt"
                    )
                if self.assigned_admin_id:
                    Notification.send_notification(
                        user_id=self.assigned_admin_id,
                        message=f"Reminder: {signup_count} signups (over {double_threshold}) for {self.name}. Please initiate a production round now!",
                        type="production_round_prompt"
                    )


# transactional system have a common model
# although I'm still not quite sure why we need this?



# the management control of the product could be managed

class ProductManageTransferRequest(db.Model):
    __tablename__ = 'product_manage_transfer_requests'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False, index=True)
    current_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_round_admins.id'), nullable=False)
    new_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_round_admins.id'), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Pending')  # "Pending", "Approved", "Disapproved"
    picked_by_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('product_approval_admins.id'), nullable=True)
    reviewed_by = db.Column(UUID(as_uuid=True), db.ForeignKey('product_approval_admins.id'), nullable=True)
    disapproval_reason = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    product = db.relationship("Product", back_populates="transfer_requests")
    current_admin = db.relationship("ProductionRoundAdmin", foreign_keys=[current_admin_id])
    new_admin = db.relationship("ProductionRoundAdmin", foreign_keys=[new_admin_id])
    reviewed_by_admin = db.relationship("ProductApprovalAdmin", foreign_keys=[reviewed_by])




# sign up for notification to trigger the new production round
# will be cleared when the new production round is changed to waiting

class ProductNotificationSignup(db.Model):
    __tablename__ = 'product_notification_signups'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False, index=True)
    
    customer = db.relationship("Customer", back_populates="notification_signups")
    product = db.relationship("Product", back_populates="notification_signups")
    
    __table_args__ = (db.UniqueConstraint('customer_id', 'product_id', name='uq_customer_product'),)



# The active production round has the stage of ["initialize", "waiting", "sample", "production", "examination"]
# The not active production round has the stage of ["stocking", "abandon"].



    # Stores production stage goals as a JSON string
    # the stage goal is like that in the co-fund systems
    # the unit cost of product will drop and to attract more customer
    # hmm... just to say...
    # will be displayed on the production (+round) page and affect the production and stocking (warehouse) system a little bit.



class ProductionRound(db.Model):
    __tablename__ = 'production_rounds'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False, index=True)
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artists.id'), nullable=False)
    admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_round_admins.id'), nullable=True)

    price = db.Column(db.Float, nullable=True)
    partial_refund = db.Column(db.Float, nullable=True)  # the amount that could be auto-refunded between waiting and production status
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
    # The active production round has the stage of ["initialize", "waiting", "sample", "production","examination"]
    # The not active production round has the stage of ["stocking", "abandon"].

    is_accepted = db.Column(db.Boolean, default=False)
    # controlled by the warehouse admin


    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    # Stores production stage goals as a JSON string
    # might need update!!! right now it is not stored as JSON string
    # ?maybe not? need investigation
    # setting partial visibility to the warehouse accept part sections would be better?

    # e.g.  [{"quantity": "100", "gift": "Keychain"}, {"quantity": "200", "gift": "Poster"}]
    production_goals = db.Column(db.Text, nullable=True, default="[]") 
    
    # record on the number of item ordered for the production round
    total_items_ordered = db.Column(db.Integer, nullable=False, default=0)

    sample_fee = db.Column(db.Float, nullable=True, default=0.0)  # Fee for sample production
    mass_production_fee = db.Column(db.Float, nullable=True, default=0.0)  # Cost per item for mass production

    artist_payout_percentage = db.Column(db.Float, nullable=True, default=0.0)  # Percentage of revenue paid to the artist



    # Relationships
    cart_items = db.relationship("CartItem", back_populates="production_round", lazy="dynamic")
    
    product = db.relationship("Product", back_populates="production_rounds")
    artist = db.relationship("Artist", back_populates="production_rounds")
    admin = db.relationship("ProductionRoundAdmin", back_populates="production_rounds")
    dialogs = db.relationship("Dialog", back_populates="production_round", lazy=True, cascade="all, delete-orphan")
    payouts = db.relationship("Payout", back_populates="production_round", lazy=True)

    item_order_items = db.relationship(
        "ItemOrderItem",
        back_populates="production_round",
        lazy=True
    )
    # location of the items of a production round in the warehouse
    warehouse_records = db.relationship("WarehouseRecord", back_populates="production_round", lazy=True)

    
    @property
    
    def toggle_display_status(self):
        """Toggle the display status of the production round."""
        self.is_published = not self.is_published
        db.session.commit()
        return f"Display status updated to {'published' if self.is_published else 'unpublished'}."
    
    
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


    def decrement_order_count(self, customer_id):
        """
        Decreases the total_items_ordered count by 1 and updates ProductionRoundNotification.
        If quantity in ProductionRoundNotification reaches 0, the record is deleted.
        """
        if self.total_items_ordered > 0:
            self.total_items_ordered -= 1
            db.session.add(self)  # Update the production round count

        # Find the notification record for this customer
        notification = ProductionRoundNotification.query.filter_by(
            production_round_id=self.id, customer_id=customer_id
        ).first()

        if notification:
            if notification.quantity > 1:
                notification.quantity -= 1
                db.session.add(notification)  # Update the quantity
            else:
                db.session.delete(notification)  # Remove the notification if quantity is 0

        db.session.commit()





class ProductionRoundNotification(db.Model):
    __tablename__ = "production_round_notifications"
    
    production_round_id = db.Column(
        UUID(as_uuid=True), 
        db.ForeignKey("production_rounds.id"), 
        primary_key=True, 
        nullable=False
    )
    customer_id = db.Column(
        UUID(as_uuid=True), 
        db.ForeignKey("customers.id"), 
        primary_key=True, 
        nullable=False
    )
    quantity = db.Column(db.Integer, nullable=False, default=0)  # New column for quantity
    
    # Composite index for efficient querying
    __table_args__ = (
        db.Index('ix_prod_round_customer', 'production_round_id', 'customer_id'),
    )






# transaction section: item order (purchased & transfer) & delivery order

# item is the individual product (of a production round) 
# transfer and refund processes are on the individual items
# each item is connected to the customer id.
# function of transferring the digital ownership of the item could be implemented
# like NFT...? it would be interesting...although the database would "seems" to be redundant
# well I actually came up with the physical merch-NFT idea a few weeks ago...
# but the implementation process is the one that makes it...



# there are two kinds of order: item_based and delivery


# cart and cart item

class Cart(db.Model):
    __tablename__ = "carts"
    id = db.Column(UUID, primary_key=True, default=uuid6)
    customer_id = db.Column(UUID, db.ForeignKey('customers.id'), nullable=False) # probably this one need index more???

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
    
    # retrive item from cart to order
    def log_cart_items(self):
        for item in self.cart_items:
            logging.debug("CartItem - ID: %s, Product: %s, Quantity: %d", 
                          item.production_round_id, item.product_name, item.quantity)


    def calculate_total(self):
        """Calculate the sum of all cart_items' quantity * unit_price."""
        total = 0
        for ci in self.cart_items:
            total += ci.quantity * ci.unit_price
        return total

    def is_empty(self):
        """Return True if the cart is empty (has no cart_items), else False."""
        return len(self.cart_items) == 0
    

    # cart item is going to be cleared after the ItemOrder is paid


    def clear_items_after_order(self, checkout_items):
        """
        Removes cart items once they are successfully ordered.
        """
        for prod_round_id_str in checkout_items.keys():
            production_round_id = uuid.UUID(prod_round_id_str)
            cart_item = CartItem.query.filter_by(cart_id=self.id, production_round_id=production_round_id).first()
            if cart_item:
                db.session.delete(cart_item)

        db.session.commit()



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
    __table_args__ = (db.Index('ix_item_order_customer_id_id', 'customer_id', 'id'),)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    total_amount = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Store items (production_round_id, quantity)
    item_list = db.Column(JSON, nullable=False, default=list)
    # Item creation, tax-related reference...? anyway it is also here
    region = db.Column(db.Integer, nullable=False)

    # Payment-related columns
    payment_method = db.Column(db.String(50), nullable=True)  # e.g., "credit_card", "paypal"
    payment_status = db.Column(db.String(50), default='unpaid')  # e.g., "unpaid", "paid", "failed"
    payment_timestamp = db.Column(db.DateTime, nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)
    
    #updated when it is paid
    tax_amount = db.Column(db.Float, default=0.0)  # Tax specific to this order
    transaction_fee = db.Column(db.Float, default=0.0)  # Fee from payment gateway


    # Relationships
    customer = db.relationship("Customer", back_populates="orders")
    order_items = db.relationship(
        "ItemOrderItem", 
        back_populates="item_order", 
        lazy=True,
        cascade="all, delete-orphan"  # Automatically deletes related ItemOrderItems...? I don't think it is needed on operational level...
    )

    def __repr__(self):
        return f"<ItemOrder {self.id} status={self.payment_status} amount={self.total_amount}>"
    

    def validate_production_round_status(self):
        """
        Ensures all production rounds associated with this order are in the 'waiting' stage.
        Raises a ValueError if any production round is expired, listing all expired items.
        """
        expired_items = []

        # Check each item in the order
        for item in self.order_items:
            if item.production_round.stage != 'waiting':
                expired_items.append(f"Item '{item.product_name}' (Stage: {item.production_round.stage})")

        # If there are expired items, raise a ValueError with details
        if expired_items:
            expired_items_info = "; ".join(expired_items)
            raise ValueError(f"The following items are associated with expired production rounds: {expired_items_info}")


    def mark_as_paid(self, payment_method: str, payment_reference: str = None, region=None):
        """
        Marks the order as paid and creates ActiveItem records.
        """
        self.payment_status = 'paid'
        self.payment_method = payment_method
        self.payment_timestamp = datetime.now()
        self.payment_reference = payment_reference
        self.updated_at = datetime.now()

        if region is not None:
            self.create_active_items(region)  # Pass region explicitly
        else:
            raise ValueError("Region must be provided when marking an order as paid.")

    # creat the item order item after order is paid

    def create_active_items(self, region):
        """Converts `item_list` JSON data into ActiveItem records with region."""
        for item in self.item_list:
            production_round = db.session.get(ProductionRound, uuid.UUID(item['production_round_id']))
            if not production_round:
                continue
            
            for _ in range(item['quantity']):
                active_item = ItemOrderItem(
                    id=uuid6(),
                    item_order_id=self.id,
                    production_round_id=production_round.id,
                    region_id=region,  # Corrected to region_id
                    unit_price=production_round.price,
                    product_name=production_round.product.name,
                    product_image_path=production_round.product.artwork.image_path,
                )
                db.session.add(active_item)


    #after the order is paid
    #1: increase the count of the total item of the production round
    #2: put the customer on the notification list of the product (ProductionRoundNotification)


    def update_production_round_totals(self):
        """Increment total_items_ordered in ProductionRound based on item_list quantities."""
        for item in self.item_list:
            prod_round_id = uuid.UUID(item['production_round_id'])
            quantity = item['quantity']
            production_round = ProductionRound.query.get(prod_round_id)
            if production_round:
                production_round.total_items_ordered += quantity
                db.session.add(production_round)
                logging.debug(f"Updated ProductionRound {prod_round_id}: total_items_ordered = {production_round.total_items_ordered}")
            else:
                logging.warning(f"ProductionRound {prod_round_id} not found for order {self.id}")


        
    def register_customer_for_notifications(self):
        """Register customer for notifications based on item_list."""
        for item in self.item_list:
            production_round_id = uuid.UUID(item['production_round_id'])
            quantity = item['quantity']
            customer_id = self.customer_id

            existing_notification = ProductionRoundNotification.query.filter_by(
                production_round_id=production_round_id,
                customer_id=customer_id
            ).first()

            if existing_notification:
                existing_notification.quantity += quantity
                db.session.add(existing_notification)
                logging.debug(f"Updated notification for {production_round_id}: quantity = {existing_notification.quantity}")
            else:
                notification = ProductionRoundNotification(
                    production_round_id=production_round_id,
                    customer_id=customer_id,
                    quantity=quantity
                )
                db.session.add(notification)
                logging.debug(f"Created new notification for {production_round_id}: quantity = {quantity}")



    
class ItemOrderItem(db.Model):
    __tablename__ = "item_order_items"
    __table_args__ = (
        db.Index('ix_item_order_production_round_id', 'production_round_id'),  # Index on production_round_id for efficiency
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)  # Unique identifier for each item in the order
    item_order_id = db.Column(UUID, db.ForeignKey('orders.id'), nullable=False)
    production_round_id = db.Column(UUID, db.ForeignKey('production_rounds.id'), nullable=False, index=True)  # Indexed for efficient filtering
    
    item_status = db.Column(db.String(50), default="item")  # Tracks the current stage: "item", ""in_stock", "in_process", "refunded", "transferred", "delivered"

    # Region record, to handle tax calculation and multi-warehouse scenario
    region_id = db.Column(db.Integer, db.ForeignKey("regions.id"), nullable=False)

    # Warehouse assignment (Initially NULL, assigned during stocking acceptance)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=True)

    # Snapshot fields
    unit_price = db.Column(db.Float, nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    product_image_path = db.Column(db.String(255), nullable=False)

    # Relationships
    item_order = db.relationship("ItemOrder", back_populates="order_items")
    production_round = db.relationship("ProductionRound", back_populates="item_order_items")
    region = db.relationship("Region", back_populates="items")
    warehouse = db.relationship("Warehouse", back_populates="items")  # New relationship




    def populate_snapshot(self, production_round):
        """
        Populate the snapshot fields using data from the ProductionRound and associated Product.
        """
        self.unit_price = production_round.price
        self.product_name = production_round.product.name
        self.product_image_path = production_round.product.artwork.image_path

    def __repr__(self):
        return f"<ItemOrderItem {self.id} order={self.item_order_id} type={self.item_type}>"



class RefundItemOrder(db.Model):
    __tablename__ = 'refund_item_orders'
    __table_args__ = (db.Index('ix_refund_item_order_customer_id', 'customer_id'),)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    item_order_item_id = db.Column(UUID(as_uuid=True), db.ForeignKey('item_order_items.id'), nullable=False)
    is_auto = db.Column(db.Boolean, default=False)  # whether the refund is auto or not
    reason = db.Column(db.String(100), default='refund')    #auto-full-refund, auto-partial_refund, 
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Refund-specific fields
    refund_method = db.Column(db.String(50), nullable=True)  # e.g., "wallet","credit_card"
    refund_status = db.Column(db.String(50), default="pending")  # "pending", "processed"
    refund_timestamp = db.Column(db.DateTime, nullable=True)
    refund_reference = db.Column(db.String(100), nullable=True)
    refund_amount = db.Column(db.Float, nullable=True)

    tax_amount = db.Column(db.Float, default=0.0)  # Tax refunded, if applicable

    # Relationships
    customer = db.relationship("Customer", back_populates="refund_item_orders")
    item_order_item = db.relationship("ItemOrderItem", backref="refunds")
        


    def __repr__(self):
        return f"<RefundItemOrder {self.id} reason={self.reason} status={self.status}>"



class TransferItemOrder(db.Model):
    __tablename__ = 'transfer_item_orders'
    __table_args__ = (db.Index('ix_transfer_item_order_from_to', 'from_customer_id', 'to_customer_id'),)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    from_customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    to_customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    item_order_item_id = db.Column(UUID(as_uuid=True), db.ForeignKey('item_order_items.id'), nullable=False)  # Direct link to ItemOrderItem
    created_at = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(50), default="initiated")  # need to decide the operation flow

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
    item_order_item = db.relationship("ItemOrderItem", backref="transfers") # Direct relationship to ItemOrderItem


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



# transfer and order
# two types of transfer: item transfer and delivered item transfer
# item transfer is for the item (when it is still in the platform)
# delivered item is for the item that has been delivered to the customer
#   collection showcase for customer
#   transaction (but the implementation level... maybe open later?)

# two types of order: item order and delivery order



# Region record, with tax rate implemented

class Region(db.Model):
    __tablename__ = "regions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # Unique region ID
    name = db.Column(db.String(255), nullable=False, unique=True)  # Human-readable name (e.g., "California, US")
    tax_rate = db.Column(db.Float, nullable=False, default=0.0)  # Region-based tax rate on product
    delivery_tax_rate = db.Column(db.Float, nullable=False, default=0.0)  # Region-based tax rate on delivery order

    # Relationships
    warehouse_mappings = db.relationship("WarehouseRegionMapping", back_populates="region")
    items = db.relationship("ItemOrderItem", back_populates="region")
    delivery_orders = db.relationship("DeliveryOrder", back_populates="region")  # Fixed reference name
    delivery_cost_grids = db.relationship("DeliveryCostGrid", back_populates="region")  # New


    def __repr__(self):
        return f"<Region(id={self.id}, name={self.name}, tax_rate={self.tax_rate})>"




# warehouse and region mapping

class WarehouseRegionMapping(db.Model):
    __tablename__ = "warehouse_region_mapping"

    region_id = db.Column(db.Integer, db.ForeignKey("regions.id"), primary_key=True)  # Correct ForeignKey reference
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)  # Integer type for consistency

    # Relationships
    region = db.relationship("Region", back_populates="warehouse_mappings")  # Fixed reference to Region
    warehouse = db.relationship("Warehouse", back_populates="regions")  # Correct relationship

    def __repr__(self):
        return f"<WarehouseRegionMapping(region_id={self.region_id}, warehouse_id={self.warehouse_id})>"


# warehouse system
# WarehouseStorage for storage unit and WarehouseRecord for item record



class Warehouse(db.Model):
    __tablename__ = "warehouses"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # Unique Warehouse ID
    name = db.Column(db.String(255), nullable=False, unique=True)
    location = db.Column(db.String(255), nullable=False)  # Address or city

    # Relationships
    regions = db.relationship("WarehouseRegionMapping", back_populates="warehouse")  # Fixed reference
    storage_spaces = db.relationship("WarehouseStorage", back_populates="warehouse")
    items = db.relationship("ItemOrderItem", back_populates="warehouse")  # Tracks stocked items
    delivery_orders = db.relationship("DeliveryOrder", back_populates="warehouse")
    delivery_cost_grids = db.relationship("DeliveryCostGrid", back_populates="warehouse")
    delivery_admins = db.relationship("DeliveryAdmin", back_populates="warehouse", lazy=True)  # New relationship

    def __repr__(self):
        return f"<Warehouse(id={self.id}, name={self.name}, location={self.location})>"



class WarehouseStorage(db.Model):
    __tablename__ = 'warehouse_storages'

    location_name = db.Column(db.String(255), primary_key=True)  # Generated from inputs
    aisle_number = db.Column(db.Integer, nullable=False)
    shelf_number = db.Column(db.Integer, nullable=False)
    position_number = db.Column(db.Integer, nullable=False)
    size = db.Column(db.Integer, nullable=False)  # Storage size: 1 (small), 2 (medium), 3 (large)
    is_available = db.Column(db.Boolean, default=True, nullable=False)  # Availability status
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)  # Which warehouse

    # Relationships
    warehouse = db.relationship("Warehouse", back_populates="storage_spaces")
    warehouse_records = db.relationship("WarehouseRecord", back_populates="storage_location", lazy=True)

    @staticmethod
    def generate_location_name(warehouse_id, aisle_number, shelf_number, position_number):
        """Generate location_name based on inputs."""
        return f"WH{warehouse_id}-A{aisle_number:02d}-S{shelf_number:02d}-P{position_number:02d}"
    


    def __repr__(self):
        return (f"<WarehouseStorage(location_name={self.location_name}, size={self.size}, "
                f"is_available={self.is_available}, warehouse={self.warehouse})>")





class WarehouseRecord(db.Model):
    __tablename__ = 'warehouse_records'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    production_round_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_rounds.id'), nullable=False, index=True)
    warehouse_storage_location = db.Column(db.String(255), db.ForeignKey('warehouse_storages.location_name'), nullable=False)  # Updated foreign key
    quantity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)  # Short description of what is in, item or gift?
    warehouse_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('warehouse_admins.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now, nullable=False)

    # Relationships
    production_round = db.relationship("ProductionRound", back_populates="warehouse_records")
    warehouse_admin = db.relationship("WarehouseAdmin", back_populates="managed_records")
    storage_location = db.relationship("WarehouseStorage", back_populates="warehouse_records")  # Reference to WarehouseStorage

    def __repr__(self):
        return f"<WarehouseRecord(id={self.id}, quantity={self.quantity})>"






class DeliveryOrder(db.Model):
    __tablename__ = 'delivery_orders'
    __table_args__ = (db.Index('ix_delivery_order_customer_id', 'customer_id'),)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id'), nullable=False)
    delivery_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('delivery_admins.id'), nullable=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)  #related to warehouse, which warehouse would handle this order?
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=False)
    postal_code_prefix = db.Column(db.String(10), nullable=True)
    shipping_address = db.Column(db.String(255), nullable=False)
    delivery_cost = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="created")    #created, in_process, delivering, received
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    delivery_item = db.Column(JSON, nullable=False, default=list)  # Example:  production_round_id,item_id;

    # Payment columns (one payment only)
    payment_method = db.Column(db.String(50), nullable=True)
    payment_status = db.Column(db.String(50), default='unpaid') #I'm wondering if it should just be True or False?
    payment_timestamp = db.Column(db.DateTime, nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)

    tax_amount = db.Column(db.Float, default=0.0)  # Tax on delivery cost, if applicable
    transaction_fee = db.Column(db.Float, default=0.0)  # Fee for delivery payment

    # Relationships
    customer = db.relationship("Customer", back_populates="delivery_orders")
    delivery_admin = db.relationship("DeliveryAdmin", back_populates="delivery_orders")
    warehouse = db.relationship("Warehouse", back_populates="delivery_orders")  # New
    region = db.relationship("Region", back_populates="delivery_orders")  # New
    packages = db.relationship("DeliveryPackage", back_populates="delivery_order", lazy=True)

    @validates("delivery_item")
    def validate_delivery_item(self, key, value):
        if not isinstance(value, list):
            raise ValueError("delivery_item must be a list")
        for item in value:
            if not isinstance(item, dict) or "item_id" not in item or "production_round_id" not in item:
                raise ValueError("Each delivery_item must be a dict with 'item_id' and 'production_round_id'")
            if not isinstance(item["item_id"], str) or not isinstance(item["production_round_id"], str):
                raise ValueError("'item_id' and 'production_round_id' must be strings")
        return value

    # Functions

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
    __table_args__ = (db.Index('ix_delivery_package_delivery_order_id', 'delivery_order_id'),)

    package_number = db.Column(db.String(100), unique=True, nullable=False, primary_key=True)
    delivery_order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('delivery_orders.id'), nullable=False)

    # New attributes
    status = db.Column(db.String(50), nullable=False, default="created")  # created, in_transit, delivered
    packaging_video_path = db.Column(db.String(255), nullable=True)  # Path or URL to the packaging video

    # Relationships
    delivery_order = db.relationship("DeliveryOrder", back_populates="packages")




class DeliveryCostGrid(db.Model):
    __tablename__ = 'delivery_cost_grid'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=False)  # Required for region-specific costs
    postal_code_prefix = db.Column(db.String(10), nullable=True)  # Optional refinement
    base_cost = db.Column(db.Float, nullable=False)  # Flat delivery cost
    per_delivery_point = db.Column(db.Float, nullable=False, default=0.0)  # Cost per delivery point

    # Relationships
    warehouse = db.relationship("Warehouse", back_populates="delivery_cost_grids")
    region = db.relationship("Region", back_populates="delivery_cost_grids")


# for revenue, tax and transaction fee
# only recorded when the items are delivered, suggested for pre-order system
# payouts for artist/ip holder are not regional so it is not here (probably in AccountingTransaction)


class RegionFinancialSummary(db.Model):
    __tablename__ = 'region_financial_summaries'
    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid6)
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=False)
    total_purchase_amount = db.Column(db.Float, default=0.0)  # Sum of customer purchases (total amount)
    total_item_tax_amount = db.Column(db.Float, default=0.0)  # Sum of taxes on items collected
    total_delivery_tax_amount = db.Column(db.Float, default=0.0)  # Sum of taxes on delivery collected
    total_transaction_fee = db.Column(db.Float, default=0.0)  # Sum of fees collected
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    region = db.relationship("Region", backref="financial_summaries")


class AccountingTransaction(db.Model):
    __tablename__ = 'accounting_transactions'
    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid6)
    transaction_type = db.Column(db.String(50), nullable=False) # artist_payout, factory_sample_payment, factory_production_payment, factory_stage_goal_payment…
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='requested')  # "requested", "approved", "rejected"
    created_at = db.Column(db.DateTime, default=datetime.now)
    approved_at = db.Column(db.DateTime, nullable=True)
    finance_admin_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey('finance_admins.id'), nullable=True)
    production_round_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey('production_rounds.id'), nullable=True)

    # Relationships
    production_round = db.relationship("ProductionRound", backref="accounting_transactions")
    finance_admin = db.relationship("FinanceAdmin", back_populates="transactions")

    @staticmethod
    def initiate_transaction(transaction_type, amount, production_round_id=None):
        transaction = AccountingTransaction(
            transaction_type=transaction_type,
            amount=amount,
            production_round_id=production_round_id,
            status="requested"
        )
        db.session.add(transaction)
        db.session.commit()
        return transaction
    



# artist incentive, need update


class Payout(db.Model):
    __tablename__ = 'payouts'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artists.id'), nullable=False, index=True)
    production_round_id = db.Column(UUID(as_uuid=True), db.ForeignKey('production_rounds.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)  # Total amount paid to the artist
    status = db.Column(db.String(50), nullable=False, default="pending")  # "pending", "completed"
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    accounting_transaction_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey('accounting_transactions.id'), nullable=True)

    # Relationships
    artist = db.relationship("Artist", back_populates="payouts")
    production_round = db.relationship("ProductionRound", back_populates="payouts")
    accounting_transaction = db.relationship("AccountingTransaction", backref="payout", uselist=False)




# Dialog Model to Track Messages Between Artist and Order Management Admin
# Update Dialog model to support rich content and multiple files
class Dialog(db.Model):
    __tablename__ = 'dialogs'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
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
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    dialog_id = db.Column(UUID(as_uuid=True), db.ForeignKey('dialogs.id'), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(200), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relationships
    dialog = db.relationship("Dialog", back_populates="files")



# Design File Model
class DesignFile(db.Model):
    __tablename__ = 'design_files'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    filename = db.Column(db.String(300), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)
    product = db.relationship("Product", back_populates="design_files")



# Notification model with updated type attribute
class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid6)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.String(300), nullable=False)
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
            is_read=False,
            timestamp=datetime.now(timezone.utc),
            type=type  # Add the notification type here
        )
        db.session.add(new_notification)
        db.session.commit()