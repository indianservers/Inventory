from datetime import date, datetime
from app.extensions import db


class CompanySetting(db.Model):
    __tablename__ = "company_settings"
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(200), nullable=False, default="Vyapara ERP")
    business_type = db.Column(db.String(100), default="Trading")
    logo = db.Column(db.String(255))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    country = db.Column(db.String(100), default="India")
    postal_code = db.Column(db.String(20))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(150))
    website = db.Column(db.String(150))
    tax_number = db.Column(db.String(50))
    pan_number = db.Column(db.String(20))
    currency = db.Column(db.String(10), default="INR")
    financial_year_start = db.Column(db.Date, default=lambda: date(date.today().year, 4, 1))
    invoice_prefix = db.Column(db.String(10), default="INV")
    purchase_prefix = db.Column(db.String(10), default="PUR")
    quotation_prefix = db.Column(db.String(10), default="QUO")
    receipt_prefix = db.Column(db.String(10), default="REC")
    payment_prefix = db.Column(db.String(10), default="PAY")
    sales_return_prefix = db.Column(db.String(10), default="SR")
    purchase_return_prefix = db.Column(db.String(10), default="PR")
    date_format = db.Column(db.String(20), default="%d-%m-%Y")
    decimal_places = db.Column(db.Integer, default=2)
    tax_mode = db.Column(db.String(20), default="GST")
    enable_negative_stock = db.Column(db.Boolean, default=False)
    enable_batch_tracking = db.Column(db.Boolean, default=False)
    enable_expiry_tracking = db.Column(db.Boolean, default=False)
    enable_barcode = db.Column(db.Boolean, default=True)
    default_invoice_terms = db.Column(db.Text)
    stock_valuation_method = db.Column(db.String(30), default="Weighted Average")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppSetting(db.Model):
    __tablename__ = "app_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PrintTemplate(db.Model):
    __tablename__ = "print_templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    template_type = db.Column(db.String(50), nullable=False)
    html = db.Column(db.Text)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Currency(db.Model):
    __tablename__ = "currencies"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    symbol = db.Column(db.String(10), default="")
    exchange_rate = db.Column(db.Numeric(12, 6), default=1)
    is_base = db.Column(db.Boolean, default=False)
    auto_update = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ExchangeRateLog(db.Model):
    __tablename__ = "exchange_rate_logs"
    id = db.Column(db.Integer, primary_key=True)
    currency_id = db.Column(db.Integer, db.ForeignKey("currencies.id"), nullable=False)
    rate = db.Column(db.Numeric(12, 6), nullable=False)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)
    currency = db.relationship("Currency", backref="rate_logs")


class ScheduledReport(db.Model):
    __tablename__ = "scheduled_reports"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    report_type = db.Column(db.String(30), nullable=False)
    frequency = db.Column(db.String(20), default="Daily")
    day_of_week = db.Column(db.Integer)
    day_of_month = db.Column(db.Integer)
    time_of_day = db.Column(db.String(5), default="09:00")
    recipient_emails = db.Column(db.Text)
    format = db.Column(db.String(10), default="Excel")
    is_active = db.Column(db.Boolean, default=True)
    last_sent_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ApiToken(db.Model):
    __tablename__ = "api_tokens"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    token_hash = db.Column(db.String(255), nullable=False)
    prefix = db.Column(db.String(16), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    last_used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="api_tokens")
