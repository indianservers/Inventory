from datetime import datetime
from app.extensions import db


class Purchase(db.Model):
    __tablename__ = 'purchases'
    id = db.Column(db.Integer, primary_key=True)
    purchase_no = db.Column(db.String(30), unique=True, nullable=False)
    purchase_date = db.Column(db.Date, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    currency_id = db.Column(db.Integer, db.ForeignKey('currencies.id'), nullable=True)
    exchange_rate_snapshot = db.Column(db.Numeric(12, 6), default=1)
    original_currency_total = db.Column(db.Numeric(12, 2), default=0)
    supplier_invoice_no = db.Column(db.String(50))
    supplier_invoice_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='Approved')
    cancelled_at = db.Column(db.DateTime)
    cancellation_reason = db.Column(db.Text)
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    discount_total = db.Column(db.Numeric(12, 2), default=0)
    tax_total = db.Column(db.Numeric(12, 2), default=0)
    shipping_charges = db.Column(db.Numeric(12, 2), default=0)
    other_charges = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    paid_amount = db.Column(db.Numeric(12, 2), default=0)
    balance_amount = db.Column(db.Numeric(12, 2), default=0)
    payment_status = db.Column(db.String(20), default='Unpaid')  # Paid, Partial, Unpaid
    notes = db.Column(db.Text)
    attachment = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship('PurchaseItem', backref='purchase', lazy='dynamic', cascade='all, delete-orphan')
    warehouse = db.relationship('Warehouse', backref='purchases')
    currency = db.relationship('Currency', backref='purchases')

    def update_payment_status(self):
        paid = float(self.paid_amount or 0)
        total = float(self.grand_total or 0)
        if paid <= 0:
            self.payment_status = 'Unpaid'
        elif paid >= total:
            self.payment_status = 'Paid'
        else:
            self.payment_status = 'Partial'
        self.balance_amount = total - paid

    def __repr__(self):
        return f'<Purchase {self.purchase_no}>'


class PurchaseItem(db.Model):
    __tablename__ = 'purchase_items'
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    discount = db.Column(db.Numeric(5, 2), default=0)
    discount_amount = db.Column(db.Numeric(12, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product', backref='purchase_items')

    def __repr__(self):
        return f'<PurchaseItem {self.product_id} x {self.quantity}>'


class PurchaseReturn(db.Model):
    __tablename__ = 'purchase_returns'
    id = db.Column(db.Integer, primary_key=True)
    return_no = db.Column(db.String(30), unique=True, nullable=False)
    return_date = db.Column(db.Date, nullable=False)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    tax_total = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    reason = db.Column(db.Text)
    refund_mode = db.Column(db.String(20), default='Credit Note')
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship('PurchaseReturnItem', backref='purchase_return', lazy='dynamic', cascade='all, delete-orphan')
    purchase = db.relationship('Purchase', backref='returns')
    supplier = db.relationship('Supplier', backref='purchase_returns')
    warehouse = db.relationship('Warehouse', backref='purchase_returns')

    def __repr__(self):
        return f'<PurchaseReturn {self.return_no}>'


class PurchaseReturnItem(db.Model):
    __tablename__ = 'purchase_return_items'
    id = db.Column(db.Integer, primary_key=True)
    purchase_return_id = db.Column(db.Integer, db.ForeignKey('purchase_returns.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product', backref='purchase_return_items')


class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'
    id = db.Column(db.Integer, primary_key=True)
    po_no = db.Column(db.String(30), unique=True, nullable=False)
    po_date = db.Column(db.Date, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    expected_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='Draft')
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    discount_total = db.Column(db.Numeric(12, 2), default=0)
    tax_total = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)
    terms = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    supplier = db.relationship('Supplier', backref='purchase_orders')
    warehouse = db.relationship('Warehouse', backref='purchase_orders')
    items = db.relationship('PurchaseOrderItem', backref='po', lazy='dynamic', cascade='all, delete-orphan')


class PurchaseOrderItem(db.Model):
    __tablename__ = 'purchase_order_items'
    id = db.Column(db.Integer, primary_key=True)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    discount = db.Column(db.Numeric(5, 2), default=0)
    discount_amount = db.Column(db.Numeric(12, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    received_qty = db.Column(db.Numeric(12, 3), default=0)
    product = db.relationship('Product', backref='purchase_order_items')


class GoodsReceiptNote(db.Model):
    __tablename__ = 'goods_receipt_notes'
    id = db.Column(db.Integer, primary_key=True)
    grn_no = db.Column(db.String(30), unique=True, nullable=False)
    grn_date = db.Column(db.Date, nullable=False)
    po_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    po = db.relationship('PurchaseOrder', backref='grns')
    supplier = db.relationship('Supplier', backref='grns')
    warehouse = db.relationship('Warehouse', backref='grns')
    items = db.relationship('GoodsReceiptItem', backref='grn', lazy='dynamic', cascade='all, delete-orphan')


class GoodsReceiptItem(db.Model):
    __tablename__ = 'goods_receipt_items'
    id = db.Column(db.Integer, primary_key=True)
    grn_id = db.Column(db.Integer, db.ForeignKey('goods_receipt_notes.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    po_item_id = db.Column(db.Integer, db.ForeignKey('purchase_order_items.id'), nullable=True)
    expected_qty = db.Column(db.Numeric(12, 3), default=0)
    received_qty = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product', backref='goods_receipt_items')
    po_item = db.relationship('PurchaseOrderItem', backref='goods_receipt_items')


class VendorCredit(db.Model):
    __tablename__ = 'vendor_credits'
    id = db.Column(db.Integer, primary_key=True)
    credit_no = db.Column(db.String(30), unique=True, nullable=False)
    credit_date = db.Column(db.Date, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), nullable=True)
    purchase_return_id = db.Column(db.Integer, db.ForeignKey('purchase_returns.id'), nullable=True)
    reason = db.Column(db.Text)
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    tax_total = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    applied_amount = db.Column(db.Numeric(12, 2), default=0)
    refunded_amount = db.Column(db.Numeric(12, 2), default=0)
    status = db.Column(db.String(20), default='Issued')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    supplier = db.relationship('Supplier', backref='vendor_credits')
    purchase = db.relationship('Purchase', backref='vendor_credits')
    purchase_return = db.relationship('PurchaseReturn', backref='vendor_credits')
    items = db.relationship('VendorCreditItem', backref='vendor_credit', lazy='dynamic', cascade='all, delete-orphan')


class VendorCreditItem(db.Model):
    __tablename__ = 'vendor_credit_items'
    id = db.Column(db.Integer, primary_key=True)
    vendor_credit_id = db.Column(db.Integer, db.ForeignKey('vendor_credits.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product', backref='vendor_credit_items')
