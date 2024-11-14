from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
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
    role = db.Column(db.String(50), nullable=False)  # "Customer", "Artist", "Admin"
    account_balance = db.Column(db.Float, default=0.0)
    shipping_addresses = db.relationship('ShippingAddress', backref='user', lazy=True)

    # Updated relationship to link to Artwork model
    works = relationship("Artwork", back_populates="artist", lazy=True)


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def update_account_balance(self, amount):
        self.account_balance += amount


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

    @property
    def hard_tags_list(self):
        """Convert hard_tags string to a list."""
        return self.hard_tags.split('#') if self.hard_tags else []

    @property
    def soft_tags_list(self):
        """Convert soft_tags string to a list."""
        return self.soft_tags.split('#') if self.soft_tags else []


# Example Methods

def create_user(name, email, password, role):
    if User.query.filter_by(email=email).first():
        raise ValueError("User with this email already exists")
    hashed_password = generate_password_hash(password)
    new_user = User(name=name, email=email, password_hash=hashed_password, role=role)
    db.session.add(new_user)
    db.session.commit()


def create_artwork(artist_id, title, description, image_path, manufacturing_specs, hard_tags, soft_tags=None):
    # Hard tags and soft tags should be strings with tags separated by commas
    if not hard_tags:
        raise ValueError("At least one hard tag must be provided for classification.")
    new_work = Artwork(
        artist_id=artist_id,
        title=title,
        description=description,
        image_path=image_path,
        manufacturing_specs=manufacturing_specs,
        hard_tags=hard_tags,
        soft_tags=soft_tags or "",
        approval_status='Pending'
    )
    db.session.add(new_work)
    db.session.commit()
