"""purchase tax reports dashboard

Revision ID: 842f55653a89
Revises: b655f8fde2ea
Create Date: 2026-05-21 17:56:16.851777

"""
from alembic import op
import sqlalchemy as sa


revision = "842f55653a89"
down_revision = "b655f8fde2ea"
branch_labels = None
depends_on = None


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table):
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)} if _has_table(table) else set()


def _add_column(table, column):
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade():
    _add_column("suppliers", sa.Column("contact_person", sa.String(120)))
    _add_column("suppliers", sa.Column("billing_address", sa.Text()))
    _add_column("suppliers", sa.Column("tax_treatment", sa.String(30), server_default="Registered"))

    _add_column("purchases", sa.Column("due_date", sa.Date()))
    _add_column("purchases", sa.Column("status", sa.String(20), server_default="Approved"))
    _add_column("purchases", sa.Column("cancelled_at", sa.DateTime()))
    _add_column("purchases", sa.Column("cancellation_reason", sa.Text()))

    _add_column("purchase_orders", sa.Column("discount_total", sa.Numeric(12, 2), server_default="0"))
    _add_column("purchase_order_items", sa.Column("discount", sa.Numeric(5, 2), server_default="0"))
    _add_column("purchase_order_items", sa.Column("discount_amount", sa.Numeric(12, 2), server_default="0"))

    _add_column("payments_made", sa.Column("unallocated_amount", sa.Numeric(12, 2), server_default="0"))
    _add_column("payments_made", sa.Column("status", sa.String(20), server_default="Posted"))
    _add_column("payments_made", sa.Column("reversed_at", sa.DateTime()))
    _add_column("payments_made", sa.Column("reversal_reason", sa.Text()))

    if not _has_table("vendor_payment_allocations"):
        op.create_table(
            "vendor_payment_allocations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("payment_id", sa.Integer(), nullable=False),
            sa.Column("purchase_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["payment_id"], ["payments_made.id"], ondelete="CASCADE", name="fk_vendor_payment_allocations_payment_id"),
            sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], name="fk_vendor_payment_allocations_purchase_id"),
        )

    if not _has_table("vendor_credits"):
        op.create_table(
            "vendor_credits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("credit_no", sa.String(30), nullable=False),
            sa.Column("credit_date", sa.Date(), nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("purchase_id", sa.Integer()),
            sa.Column("purchase_return_id", sa.Integer()),
            sa.Column("reason", sa.Text()),
            sa.Column("subtotal", sa.Numeric(12, 2), server_default="0"),
            sa.Column("tax_total", sa.Numeric(12, 2), server_default="0"),
            sa.Column("grand_total", sa.Numeric(12, 2), server_default="0"),
            sa.Column("applied_amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("refunded_amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("status", sa.String(20), server_default="Issued"),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_vendor_credits_supplier_id"),
            sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], name="fk_vendor_credits_purchase_id"),
            sa.ForeignKeyConstraint(["purchase_return_id"], ["purchase_returns.id"], name="fk_vendor_credits_purchase_return_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_vendor_credits_created_by"),
            sa.UniqueConstraint("credit_no", name="uq_vendor_credits_credit_no"),
        )

    if not _has_table("vendor_credit_items"):
        op.create_table(
            "vendor_credit_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("vendor_credit_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("rate", sa.Numeric(12, 4), nullable=False),
            sa.Column("tax_rate", sa.Numeric(5, 2), server_default="0"),
            sa.Column("tax_amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
            sa.ForeignKeyConstraint(["vendor_credit_id"], ["vendor_credits.id"], ondelete="CASCADE", name="fk_vendor_credit_items_credit_id"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_vendor_credit_items_product_id"),
        )

    if not _has_table("tax_groups"):
        op.create_table(
            "tax_groups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("status", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table("tax_rates"):
        op.create_table(
            "tax_rates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tax_group_id", sa.Integer()),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("rate", sa.Numeric(5, 2), server_default="0"),
            sa.Column("tax_type", sa.String(30), server_default="GST"),
            sa.Column("treatment", sa.String(30), server_default="Taxable"),
            sa.Column("status", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["tax_group_id"], ["tax_groups.id"], name="fk_tax_rates_tax_group_id"),
        )


def downgrade():
    for table in ["tax_rates", "tax_groups", "vendor_credit_items", "vendor_credits", "vendor_payment_allocations"]:
        if _has_table(table):
            op.drop_table(table)
