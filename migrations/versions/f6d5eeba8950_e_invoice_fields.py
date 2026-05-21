"""e-invoice fields

Revision ID: f6d5eeba8950
Revises:
Create Date: 2026-05-21 15:46:24.647361

"""
from alembic import op
import sqlalchemy as sa


revision = "f6d5eeba8950"
down_revision = None
branch_labels = None
depends_on = None


def has_table(inspector, name):
    return name in inspector.get_table_names()


def has_column(inspector, table, column):
    return has_table(inspector, table) and column in {col["name"] for col in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    sale_columns = [
        ("irn", sa.Column("irn", sa.String(length=64), nullable=True)),
        ("irn_ack_no", sa.Column("irn_ack_no", sa.String(length=64), nullable=True)),
        ("irn_ack_dt", sa.Column("irn_ack_dt", sa.DateTime(), nullable=True)),
        ("qr_code_data", sa.Column("qr_code_data", sa.Text(), nullable=True)),
        ("e_invoice_status", sa.Column("e_invoice_status", sa.String(length=20), nullable=True, server_default="Pending")),
    ]
    for name, column in sale_columns:
        if not has_column(inspector, "sales", name):
            op.add_column("sales", column)

    if not has_table(inspector, "eway_bills"):
        op.create_table(
            "eway_bills",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("sale_id", sa.Integer(), nullable=False),
            sa.Column("ewb_no", sa.String(length=30), nullable=False),
            sa.Column("ewb_date", sa.DateTime(), nullable=True),
            sa.Column("valid_upto", sa.DateTime(), nullable=True),
            sa.Column("vehicle_no", sa.String(length=30), nullable=True),
            sa.Column("transporter_name", sa.String(length=150), nullable=True),
            sa.Column("transporter_id", sa.String(length=30), nullable=True),
            sa.Column("supply_type", sa.String(length=20), nullable=True),
            sa.Column("sub_type", sa.String(length=20), nullable=True),
            sa.Column("distance_km", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("ewb_no"),
        )

    if not has_table(inspector, "purchase_orders"):
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("po_no", sa.String(length=30), nullable=False),
            sa.Column("po_date", sa.Date(), nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("expected_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=True),
            sa.Column("subtotal", sa.Numeric(12, 2), nullable=True),
            sa.Column("tax_total", sa.Numeric(12, 2), nullable=True),
            sa.Column("grand_total", sa.Numeric(12, 2), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("terms", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("po_no"),
        )

    if not has_table(inspector, "purchase_order_items"):
        op.create_table(
            "purchase_order_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("po_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("rate", sa.Numeric(12, 4), nullable=False),
            sa.Column("tax_rate", sa.Numeric(5, 2), nullable=True),
            sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
            sa.Column("received_qty", sa.Numeric(12, 3), nullable=True),
            sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not has_table(inspector, "goods_receipt_notes"):
        op.create_table(
            "goods_receipt_notes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("grn_no", sa.String(length=30), nullable=False),
            sa.Column("grn_date", sa.Date(), nullable=False),
            sa.Column("po_id", sa.Integer(), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"]),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("grn_no"),
        )

    if not has_table(inspector, "goods_receipt_items"):
        op.create_table(
            "goods_receipt_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("grn_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("po_item_id", sa.Integer(), nullable=True),
            sa.Column("expected_qty", sa.Numeric(12, 3), nullable=True),
            sa.Column("received_qty", sa.Numeric(12, 3), nullable=False),
            sa.Column("rate", sa.Numeric(12, 4), nullable=False),
            sa.Column("tax_rate", sa.Numeric(5, 2), nullable=True),
            sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
            sa.ForeignKeyConstraint(["grn_id"], ["goods_receipt_notes.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["po_item_id"], ["purchase_order_items.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ["goods_receipt_items", "goods_receipt_notes", "purchase_order_items", "purchase_orders", "eway_bills"]:
        if has_table(inspector, table):
            op.drop_table(table)
    for column in ["e_invoice_status", "qr_code_data", "irn_ack_dt", "irn_ack_no", "irn"]:
        inspector = sa.inspect(bind)
        if has_column(inspector, "sales", column):
            op.drop_column("sales", column)
