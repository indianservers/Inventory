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


class Company(db.Model):
    __tablename__ = "companies"
    id = db.Column(db.Integer, primary_key=True)
    legal_name = db.Column(db.String(200), nullable=False, default="Vyapara ERP")
    trade_name = db.Column(db.String(200))
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
    currency = db.Column(db.String(10), default="INR")
    financial_year_start_month = db.Column(db.Integer, default=4)
    invoice_prefix = db.Column(db.String(10), default="INV")
    purchase_prefix = db.Column(db.String(10), default="PUR")
    quotation_prefix = db.Column(db.String(10), default="QUO")
    receipt_prefix = db.Column(db.String(10), default="REC")
    payment_prefix = db.Column(db.String(10), default="PAY")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def company_name(self):
        return self.trade_name or self.legal_name


class Branch(db.Model):
    __tablename__ = "branches"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.Text)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(150))
    tax_number = db.Column(db.String(50))
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Branch {self.code}>"


class Register(db.Model):
    __tablename__ = "registers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    receipt_printer = db.Column(db.String(150))
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    branch = db.relationship("Branch", backref="registers")
    warehouse = db.relationship("Warehouse", backref="registers")

    def __repr__(self):
        return f"<Register {self.code}>"


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
    module = db.Column(db.String(50))
    paper_size = db.Column(db.String(20), default="A4")
    show_header = db.Column(db.Boolean, default=True)
    show_footer = db.Column(db.Boolean, default=True)
    show_logo = db.Column(db.Boolean, default=True)
    column_config = db.Column(db.Text)
    terms_conditions = db.Column(db.Text)
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


class EmailTemplate(db.Model):
    __tablename__ = "email_templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    template_type = db.Column(db.String(50), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    placeholders = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CommunicationLog(db.Model):
    __tablename__ = "communication_logs"
    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.String(20), nullable=False)
    recipient = db.Column(db.String(180), nullable=False)
    subject = db.Column(db.String(255))
    body = db.Column(db.Text)
    provider = db.Column(db.String(80))
    status = db.Column(db.String(30), default="Pending")
    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.Integer)
    error_message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class IntegrationSetting(db.Model):
    __tablename__ = "integration_settings"
    id = db.Column(db.Integer, primary_key=True)
    provider_type = db.Column(db.String(50), nullable=False)
    provider_name = db.Column(db.String(100), nullable=False)
    config_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    test_mode = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaymentGateway(db.Model):
    __tablename__ = "payment_gateways"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(80), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    api_key_label = db.Column(db.String(120))
    config_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    test_mode = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PaymentLink(db.Model):
    __tablename__ = "payment_links"
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    gateway_id = db.Column(db.Integer, db.ForeignKey("payment_gateways.id"))
    link_url = db.Column(db.String(500))
    provider_reference = db.Column(db.String(120))
    amount = db.Column(db.Numeric(12, 2), default=0)
    currency = db.Column(db.String(10), default="INR")
    status = db.Column(db.String(30), default="Created")
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sale = db.relationship("Sale", backref="payment_links")
    gateway = db.relationship("PaymentGateway", backref="payment_links")


class EcommerceOrder(db.Model):
    __tablename__ = "ecommerce_orders"
    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(80), nullable=False)
    external_order_id = db.Column(db.String(120), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))
    customer_payload = db.Column(db.Text)
    stock_sync_status = db.Column(db.String(30), default="Pending")
    import_status = db.Column(db.String(30), default="Imported")
    invoice_id = db.Column(db.Integer, db.ForeignKey("sales.id"))
    order_date = db.Column(db.DateTime)
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer", backref="ecommerce_orders")
    invoice = db.relationship("Sale", backref="ecommerce_orders")


