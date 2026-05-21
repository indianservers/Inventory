"""integration automation foundation

Revision ID: ec2eab559ca6
Revises: 842f55653a89
Create Date: 2026-05-21 18:17:34.713466

"""
from alembic import op
import sqlalchemy as sa


revision = "ec2eab559ca6"
down_revision = "842f55653a89"
branch_labels = None
depends_on = None


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table):
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)} if _has_table(table) else set()


def _add_column(table, column):
    if _has_table(table) and column.name not in _columns(table):
        op.add_column(table, column)


def upgrade():
    _add_column("print_templates", sa.Column("module", sa.String(50)))
    _add_column("print_templates", sa.Column("paper_size", sa.String(20), server_default="A4"))
    _add_column("print_templates", sa.Column("show_header", sa.Boolean(), server_default=sa.true()))
    _add_column("print_templates", sa.Column("show_footer", sa.Boolean(), server_default=sa.true()))
    _add_column("print_templates", sa.Column("show_logo", sa.Boolean(), server_default=sa.true()))
    _add_column("print_templates", sa.Column("column_config", sa.Text()))
    _add_column("print_templates", sa.Column("terms_conditions", sa.Text()))

    if not _has_table("email_templates"):
        op.create_table(
            "email_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("template_type", sa.String(50), nullable=False),
            sa.Column("subject", sa.String(255), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("placeholders", sa.Text()),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )
    if not _has_table("communication_logs"):
        op.create_table(
            "communication_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("recipient", sa.String(180), nullable=False),
            sa.Column("subject", sa.String(255)),
            sa.Column("body", sa.Text()),
            sa.Column("provider", sa.String(80)),
            sa.Column("status", sa.String(30), server_default="Pending"),
            sa.Column("reference_type", sa.String(50)),
            sa.Column("reference_id", sa.Integer()),
            sa.Column("error_message", sa.Text()),
            sa.Column("sent_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
        )
    if not _has_table("integration_settings"):
        op.create_table(
            "integration_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider_type", sa.String(50), nullable=False),
            sa.Column("provider_name", sa.String(100), nullable=False),
            sa.Column("config_json", sa.Text()),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("test_mode", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )
    if not _has_table("payment_gateways"):
        op.create_table(
            "payment_gateways",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider", sa.String(80), nullable=False),
            sa.Column("display_name", sa.String(120), nullable=False),
            sa.Column("api_key_label", sa.String(120)),
            sa.Column("config_json", sa.Text()),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("test_mode", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
    if not _has_table("payment_links"):
        op.create_table(
            "payment_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sale_id", sa.Integer(), nullable=False),
            sa.Column("gateway_id", sa.Integer()),
            sa.Column("link_url", sa.String(500)),
            sa.Column("provider_reference", sa.String(120)),
            sa.Column("amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("currency", sa.String(10), server_default="INR"),
            sa.Column("status", sa.String(30), server_default="Created"),
            sa.Column("expires_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_payment_links_sale_id"),
            sa.ForeignKeyConstraint(["gateway_id"], ["payment_gateways.id"], name="fk_payment_links_gateway_id"),
        )
    if not _has_table("ecommerce_orders"):
        op.create_table(
            "ecommerce_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("platform", sa.String(80), nullable=False),
            sa.Column("external_order_id", sa.String(120), nullable=False),
            sa.Column("customer_id", sa.Integer()),
            sa.Column("customer_payload", sa.Text()),
            sa.Column("stock_sync_status", sa.String(30), server_default="Pending"),
            sa.Column("import_status", sa.String(30), server_default="Imported"),
            sa.Column("invoice_id", sa.Integer()),
            sa.Column("order_date", sa.DateTime()),
            sa.Column("total_amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_ecommerce_orders_customer_id"),
            sa.ForeignKeyConstraint(["invoice_id"], ["sales.id"], name="fk_ecommerce_orders_invoice_id"),
        )
    if not _has_table("ecommerce_order_items"):
        op.create_table(
            "ecommerce_order_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ecommerce_order_id", sa.Integer(), nullable=False),
            sa.Column("external_product_id", sa.String(120)),
            sa.Column("product_id", sa.Integer()),
            sa.Column("name", sa.String(180), nullable=False),
            sa.Column("sku", sa.String(80)),
            sa.Column("quantity", sa.Numeric(12, 3), server_default="0"),
            sa.Column("rate", sa.Numeric(12, 2), server_default="0"),
            sa.Column("tax_rate", sa.Numeric(5, 2), server_default="0"),
            sa.Column("line_total", sa.Numeric(12, 2), server_default="0"),
            sa.ForeignKeyConstraint(["ecommerce_order_id"], ["ecommerce_orders.id"], ondelete="CASCADE", name="fk_ecommerce_order_items_order_id"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_ecommerce_order_items_product_id"),
        )
    if not _has_table("shipping_providers"):
        op.create_table(
            "shipping_providers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("provider_code", sa.String(50), nullable=False),
            sa.Column("config_json", sa.Text()),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("test_mode", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
    if not _has_table("shipments"):
        op.create_table(
            "shipments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider_id", sa.Integer()),
            sa.Column("reference_type", sa.String(50), nullable=False),
            sa.Column("reference_id", sa.Integer(), nullable=False),
            sa.Column("awb_no", sa.String(120)),
            sa.Column("tracking_no", sa.String(120)),
            sa.Column("status", sa.String(40), server_default="Pending"),
            sa.Column("delivery_partner", sa.String(120)),
            sa.Column("shipping_label", sa.Text()),
            sa.Column("tracking_url", sa.String(500)),
            sa.Column("delivery_updates", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["provider_id"], ["shipping_providers.id"], name="fk_shipments_provider_id"),
        )
    if not _has_table("webhook_subscriptions"):
        op.create_table(
            "webhook_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("target_url", sa.String(500), nullable=False),
            sa.Column("events", sa.Text(), nullable=False),
            sa.Column("secret", sa.String(120)),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
    if not _has_table("webhook_logs"):
        op.create_table(
            "webhook_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("subscription_id", sa.Integer()),
            sa.Column("event", sa.String(80), nullable=False),
            sa.Column("payload", sa.Text()),
            sa.Column("response_status", sa.Integer()),
            sa.Column("response_body", sa.Text()),
            sa.Column("status", sa.String(30), server_default="Pending"),
            sa.Column("error_message", sa.Text()),
            sa.Column("delivered_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["subscription_id"], ["webhook_subscriptions.id"], name="fk_webhook_logs_subscription_id"),
        )
    if not _has_table("incoming_webhook_logs"):
        op.create_table(
            "incoming_webhook_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider", sa.String(80), nullable=False),
            sa.Column("event_type", sa.String(80)),
            sa.Column("payload", sa.Text()),
            sa.Column("headers", sa.Text()),
            sa.Column("status", sa.String(30), server_default="Received"),
            sa.Column("error_message", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
        )
    if not _has_table("custom_fields"):
        op.create_table(
            "custom_fields",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("entity_type", sa.String(50), nullable=False),
            sa.Column("field_key", sa.String(80), nullable=False),
            sa.Column("label", sa.String(120), nullable=False),
            sa.Column("field_type", sa.String(30), nullable=False),
            sa.Column("options", sa.Text()),
            sa.Column("is_required", sa.Boolean(), server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
    if not _has_table("custom_field_values"):
        op.create_table(
            "custom_field_values",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("field_id", sa.Integer(), nullable=False),
            sa.Column("entity_type", sa.String(50), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("value", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["field_id"], ["custom_fields.id"], name="fk_custom_field_values_field_id"),
        )
    if not _has_table("custom_views"):
        op.create_table(
            "custom_views",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("entity_type", sa.String(50), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("filters_json", sa.Text()),
            sa.Column("columns_json", sa.Text()),
            sa.Column("sort_json", sa.Text()),
            sa.Column("is_default", sa.Boolean(), server_default=sa.false()),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_custom_views_created_by"),
        )
    if not _has_table("workflow_rules"):
        op.create_table(
            "workflow_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("trigger_event", sa.String(80), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
    if not _has_table("workflow_conditions"):
        op.create_table(
            "workflow_conditions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workflow_id", sa.Integer(), nullable=False),
            sa.Column("field_name", sa.String(100), nullable=False),
            sa.Column("operator", sa.String(30), nullable=False),
            sa.Column("value", sa.String(255)),
            sa.ForeignKeyConstraint(["workflow_id"], ["workflow_rules.id"], ondelete="CASCADE", name="fk_workflow_conditions_workflow_id"),
        )
    if not _has_table("workflow_actions"):
        op.create_table(
            "workflow_actions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workflow_id", sa.Integer(), nullable=False),
            sa.Column("action_type", sa.String(80), nullable=False),
            sa.Column("config_json", sa.Text()),
            sa.ForeignKeyConstraint(["workflow_id"], ["workflow_rules.id"], ondelete="CASCADE", name="fk_workflow_actions_workflow_id"),
        )
    if not _has_table("scheduled_jobs"):
        op.create_table(
            "scheduled_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("job_type", sa.String(80), nullable=False),
            sa.Column("frequency", sa.String(20), server_default="Daily"),
            sa.Column("time_of_day", sa.String(5), server_default="09:00"),
            sa.Column("config_json", sa.Text()),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("last_run_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
        )
    if not _has_table("scheduled_job_logs"):
        op.create_table(
            "scheduled_job_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("job_id", sa.Integer()),
            sa.Column("status", sa.String(30), server_default="Pending"),
            sa.Column("message", sa.Text()),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("finished_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["job_id"], ["scheduled_jobs.id"], name="fk_scheduled_job_logs_job_id"),
        )


def downgrade():
    for table in [
        "scheduled_job_logs", "scheduled_jobs", "workflow_actions", "workflow_conditions",
        "workflow_rules", "custom_views", "custom_field_values", "custom_fields",
        "incoming_webhook_logs", "webhook_logs", "webhook_subscriptions", "shipments",
        "shipping_providers", "ecommerce_order_items", "ecommerce_orders", "payment_links",
        "payment_gateways", "integration_settings", "communication_logs", "email_templates",
    ]:
        if _has_table(table):
            op.drop_table(table)
    for column in ["terms_conditions", "column_config", "show_logo", "show_footer", "show_header", "paper_size", "module"]:
        if column in _columns("print_templates"):
            op.drop_column("print_templates", column)
