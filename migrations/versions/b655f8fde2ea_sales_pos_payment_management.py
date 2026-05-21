"""sales pos payment management

Revision ID: b655f8fde2ea
Revises: 639d431807a5
Create Date: 2026-05-21 17:36:21.917146

"""
from alembic import op
import sqlalchemy as sa


revision = "b655f8fde2ea"
down_revision = "639d431807a5"
branch_labels = None
depends_on = None


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table):
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)} if _has_table(table) else set()


def _has_fk(table, constrained_columns, referred_table):
    if not _has_table(table):
        return False
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk.get("constrained_columns") == constrained_columns and fk.get("referred_table") == referred_table:
            return True
    return False


def _add_column(table, column):
    if column.name not in _columns(table):
        op.add_column(table, column)


def _fk(name, table, ref_table, cols, ref_cols):
    if _has_table(table) and not _has_fk(table, cols, ref_table):
        op.create_foreign_key(name, table, ref_table, cols, ref_cols)


def upgrade():
    _add_column("customers", sa.Column("customer_type", sa.String(20), server_default="Retail"))
    _add_column("sales", sa.Column("invoice_type", sa.String(30), server_default="Tax Invoice"))
    _add_column("sales_returns", sa.Column("restock", sa.Boolean(), server_default=sa.true()))
    _add_column("sales_returns", sa.Column("status", sa.String(20), server_default="Approved"))
    _add_column("credit_notes", sa.Column("applied_amount", sa.Numeric(12, 2), server_default="0"))
    _add_column("credit_notes", sa.Column("refunded_amount", sa.Numeric(12, 2), server_default="0"))
    for name in ["total_wallet", "total_credit", "total_refunds", "cash_withdrawals", "expected_closing_cash", "cash_difference"]:
        _add_column("pos_sessions", sa.Column(name, sa.Numeric(12, 2), server_default="0"))
    _add_column("payments_received", sa.Column("unallocated_amount", sa.Numeric(12, 2), server_default="0"))
    _add_column("payments_received", sa.Column("status", sa.String(20), server_default="Posted"))
    _add_column("payments_received", sa.Column("reversed_at", sa.DateTime()))
    _add_column("payments_received", sa.Column("reversal_reason", sa.Text()))

    if not _has_table("held_bills"):
        op.create_table(
            "held_bills",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("hold_no", sa.String(30), nullable=False),
            sa.Column("session_id", sa.Integer()),
            sa.Column("customer_id", sa.Integer()),
            sa.Column("warehouse_id", sa.Integer()),
            sa.Column("cart_json", sa.Text(), nullable=False),
            sa.Column("notes", sa.String(255)),
            sa.Column("status", sa.String(20), server_default="Held"),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["session_id"], ["pos_sessions.id"], name="fk_held_bills_session_id"),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_held_bills_customer_id"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name="fk_held_bills_warehouse_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_held_bills_created_by"),
            sa.UniqueConstraint("hold_no", name="uq_held_bills_hold_no"),
        )

    if not _has_table("sales_orders"):
        op.create_table(
            "sales_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_no", sa.String(30), nullable=False),
            sa.Column("order_date", sa.Date(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("expected_date", sa.Date()),
            sa.Column("status", sa.String(20), server_default="Draft"),
            sa.Column("subtotal", sa.Numeric(12, 2), server_default="0"),
            sa.Column("discount_total", sa.Numeric(12, 2), server_default="0"),
            sa.Column("tax_total", sa.Numeric(12, 2), server_default="0"),
            sa.Column("grand_total", sa.Numeric(12, 2), server_default="0"),
            sa.Column("notes", sa.Text()),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_sales_orders_customer_id"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name="fk_sales_orders_warehouse_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_sales_orders_created_by"),
            sa.UniqueConstraint("order_no", name="uq_sales_orders_order_no"),
        )

    if not _has_table("sales_order_items"):
        op.create_table(
            "sales_order_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("rate", sa.Numeric(12, 4), nullable=False),
            sa.Column("discount", sa.Numeric(5, 2), server_default="0"),
            sa.Column("tax_rate", sa.Numeric(5, 2), server_default="0"),
            sa.Column("tax_amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
            sa.Column("fulfilled_qty", sa.Numeric(12, 3), server_default="0"),
            sa.Column("backorder_qty", sa.Numeric(12, 3), server_default="0"),
            sa.ForeignKeyConstraint(["order_id"], ["sales_orders.id"], ondelete="CASCADE", name="fk_sales_order_items_order_id"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_sales_order_items_product_id"),
        )

    if not _has_table("delivery_bills"):
        op.create_table(
            "delivery_bills",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("delivery_no", sa.String(30), nullable=False),
            sa.Column("sale_id", sa.Integer()),
            sa.Column("sales_order_id", sa.Integer()),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("delivery_status", sa.String(30), server_default="Pending"),
            sa.Column("delivery_address", sa.Text()),
            sa.Column("delivery_person", sa.String(120)),
            sa.Column("delivery_date", sa.Date()),
            sa.Column("remarks", sa.Text()),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_delivery_bills_sale_id"),
            sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], name="fk_delivery_bills_sales_order_id"),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_delivery_bills_customer_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_delivery_bills_created_by"),
            sa.UniqueConstraint("delivery_no", name="uq_delivery_bills_delivery_no"),
        )

    if not _has_table("picklists"):
        op.create_table(
            "picklists",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("picklist_no", sa.String(30), nullable=False),
            sa.Column("sale_id", sa.Integer()),
            sa.Column("sales_order_id", sa.Integer()),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), server_default="Open"),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_picklists_sale_id"),
            sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], name="fk_picklists_sales_order_id"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name="fk_picklists_warehouse_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_picklists_created_by"),
            sa.UniqueConstraint("picklist_no", name="uq_picklists_picklist_no"),
        )

    if not _has_table("picklist_items"):
        op.create_table(
            "picklist_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("picklist_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("picked_qty", sa.Numeric(12, 3), server_default="0"),
            sa.Column("is_picked", sa.Boolean(), server_default=sa.false()),
            sa.ForeignKeyConstraint(["picklist_id"], ["picklists.id"], ondelete="CASCADE", name="fk_picklist_items_picklist_id"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_picklist_items_product_id"),
        )

    if not _has_table("packages"):
        op.create_table(
            "packages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("package_no", sa.String(30), nullable=False),
            sa.Column("picklist_id", sa.Integer()),
            sa.Column("sale_id", sa.Integer()),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), server_default="Packed"),
            sa.Column("weight", sa.Numeric(12, 3), server_default="0"),
            sa.Column("remarks", sa.Text()),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["picklist_id"], ["picklists.id"], name="fk_packages_picklist_id"),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_packages_sale_id"),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_packages_customer_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_packages_created_by"),
            sa.UniqueConstraint("package_no", name="uq_packages_package_no"),
        )

    if not _has_table("package_items"):
        op.create_table(
            "package_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("package_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.ForeignKeyConstraint(["package_id"], ["packages.id"], ondelete="CASCADE", name="fk_package_items_package_id"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_package_items_product_id"),
        )

    if not _has_table("payment_allocations"):
        op.create_table(
            "payment_allocations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("payment_id", sa.Integer(), nullable=False),
            sa.Column("sale_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["payment_id"], ["payments_received.id"], ondelete="CASCADE", name="fk_payment_allocations_payment_id"),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_payment_allocations_sale_id"),
        )

    if not _has_table("refunds"):
        op.create_table(
            "refunds",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("refund_no", sa.String(30), nullable=False),
            sa.Column("refund_date", sa.Date(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("credit_note_id", sa.Integer()),
            sa.Column("sale_return_id", sa.Integer()),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("refund_mode", sa.String(30), server_default="Cash"),
            sa.Column("reference_no", sa.String(50)),
            sa.Column("approval_status", sa.String(20), server_default="Approved"),
            sa.Column("notes", sa.Text()),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_refunds_customer_id"),
            sa.ForeignKeyConstraint(["credit_note_id"], ["credit_notes.id"], name="fk_refunds_credit_note_id"),
            sa.ForeignKeyConstraint(["sale_return_id"], ["sales_returns.id"], name="fk_refunds_sale_return_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_refunds_created_by"),
            sa.UniqueConstraint("refund_no", name="uq_refunds_refund_no"),
        )

    if not _has_table("cash_movements"):
        op.create_table(
            "cash_movements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("movement_date", sa.DateTime()),
            sa.Column("movement_type", sa.String(20), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("reason", sa.String(255)),
            sa.Column("created_by", sa.Integer()),
            sa.ForeignKeyConstraint(["session_id"], ["pos_sessions.id"], name="fk_cash_movements_session_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_cash_movements_created_by"),
        )


def downgrade():
    for table in [
        "cash_movements",
        "refunds",
        "payment_allocations",
        "package_items",
        "packages",
        "picklist_items",
        "picklists",
        "delivery_bills",
        "sales_order_items",
        "sales_orders",
        "held_bills",
    ]:
        if _has_table(table):
            op.drop_table(table)
