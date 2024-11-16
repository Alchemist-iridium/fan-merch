from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship

# Define the database instance
db = SQLAlchemy()

# Define Models

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # "customer", "artist", "admin"
    account_balance = db.Column(db.Float, default=0.0)
    shipping_addresses = db.relationship('ShippingAddress', backref='user', lazy=True)
    works = relationship("Artwork", back_populates="artist", lazy=True)

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
    id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'admin',
    }

class ArtworkApprovalAdmin(Admin):
    __tablename__ = 'artwork_approval_admins'
    id = db.Column(db.Integer, db.ForeignKey('admins.id'), primary_key=True)

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
    id = db.Column(db.Integer, db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'order_management_admin',
    }

    products_managed = relationship('Product', back_populates='managing_admin', lazy=True)

    def update_product_status(self, product, status):
        if product.assigned_admin_id != self.id:
            raise PermissionError("This product is not assigned to this admin.")
        product.status = status
        db.session.commit()

class SuperAdmin(Admin):
    __tablename__ = 'super_admins'
    id = db.Column(db.Integer, db.ForeignKey('admins.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'super_admin',
    }

    def assign_order_management_admin(self, product, order_management_admin):
        product.assigned_admin_id = order_management_admin.id
        db.session.commit()

class Artist(User):
    __tablename__ = 'artists'
    id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'artist',
    }

class Customer(User):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'customer',
    }

class ShippingAddress(db.Model):
    __tablename__ = 'shipping_addresses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    address = db.Column(db.String(200), nullable=False)

class Artwork(db.Model):
    __tablename__ = 'artworks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    image_path = db.Column(db.String(300), nullable=False)
    manufacturing_specs = db.Column(db.String(300), nullable=True)
    hard_tags = db.Column(db.String(300), nullable=False)  # Store as a string
    soft_tags = db.Column(db.String(300), nullable=True)  # Store as a string
    approval_status = db.Column(db.String(50), nullable=False, default='Pending')
    artist_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    artist = relationship("User", back_populates="works")
    products = relationship("Product", back_populates="artwork", lazy=True)

    @property
    def hard_tags_list(self):
        """Convert hard_tags string to a list."""
        return self.hard_tags.split('#') if self.hard_tags else []

    @property
    def soft_tags_list(self):
        """Convert soft_tags string to a list."""
        return self.soft_tags.split('#') if self.soft_tags else []

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    artwork_id = db.Column(db.Integer, db.ForeignKey('artworks.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='make_sample')  # Stages: "make_sample", "production", "detect_flaw", "stock delivery"
    assigned_admin_id = db.Column(db.Integer, db.ForeignKey('order_management_admins.id'), nullable=True)

    artwork = relationship("Artwork", back_populates="products")
    managing_admin = relationship("OrderManagementAdmin", foreign_keys=[assigned_admin_id], back_populates="products_managed")

    def assign_admin(self, admin_id):
        """Assign a specific order_management_admin to this product."""
        admin = OrderManagementAdmin.query.get(admin_id)
        if not admin:
            raise ValueError("Admin not found.")
        self.assigned_admin_id = admin_id
        db.session.commit()
        return f"Product {self.id} successfully assigned to Admin {admin_id}"

    def update_status(self, new_status):
        """Update the production status of this product."""
        valid_statuses = ["make_sample", "production", "detect_flaw", "stock delivery"]
        if new_status not in valid_statuses:
            raise ValueError("Invalid status update. Choose from 'make_sample', 'production', 'detect_flaw', or 'stock delivery'.")
        self.status = new_status
        db.session.commit()
        return f"Product {self.id} status updated to {new_status}"

    def is_assignable(self):
        """Check if this product can be assigned to an admin (i.e., if it's unassigned)."""
        return self.assigned_admin_id is None

# Updated create_user function to handle correct user types
def create_user(name, email, password, role):
    if User.query.filter_by(email=email).first():
        raise ValueError("User with this email already exists")
    hashed_password = generate_password_hash(password)
    new_user = None

    # Use appropriate classes based on the role to correctly use polymorphic identity
    if role == 'customer':
        new_user = Customer(name=name, email=email, password_hash=hashed_password, role=role)
    elif role == 'artist':
        new_user = Artist(name=name, email=email, password_hash=hashed_password, role=role)
    elif role == 'artwork_approval_admin':
        new_user = ArtworkApprovalAdmin(name=name, email=email, password_hash=hashed_password, role=role)
    elif role == 'order_management_admin':
        new_user = OrderManagementAdmin(name=name, email=email, password_hash=hashed_password, role=role)
    elif role == 'super_admin':
        new_user = SuperAdmin(name=name, email=email, password_hash=hashed_password, role=role)
    else:
        raise ValueError("Invalid role specified")

    if new_user:
        db.session.add(new_user)
        db.session.commit()