class EcommerceOrderItem(db.Model):
    __tablename__ = "ecommerce_order_items"
    id = db.Column(db.Integer, primary_key=True)
    ecommerce_order_id = db.Column(db.Integer, db.ForeignKey("ecommerce_orders.id"), nullable=False)
    external_product_id = db.Column(db.String(120))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    name = db.Column(db.String(180), nullable=False)
    sku = db.Column(db.String(80))
    quantity = db.Column(db.Numeric(12, 3), default=0)
    rate = db.Column(db.Numeric(12, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    line_total = db.Column(db.Numeric(12, 2), default=0)
    order = db.relationship("EcommerceOrder", backref=db.backref("items", cascade="all, delete-orphan"))
    product = db.relationship("Product")


class ShippingProvider(db.Model):
    __tablename__ = "shipping_providers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    provider_code = db.Column(db.String(50), nullable=False)
    config_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    test_mode = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Shipment(db.Model):
    __tablename__ = "shipments"
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("shipping_providers.id"))
    reference_type = db.Column(db.String(50), nullable=False)
    reference_id = db.Column(db.Integer, nullable=False)
    awb_no = db.Column(db.String(120))
    tracking_no = db.Column(db.String(120))
    status = db.Column(db.String(40), default="Pending")
    delivery_partner = db.Column(db.String(120))
    shipping_label = db.Column(db.Text)
    tracking_url = db.Column(db.String(500))
    delivery_updates = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    provider = db.relationship("ShippingProvider", backref="shipments")


class WebhookSubscription(db.Model):
    __tablename__ = "webhook_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    target_url = db.Column(db.String(500), nullable=False)
    events = db.Column(db.Text, nullable=False)
    secret = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WebhookLog(db.Model):
    __tablename__ = "webhook_logs"
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("webhook_subscriptions.id"))
    event = db.Column(db.String(80), nullable=False)
    payload = db.Column(db.Text)
    response_status = db.Column(db.Integer)
    response_body = db.Column(db.Text)
    status = db.Column(db.String(30), default="Pending")
    error_message = db.Column(db.Text)
    delivered_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subscription = db.relationship("WebhookSubscription", backref="logs")


class IncomingWebhookLog(db.Model):
    __tablename__ = "incoming_webhook_logs"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(80), nullable=False)
    event_type = db.Column(db.String(80))
    payload = db.Column(db.Text)
    headers = db.Column(db.Text)
    status = db.Column(db.String(30), default="Received")
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CustomField(db.Model):
    __tablename__ = "custom_fields"
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False)
    field_key = db.Column(db.String(80), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    field_type = db.Column(db.String(30), nullable=False, default="Text")
    options = db.Column(db.Text)
    is_required = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CustomFieldValue(db.Model):
    __tablename__ = "custom_field_values"
    id = db.Column(db.Integer, primary_key=True)
    field_id = db.Column(db.Integer, db.ForeignKey("custom_fields.id"), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    field = db.relationship("CustomField", backref="values")


class CustomView(db.Model):
    __tablename__ = "custom_views"
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    filters_json = db.Column(db.Text)
    columns_json = db.Column(db.Text)
    sort_json = db.Column(db.Text)
    is_default = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CustomModule(db.Model):
    __tablename__ = "custom_modules"
    id = db.Column(db.Integer, primary_key=True)
    module_key = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    plural_name = db.Column(db.String(140))
    description = db.Column(db.Text)
    icon = db.Column(db.String(50), default="bi-grid")
    show_in_sidebar = db.Column(db.Boolean, default=True)
    allow_import = db.Column(db.Boolean, default=True)
    allow_export = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    fields = db.relationship("CustomModuleField", backref="module", lazy="dynamic", cascade="all, delete-orphan")
    records = db.relationship("CustomModuleRecord", backref="module", lazy="dynamic", cascade="all, delete-orphan")


class CustomModuleField(db.Model):
    __tablename__ = "custom_module_fields"
    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("custom_modules.id", ondelete="CASCADE"), nullable=False)
    field_key = db.Column(db.String(80), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    field_type = db.Column(db.String(30), default="Text")
    options = db.Column(db.Text)
    is_required = db.Column(db.Boolean, default=False)
    show_in_list = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("module_id", "field_key", name="uq_custom_module_field"),)


class CustomModuleRecord(db.Model):
    __tablename__ = "custom_module_records"
    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("custom_modules.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    data_json = db.Column(db.Text)
    status = db.Column(db.String(30), default="Active")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkflowRule(db.Model):
    __tablename__ = "workflow_rules"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    trigger_event = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkflowCondition(db.Model):
    __tablename__ = "workflow_conditions"
    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey("workflow_rules.id"), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)
    operator = db.Column(db.String(30), nullable=False, default="equals")
    value = db.Column(db.String(255))
    workflow = db.relationship("WorkflowRule", backref=db.backref("conditions", cascade="all, delete-orphan"))


class WorkflowAction(db.Model):
    __tablename__ = "workflow_actions"
    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey("workflow_rules.id"), nullable=False)
    action_type = db.Column(db.String(80), nullable=False)
    config_json = db.Column(db.Text)
    workflow = db.relationship("WorkflowRule", backref=db.backref("actions", cascade="all, delete-orphan"))


