from datetime import datetime
from app.extensions import db


class Sale(db.Model):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(30), unique=True, nullable=False)
    invoice_date = db.Column(db.Date, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    currency_id = db.Column(db.Integer, db.ForeignKey('currencies.id'), nullable=True)
    exchange_rate_snapshot = db.Column(db.Numeric(12, 6), default=1)
    original_currency_total = db.Column(db.Numeric(12, 2), default=0)
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
    irn = db.Column(db.String(64))
    irn_ack_no = db.Column(db.String(64))
    irn_ack_dt = db.Column(db.DateTime)
    qr_code_data = db.Column(db.Text)
    e_invoice_status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship('SaleItem', backref='sale', lazy='dynamic', cascade='all, delete-orphan')
    warehouse = db.relationship('Warehouse', backref='sales')
    currency = db.relationship('Currency', backref='sales')

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


class POSSession(db.Model):
    __tablename__ = 'pos_sessions'
    id = db.Column(db.Integer, primary_key=True)
    session_no = db.Column(db.String(30), unique=True, nullable=False)
    opened_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime)
    opening_cash = db.Column(db.Numeric(12, 2), default=0)
    closing_cash = db.Column(db.Numeric(12, 2), default=0)
    total_sales = db.Column(db.Numeric(12, 2), default=0)
    total_cash = db.Column(db.Numeric(12, 2), default=0)
    total_card = db.Column(db.Numeric(12, 2), default=0)
    total_upi = db.Column(db.Numeric(12, 2), default=0)
    status = db.Column(db.String(20), default='Open')
    user = db.relationship('User', backref='pos_sessions', foreign_keys=[opened_by])


class RecurringInvoice(db.Model):
    __tablename__ = 'recurring_invoices'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    frequency = db.Column(db.String(20), default='Monthly')
    interval_value = db.Column(db.Integer, default=1)
    next_run_date = db.Column(db.Date, nullable=False)
    last_run_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    auto_send = db.Column(db.Boolean, default=False)
    auto_collect = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='Active')
    notes = db.Column(db.Text)
    terms = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship('Customer', backref='recurring_invoices')
    warehouse = db.relationship('Warehouse', backref='recurring_invoices')
    items = db.relationship('RecurringInvoiceItem', backref='recurring_invoice', lazy='dynamic', cascade='all, delete-orphan')


class RecurringInvoiceItem(db.Model):
    __tablename__ = 'recurring_invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    recurring_id = db.Column(db.Integer, db.ForeignKey('recurring_invoices.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    discount = db.Column(db.Numeric(5, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    product = db.relationship('Product', backref='recurring_invoice_items')


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


class EWayBill(db.Model):
    __tablename__ = 'eway_bills'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id', ondelete='CASCADE'), nullable=False)
    ewb_no = db.Column(db.String(30), unique=True, nullable=False)
    ewb_date = db.Column(db.DateTime, default=datetime.utcnow)
    valid_upto = db.Column(db.DateTime)
    vehicle_no = db.Column(db.String(30))
    transporter_name = db.Column(db.String(150))
    transporter_id = db.Column(db.String(30))
    supply_type = db.Column(db.String(20), default='Outward')
    sub_type = db.Column(db.String(20), default='Supply')
    distance_km = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='Generated')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sale = db.relationship('Sale', backref=db.backref('eway_bills', lazy='dynamic', cascade='all, delete-orphan'))


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


class CreditNote(db.Model):
    __tablename__ = 'credit_notes'
    id = db.Column(db.Integer, primary_key=True)
    cn_no = db.Column(db.String(30), unique=True, nullable=False)
    cn_date = db.Column(db.Date, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True)
    reason = db.Column(db.Text)
    adjustment_type = db.Column(db.String(20), default='Other')
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    tax_total = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    status = db.Column(db.String(20), default='Draft')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship('Customer', backref='credit_notes')
    sale = db.relationship('Sale', backref='credit_notes')
    items = db.relationship('CreditNoteItem', backref='credit_note', lazy='dynamic', cascade='all, delete-orphan')


class CreditNoteItem(db.Model):
    __tablename__ = 'credit_note_items'
    id = db.Column(db.Integer, primary_key=True)
    cn_id = db.Column(db.Integer, db.ForeignKey('credit_notes.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product', backref='credit_note_items')


class DebitNote(db.Model):
    __tablename__ = 'debit_notes'
    id = db.Column(db.Integer, primary_key=True)
    dn_no = db.Column(db.String(30), unique=True, nullable=False)
    dn_date = db.Column(db.Date, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), nullable=True)
    reason = db.Column(db.Text)
    adjustment_type = db.Column(db.String(20), default='Other')
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    tax_total = db.Column(db.Numeric(12, 2), default=0)
    grand_total = db.Column(db.Numeric(12, 2), default=0)
    status = db.Column(db.String(20), default='Draft')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    supplier = db.relationship('Supplier', backref='debit_notes')
    purchase = db.relationship('Purchase', backref='debit_notes')
    items = db.relationship('DebitNoteItem', backref='debit_note', lazy='dynamic', cascade='all, delete-orphan')


class DebitNoteItem(db.Model):
    __tablename__ = 'debit_note_items'
    id = db.Column(db.Integer, primary_key=True)
    dn_id = db.Column(db.Integer, db.ForeignKey('debit_notes.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product', backref='debit_note_items')
