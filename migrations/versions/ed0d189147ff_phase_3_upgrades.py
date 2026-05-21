"""phase 3 upgrades

Revision ID: ed0d189147ff
Revises: 747f6af9bfa9
Create Date: 2026-05-21 16:31:10.223694

"""
from alembic import op
import sqlalchemy as sa


revision = "ed0d189147ff"
down_revision = "747f6af9bfa9"
branch_labels = None
depends_on = None


def tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def cols(table):
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)} if table in inspector.get_table_names() else set()


def add_col(table, column):
    if column.name not in cols(table):
        op.add_column(table, column)


def upgrade():
    existing = tables()
    if "currencies" not in existing:
        op.create_table("currencies", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("code", sa.String(10), nullable=False, unique=True), sa.Column("name", sa.String(80), nullable=False), sa.Column("symbol", sa.String(10)), sa.Column("exchange_rate", sa.Numeric(12, 6)), sa.Column("is_base", sa.Boolean()), sa.Column("auto_update", sa.Boolean()), sa.Column("last_updated", sa.DateTime()), sa.Column("created_at", sa.DateTime()))
    if "exchange_rate_logs" not in existing:
        op.create_table("exchange_rate_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("currency_id", sa.Integer(), nullable=False), sa.Column("rate", sa.Numeric(12, 6), nullable=False), sa.Column("fetched_at", sa.DateTime()), sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"]))
    if "scheduled_reports" not in existing:
        op.create_table("scheduled_reports", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("report_type", sa.String(30), nullable=False), sa.Column("frequency", sa.String(20)), sa.Column("day_of_week", sa.Integer()), sa.Column("day_of_month", sa.Integer()), sa.Column("time_of_day", sa.String(5)), sa.Column("recipient_emails", sa.Text()), sa.Column("format", sa.String(10)), sa.Column("is_active", sa.Boolean()), sa.Column("last_sent_at", sa.DateTime()), sa.Column("created_by", sa.Integer()), sa.Column("created_at", sa.DateTime()), sa.ForeignKeyConstraint(["created_by"], ["users.id"]))

    existing = tables()
    if "recurring_invoices" not in existing:
        op.create_table("recurring_invoices", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(150), nullable=False), sa.Column("customer_id", sa.Integer(), nullable=False), sa.Column("warehouse_id", sa.Integer(), nullable=False), sa.Column("frequency", sa.String(20)), sa.Column("interval_value", sa.Integer()), sa.Column("next_run_date", sa.Date(), nullable=False), sa.Column("last_run_date", sa.Date()), sa.Column("end_date", sa.Date()), sa.Column("auto_send", sa.Boolean()), sa.Column("auto_collect", sa.Boolean()), sa.Column("status", sa.String(20)), sa.Column("notes", sa.Text()), sa.Column("terms", sa.Text()), sa.Column("created_by", sa.Integer()), sa.Column("created_at", sa.DateTime()), sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]), sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]), sa.ForeignKeyConstraint(["created_by"], ["users.id"]))
    if "recurring_invoice_items" not in existing:
        op.create_table("recurring_invoice_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("recurring_id", sa.Integer(), nullable=False), sa.Column("product_id", sa.Integer(), nullable=False), sa.Column("quantity", sa.Numeric(12, 3), nullable=False), sa.Column("rate", sa.Numeric(12, 4), nullable=False), sa.Column("discount", sa.Numeric(5, 2)), sa.Column("tax_rate", sa.Numeric(5, 2)), sa.ForeignKeyConstraint(["recurring_id"], ["recurring_invoices.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["product_id"], ["products.id"]))

    existing = tables()
    if "bill_of_materials" not in existing:
        op.create_table("bill_of_materials", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), nullable=False), sa.Column("name", sa.String(150), nullable=False), sa.Column("yield_qty", sa.Numeric(12, 3)), sa.Column("version", sa.String(20)), sa.Column("is_active", sa.Boolean()), sa.Column("notes", sa.Text()), sa.Column("created_at", sa.DateTime()), sa.ForeignKeyConstraint(["product_id"], ["products.id"]))
    if "bom_items" not in existing:
        op.create_table("bom_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("bom_id", sa.Integer(), nullable=False), sa.Column("component_id", sa.Integer(), nullable=False), sa.Column("quantity", sa.Numeric(12, 3), nullable=False), sa.Column("unit_id", sa.Integer()), sa.Column("waste_pct", sa.Numeric(5, 2)), sa.ForeignKeyConstraint(["bom_id"], ["bill_of_materials.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["component_id"], ["products.id"]), sa.ForeignKeyConstraint(["unit_id"], ["units.id"]))
    if "manufacturing_orders" not in existing:
        op.create_table("manufacturing_orders", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("mo_no", sa.String(30), nullable=False, unique=True), sa.Column("bom_id", sa.Integer(), nullable=False), sa.Column("warehouse_id", sa.Integer(), nullable=False), sa.Column("planned_qty", sa.Numeric(12, 3), nullable=False), sa.Column("produced_qty", sa.Numeric(12, 3)), sa.Column("planned_date", sa.Date()), sa.Column("completed_date", sa.Date()), sa.Column("status", sa.String(20)), sa.Column("notes", sa.Text()), sa.Column("created_by", sa.Integer()), sa.Column("created_at", sa.DateTime()), sa.ForeignKeyConstraint(["bom_id"], ["bill_of_materials.id"]), sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]), sa.ForeignKeyConstraint(["created_by"], ["users.id"]))

    existing = tables()
    if "tds_sections" not in existing:
        op.create_table("tds_sections", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("section_code", sa.String(20), nullable=False, unique=True), sa.Column("description", sa.String(255)), sa.Column("default_rate", sa.Numeric(5, 2)), sa.Column("threshold_amount", sa.Numeric(12, 2)), sa.Column("is_active", sa.Boolean()))
    if "tds_entries" not in existing:
        op.create_table("tds_entries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("entry_date", sa.Date(), nullable=False), sa.Column("party_type", sa.String(20), nullable=False), sa.Column("party_id", sa.Integer(), nullable=False), sa.Column("reference_type", sa.String(30)), sa.Column("reference_id", sa.Integer()), sa.Column("reference_no", sa.String(50)), sa.Column("section_id", sa.Integer(), nullable=False), sa.Column("base_amount", sa.Numeric(12, 2)), sa.Column("tds_rate", sa.Numeric(5, 2)), sa.Column("tds_amount", sa.Numeric(12, 2)), sa.Column("status", sa.String(20)), sa.Column("created_by", sa.Integer()), sa.Column("created_at", sa.DateTime()), sa.ForeignKeyConstraint(["section_id"], ["tds_sections.id"]), sa.ForeignKeyConstraint(["created_by"], ["users.id"]))
    if "tcs_entries" not in existing:
        op.create_table("tcs_entries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("entry_date", sa.Date(), nullable=False), sa.Column("party_type", sa.String(20), nullable=False), sa.Column("party_id", sa.Integer(), nullable=False), sa.Column("reference_type", sa.String(30)), sa.Column("reference_id", sa.Integer()), sa.Column("reference_no", sa.String(50)), sa.Column("section_id", sa.Integer(), nullable=False), sa.Column("base_amount", sa.Numeric(12, 2)), sa.Column("tds_rate", sa.Numeric(5, 2)), sa.Column("tds_amount", sa.Numeric(12, 2)), sa.Column("status", sa.String(20)), sa.Column("created_by", sa.Integer()), sa.Column("created_at", sa.DateTime()), sa.ForeignKeyConstraint(["section_id"], ["tds_sections.id"]), sa.ForeignKeyConstraint(["created_by"], ["users.id"]))

    add_col("sales", sa.Column("currency_id", sa.Integer(), nullable=True))
    add_col("sales", sa.Column("exchange_rate_snapshot", sa.Numeric(12, 6), nullable=True))
    add_col("sales", sa.Column("original_currency_total", sa.Numeric(12, 2), nullable=True))
    add_col("purchases", sa.Column("currency_id", sa.Integer(), nullable=True))
    add_col("purchases", sa.Column("exchange_rate_snapshot", sa.Numeric(12, 6), nullable=True))
    add_col("purchases", sa.Column("original_currency_total", sa.Numeric(12, 2), nullable=True))
    add_col("suppliers", sa.Column("tds_applicable", sa.Boolean(), nullable=True))
    add_col("suppliers", sa.Column("tds_section_id", sa.Integer(), nullable=True))


def downgrade():
    for table in ["tcs_entries", "tds_entries", "tds_sections", "manufacturing_orders", "bom_items", "bill_of_materials", "recurring_invoice_items", "recurring_invoices", "scheduled_reports", "exchange_rate_logs", "currencies"]:
        if table in tables():
            op.drop_table(table)
    for table, column in [
        ("suppliers", "tds_section_id"), ("suppliers", "tds_applicable"),
        ("purchases", "original_currency_total"), ("purchases", "exchange_rate_snapshot"), ("purchases", "currency_id"),
        ("sales", "original_currency_total"), ("sales", "exchange_rate_snapshot"), ("sales", "currency_id"),
    ]:
        if column in cols(table):
            op.drop_column(table, column)