class ScheduledJob(db.Model):
    __tablename__ = "scheduled_jobs"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    job_type = db.Column(db.String(80), nullable=False)
    frequency = db.Column(db.String(20), default="Daily")
    time_of_day = db.Column(db.String(5), default="09:00")
    config_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    last_run_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ScheduledJobLog(db.Model):
    __tablename__ = "scheduled_job_logs"
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("scheduled_jobs.id"))
    status = db.Column(db.String(30), default="Pending")
    message = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    job = db.relationship("ScheduledJob", backref="logs")


class LoyaltySetting(db.Model):
    __tablename__ = "loyalty_settings"
    id = db.Column(db.Integer, primary_key=True)
    is_enabled = db.Column(db.Boolean, default=False)
    earn_points_per_amount = db.Column(db.Numeric(12, 2), default=100)
    points_earned = db.Column(db.Numeric(12, 2), default=1)
    redemption_value_per_point = db.Column(db.Numeric(12, 2), default=1)
    points_expiry_days = db.Column(db.Integer, default=365)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomerLoyaltyAccount(db.Model):
    __tablename__ = "customer_loyalty_accounts"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    points_balance = db.Column(db.Numeric(12, 2), default=0)
    lifetime_points = db.Column(db.Numeric(12, 2), default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    customer = db.relationship("Customer", backref="loyalty_account")


class LoyaltyTransaction(db.Model):
    __tablename__ = "loyalty_transactions"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"))
    transaction_type = db.Column(db.String(20), nullable=False)
    points = db.Column(db.Numeric(12, 2), default=0)
    expiry_date = db.Column(db.Date)
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer", backref="loyalty_transactions")
    sale = db.relationship("Sale", backref="loyalty_transactions")


class Coupon(db.Model):
    __tablename__ = "coupons"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    description = db.Column(db.String(255))
    discount_type = db.Column(db.String(20), default="Percentage")
    discount_value = db.Column(db.Numeric(12, 2), default=0)
    valid_from = db.Column(db.Date)
    valid_to = db.Column(db.Date)
    minimum_invoice_amount = db.Column(db.Numeric(12, 2), default=0)
    customer_group = db.Column(db.String(80))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    max_usage = db.Column(db.Integer)
    per_customer_usage_limit = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship("Product")
    category = db.relationship("Category")


class CouponRedemption(db.Model):
    __tablename__ = "coupon_redemptions"
    id = db.Column(db.Integer, primary_key=True)
    coupon_id = db.Column(db.Integer, db.ForeignKey("coupons.id"), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))
    discount_amount = db.Column(db.Numeric(12, 2), default=0)
    redeemed_at = db.Column(db.DateTime, default=datetime.utcnow)
    coupon = db.relationship("Coupon", backref="redemptions")
    sale = db.relationship("Sale", backref="coupon_redemptions")
    customer = db.relationship("Customer", backref="coupon_redemptions")


class Promotion(db.Model):
    __tablename__ = "promotions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    valid_from = db.Column(db.Date)
    valid_to = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PromotionRule(db.Model):
    __tablename__ = "promotion_rules"
    id = db.Column(db.Integer, primary_key=True)
    promotion_id = db.Column(db.Integer, db.ForeignKey("promotions.id"), nullable=False)
    rule_type = db.Column(db.String(40), nullable=False)
    config_json = db.Column(db.Text)
    promotion = db.relationship("Promotion", backref=db.backref("rules", cascade="all, delete-orphan"))
