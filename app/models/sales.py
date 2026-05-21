from datetime import datetime
from app.extensions import db


class Sale(db.Model):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(30), unique=True, nullable=False)
    invoice_date = db.Column(db.Date, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    sale_type = db.Column(db.String(10), default='Credit')  # Cash, Credit
    status = db.Column(db.String(20), default='Issued')  # Draft, Issued, Partially Paid, Paid, Overdue, Cancelled
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    discount_total = db.Column(db.Numeric(12, 2), default=0)
    tax_total = db.Column(db.Numeric(12, 2), default=0)
    shipping_charges = db.Column(db.Numeric(12, 2), default=0)
    round_off = db.Column(db.Numeric(5, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    paid_amount = db.Column(db.Numeric(12, 2), default=0)
    balance_amount = db.Column(db.Numeric(12, 2), default=0)
    payment_status = db.Column(db.String(20), default='Unpaid')
    due_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    terms = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    issued_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    cancellation_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship('SaleItem', backref='sale', lazy='dynamic', cascade='all, delete-orphan')
    warehouse = db.relationship('Warehouse', backref='sales')

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
        if self.status != "Cancelled":
            if self.payment_status == "Paid":
                self.status = "Paid"
            elif self.payment_status == "Partial":
                self.status = "Partially Paid"
            elif self.status != "Draft":
                self.status = "Issued"

    @property
    def display_status(self):
        from datetime import date

        if self.status in ["Draft", "Cancelled", "Paid"]:
            return self.status
        if self.balance_amount and float(self.balance_amount or 0) > 0 and self.due_date and self.due_date < date.today():
            return "Overdue"
        return self.status or self.payment_status or "Issued"

    def __repr__(self):
        return f'<Sale {self.invoice_no}>'


class SaleItem(db.Model):
    __tablename__ = 'sale_items'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    discount = db.Column(db.Numeric(5, 2), default=0)
    discount_amount = db.Column(db.Numeric(12, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    cost_price = db.Column(db.Numeric(12, 4), default=0)
    product = db.relationship('Product', backref='sale_items')

    def __repr__(self):
        return f'<SaleItem {self.product_id} x {self.quantity}>'


class SalesReturn(db.Model):
    __tablename__ = 'sales_returns'
    id = db.Column(db.Integer, primary_key=True)
    return_no = db.Column(db.String(30), unique=True, nullable=False)
    return_date = db.Column(db.Date, nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
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
    items = db.relationship('SalesReturnItem', backref='sales_return', lazy='dynamic', cascade='all, delete-orphan')
    sale = db.relationship('Sale', backref='returns')
    sales_return_customer = db.relationship('Customer', backref='sales_returns', foreign_keys=[customer_id])
    warehouse = db.relationship('Warehouse', backref='sales_returns')

    def __repr__(self):
        return f'<SalesReturn {self.return_no}>'


class SalesReturnItem(db.Model):
    __tablename__ = 'sales_return_items'
    id = db.Column(db.Integer, primary_key=True)
    sales_return_id = db.Column(db.Integer, db.ForeignKey('sales_returns.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product', backref='sales_return_items')


class Quotation(db.Model):
    __tablename__ = 'quotations'
    id = db.Column(db.Integer, primary_key=True)
    quotation_no = db.Column(db.String(30), unique=True, nullable=False)
    quotation_date = db.Column(db.Date, nullable=False)
    valid_until = db.Column(db.Date)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    discount_total = db.Column(db.Numeric(12, 2), default=0)
    tax_total = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)
    terms = db.Column(db.Text)
    status = db.Column(db.String(20), default='Draft')  # Draft, Sent, Accepted, Rejected, Expired, Converted
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship('QuotationItem', backref='quotation', lazy='dynamic', cascade='all, delete-orphan')
    quotation_customer = db.relationship('Customer', backref='quotations', foreign_keys=[customer_id])

    def __repr__(self):
        return f'<Quotation {self.quotation_no}>'


class QuotationItem(db.Model):
    __tablename__ = 'quotation_items'
    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.Integer, db.ForeignKey('quotations.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    discount = db.Column(db.Numeric(5, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product', backref='quotation_items')


class ProformaInvoice(db.Model):
    __tablename__ = 'proforma_invoices'
    id = db.Column(db.Integer, primary_key=True)
    proforma_no = db.Column(db.String(30), unique=True, nullable=False)
    proforma_date = db.Column(db.Date, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    tax_total = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)
    terms = db.Column(db.Text)
    status = db.Column(db.String(20), default='Draft')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('ProformaInvoiceItem', backref='proforma', lazy='dynamic', cascade='all, delete-orphan')
    proforma_customer = db.relationship('Customer', backref='proforma_invoices', foreign_keys=[customer_id])

    def __repr__(self):
        return f'<ProformaInvoice {self.proforma_no}>'


class ProformaInvoiceItem(db.Model):
    __tablename__ = 'proforma_invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    proforma_id = db.Column(db.Integer, db.ForeignKey('proforma_invoices.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product', backref='proforma_items')


class DeliveryChallan(db.Model):
    __tablename__ = 'delivery_challans'
    id = db.Column(db.Integer, primary_key=True)
    challan_no = db.Column(db.String(30), unique=True, nullable=False)
    challan_date = db.Column(db.Date, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    delivery_address = db.Column(db.Text)
    vehicle_no = db.Column(db.String(20))
    driver_name = db.Column(db.String(100))
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='Draft')  # Draft, Delivered, Converted
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('DeliveryChallanItem', backref='challan', lazy='dynamic', cascade='all, delete-orphan')
    challan_customer = db.relationship('Customer', backref='challans', foreign_keys=[customer_id])

    def __repr__(self):
        return f'<DeliveryChallan {self.challan_no}>'


class DeliveryChallanItem(db.Model):
    __tablename__ = 'delivery_challan_items'
    id = db.Column(db.Integer, primary_key=True)
    challan_id = db.Column(db.Integer, db.ForeignKey('delivery_challans.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    notes = db.Column(db.String(255))
    product = db.relationship('Product', backref='challan_items')
