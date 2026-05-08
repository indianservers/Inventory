from datetime import datetime
from app.extensions import db


class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    customer_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    business_name = db.Column(db.String(200))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(20))
    alt_phone = db.Column(db.String(20))
    billing_address = db.Column(db.Text)
    shipping_address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    country = db.Column(db.String(100), default='India')
    postal_code = db.Column(db.String(20))
    gst_number = db.Column(db.String(20))
    pan_number = db.Column(db.String(20))
    credit_limit = db.Column(db.Numeric(12, 2), default=0)
    opening_balance = db.Column(db.Numeric(12, 2), default=0)
    current_balance = db.Column(db.Numeric(12, 2), default=0)
    payment_terms = db.Column(db.Integer, default=30)
    status = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sales = db.relationship('Sale', backref='customer', lazy='dynamic')
    ledger_entries = db.relationship('CustomerLedger', backref='customer', lazy='dynamic')
    payments_received = db.relationship('PaymentReceived', backref='customer', lazy='dynamic')

    @property
    def outstanding(self):
        from app.models.accounts import CustomerLedger
        from sqlalchemy import func
        result = db.session.query(
            func.sum(CustomerLedger.debit) - func.sum(CustomerLedger.credit)
        ).filter_by(customer_id=self.id).scalar()
        return float(result or 0)

    def __repr__(self):
        return f'<Customer {self.name}>'


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    supplier_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    business_name = db.Column(db.String(200))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(20))
    alt_phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    country = db.Column(db.String(100), default='India')
    postal_code = db.Column(db.String(20))
    gst_number = db.Column(db.String(20))
    pan_number = db.Column(db.String(20))
    opening_balance = db.Column(db.Numeric(12, 2), default=0)
    current_balance = db.Column(db.Numeric(12, 2), default=0)
    payment_terms = db.Column(db.Integer, default=30)
    status = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    purchases = db.relationship('Purchase', backref='supplier', lazy='dynamic')
    ledger_entries = db.relationship('SupplierLedger', backref='supplier', lazy='dynamic')
    payments_made = db.relationship('PaymentMade', backref='supplier', lazy='dynamic')

    @property
    def outstanding(self):
        from app.models.accounts import SupplierLedger
        from sqlalchemy import func
        result = db.session.query(
            func.sum(SupplierLedger.credit) - func.sum(SupplierLedger.debit)
        ).filter_by(supplier_id=self.id).scalar()
        return float(result or 0)

    def __repr__(self):
        return f'<Supplier {self.name}>'
