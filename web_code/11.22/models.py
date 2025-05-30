from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
from extensions import db
from datetime import datetime, timezone
import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import func

# Define Models

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # "customer", "artist", "admin"
    account_balance = db.Column(db.Float, default=0.0)

    # Updated relationship with ShippingAddress (use unique backref name)
    shipping_addresses = db.relationship('ShippingAddress', back_populates='user', lazy=True)

    # Updated relationship with Artwork (used by Artists)
    artworks = db.relationship("Artwork", back_populates="artist", lazy=True)

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


class Admin(User):
    __tablename__ = 'admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'admin',
    }


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


class OrderManagementAdmin(Admin):
    __tablename__ = 'order_management_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)
    main_production_species = db.Column(db.String(200), nullable=False, default="general")  # Example: "pins, keychains"
    
    __mapper_args__ = {
        'polymorphic_identity': 'order_management_admin',
    }

    products_managed = relationship('Product', back_populates='managing_admin', lazy=True)

    def get_product_count(self):
        return len(self.products_managed)

    def update_product_status(self, product, status):
        if product.assigned_admin_id != self.id:
            raise PermissionError("This product is not assigned to this admin.")
        product.production_status = status
        db.session.commit()


class ProductApprovalAdmin(Admin):
    __tablename__ = 'product_approval_admins'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'product_approval_admin',
    }

    def assign_order_management_admin(self, product, order_management_admin):
        product.assigned_admin_id = order_management_admin.id
        db.session.commit()


class Artist(User):
    __tablename__ = 'artists'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)

    # Relationship to artworks
    artworks = db.relationship("Artwork", back_populates="artist", lazy=True)

    __mapper_args__ = {
        'polymorphic_identity': 'artist',
    }


class Customer(User):
    __tablename__ = 'customers'
    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'customer',
    }


class ShippingAddress(db.Model):
    __tablename__ = 'shipping_addresses'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    # Updated relationship to User (use unique back_populates name)
    user = db.relationship('User', back_populates='shipping_addresses')


class Artwork(db.Model):
    __tablename__ = 'artworks'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    image_path = db.Column(db.String(300), nullable=False)
    manufacturing_specs = db.Column(db.String(300), nullable=True)
    hard_tags = db.Column(db.String(300), nullable=False)  # Store as a string
    soft_tags = db.Column(db.String(300), nullable=True)  # Store as a string
    approval_status = db.Column(db.String(50), nullable=False, default='Pending')
    artist_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    disapproval_reason = db.Column(db.Text, nullable=True)  # New field to store disapproval reason

    # Updated relationship
    artist = db.relationship("Artist", back_populates="artworks")
    products = db.relationship("Product", back_populates="artwork", lazy=True)




class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(200), nullable=False)
    production_specs = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    manufacture_type = db.Column(db.String(50), nullable=False)  # "platform arranged" or "artist arranged"
    production_status = db.Column(db.String(50), nullable=False, default='Pending')
    display_status = db.Column(db.String(50), nullable=False, default='not display')  # "not display" or "on display"
    production_status_history = db.Column(db.PickleType, nullable=False, default={})  # Track production status changes with timestamps
    product_price = db.Column(db.Float, nullable=True, default=0.0)
    artwork_id = db.Column(UUID(as_uuid=True), db.ForeignKey('artworks.id'), nullable=False)
    assigned_admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('order_management_admins.id'), nullable=True)
    introduction = db.Column(db.Text, nullable=True)  # Allows storing rich text content
    disapproval_reason = db.Column(db.Text, nullable=True)  # To store the reason for disapproval

    # Relationships
    artwork = db.relationship("Artwork", back_populates="products")
    managing_admin = db.relationship("OrderManagementAdmin", back_populates="products_managed")
    design_files = db.relationship("DesignFile", back_populates="product", cascade="all, delete-orphan")


    def assign_admin(self, admin_id):
        """Assign a specific Order Management Admin to manage the product."""
        admin = OrderManagementAdmin.query.get(admin_id)
        if not admin:
            raise ValueError("Admin not found.")
        self.assigned_admin_id = admin_id
        db.session.commit()
        return f"Product {self.id} successfully assigned to Admin {admin_id}"

    def update_status(self, new_status):
        """Update the production status of the product and log the update with timestamp."""
        valid_statuses = ["make_sample", "production", "detect_flaw", "stock delivery"]
        if new_status not in valid_statuses:
            raise ValueError("Invalid status update. Choose from 'make_sample', 'production', 'detect_flaw', or 'stock delivery'.")
        
        self.production_status = new_status
        self.production_status_history[new_status] = datetime.now(timezone.utc)
        db.session.commit()
        return f"Product {self.id} status updated to {new_status}"

    def is_assignable(self):
        """Check if this product can be assigned to an Order Management Admin (i.e., if it's unassigned)."""
        return self.assigned_admin_id is None

    def disapprove(self, reason):
        """Disapprove the product with a detailed reason."""
        self.production_status = 'Disapproved'
        self.disapproval_reason = reason
        db.session.commit()
        return f"Product {self.id} disapproved with reason: {reason}"

    def request_price_or_status_change(self, requested_by, new_price=None, new_status=None):
        """
        Allow the artist to send requests to Order Management Admin for status or price changes.
        Only applicable for products managed by artists.
        """
        if self.manufacture_type != "artist arranged":
            raise ValueError("Only artist-arranged products can request changes.")
        if not self.assigned_admin_id:
            raise ValueError("This product does not have an assigned Order Management Admin.")

        change_request = {
            'requested_by': requested_by,
            'new_price': new_price,
            'new_status': new_status,
            'timestamp': datetime.now(timezone.utc)
        }
        
        # Handle the request as needed - this is a placeholder; you may implement more detailed logic
        # for notifying or handling these change requests in another part of your system.
        return change_request
    
    def toggle_display_status(self):
        # Toggle the display status between "on display" and "not display"
        if self.display_status == "not display":
            self.display_status = "on display"
        else:
            self.display_status = "not display"
        db.session.commit()
        return f"Product {self.id} display status updated to {self.display_status}"



class DesignFile(db.Model):
    __tablename__ = 'design_files'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = db.Column(db.String(300), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)  # e.g., "image/png", "application/pdf"
    upload_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Foreign key to link with Product
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id'), nullable=False)

    # Relationship
    product = db.relationship("Product", back_populates="design_files")

