"""advanced inventory management

Revision ID: 639d431807a5
Revises: 2e57f7f58e07
Create Date: 2026-05-21 17:10:58.530264

"""
from alembic import op
import sqlalchemy as sa


revision = "639d431807a5"
down_revision = "2e57f7f58e07"
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


def upgrade():
    _add_column("products", sa.Column("preferred_supplier_id", sa.Integer(), nullable=True))
    _add_column("products", sa.Column("track_inventory", sa.Boolean(), server_default=sa.true()))
    if not _has_fk("products", ["preferred_supplier_id"], "suppliers"):
        op.create_foreign_key("fk_products_preferred_supplier_id", "products", "suppliers", ["preferred_supplier_id"], ["id"])

    _add_column("price_lists", sa.Column("price_type", sa.String(30), server_default="Retail"))
    _add_column("price_lists", sa.Column("customer_group", sa.String(80), nullable=True))
    _add_column("price_lists", sa.Column("branch_id", sa.Integer(), nullable=True))
    if not _has_fk("price_lists", ["branch_id"], "branches"):
        op.create_foreign_key("fk_price_lists_branch_id", "price_lists", "branches", ["branch_id"], ["id"])

    _add_column("stock_adjustments", sa.Column("adjustment_type", sa.String(30), server_default="Other"))

    if not _has_table("product_variants"):
        op.create_table(
            "product_variants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("size", sa.String(50)),
            sa.Column("color", sa.String(50)),
            sa.Column("weight", sa.String(50)),
            sa.Column("model", sa.String(80)),
            sa.Column("packaging", sa.String(80)),
            sa.Column("sku", sa.String(50), nullable=False),
            sa.Column("barcode", sa.String(100)),
            sa.Column("purchase_price", sa.Numeric(12, 2), server_default="0"),
            sa.Column("sales_price", sa.Numeric(12, 2), server_default="0"),
            sa.Column("mrp", sa.Numeric(12, 2), server_default="0"),
            sa.Column("current_stock", sa.Numeric(12, 3), server_default="0"),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE", name="fk_product_variants_product_id"),
            sa.UniqueConstraint("sku", name="uq_product_variants_sku"),
            sa.UniqueConstraint("barcode", name="uq_product_variants_barcode"),
        )

    if not _has_table("batches"):
        op.create_table(
            "batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("batch_no", sa.String(100), nullable=False),
            sa.Column("manufacture_date", sa.Date()),
            sa.Column("expiry_date", sa.Date()),
            sa.Column("purchase_reference", sa.String(50)),
            sa.Column("quantity", sa.Numeric(12, 3), server_default="0"),
            sa.Column("cost", sa.Numeric(12, 4), server_default="0"),
            sa.Column("status", sa.String(20), server_default="Available"),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_batches_product_id"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name="fk_batches_warehouse_id"),
            sa.UniqueConstraint("product_id", "warehouse_id", "batch_no", name="uq_batch_product_warehouse_no"),
        )

    if not _has_table("serial_numbers"):
        op.create_table(
            "serial_numbers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("warehouse_id", sa.Integer()),
            sa.Column("serial_no", sa.String(100), nullable=False),
            sa.Column("status", sa.String(20), server_default="Available"),
            sa.Column("purchase_id", sa.Integer()),
            sa.Column("sale_id", sa.Integer()),
            sa.Column("batch_id", sa.Integer()),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_serial_numbers_product_id"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name="fk_serial_numbers_warehouse_id"),
            sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], name="fk_serial_numbers_purchase_id"),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_serial_numbers_sale_id"),
            sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], name="fk_serial_numbers_batch_id"),
            sa.UniqueConstraint("serial_no", name="uq_serial_numbers_serial_no"),
        )

    if not _has_table("product_price_lists"):
        op.create_table(
            "product_price_lists",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("branch_id", sa.Integer()),
            sa.Column("customer_group", sa.String(80)),
            sa.Column("price_type", sa.String(30), server_default="Retail"),
            sa.Column("price", sa.Numeric(12, 2), nullable=False),
            sa.Column("discount_pct", sa.Numeric(5, 2), server_default="0"),
            sa.Column("valid_from", sa.Date()),
            sa.Column("valid_to", sa.Date()),
            sa.Column("status", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_product_price_lists_product_id"),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name="fk_product_price_lists_branch_id"),
        )

    if not _has_table("stock_openings"):
        op.create_table(
            "stock_openings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("opening_no", sa.String(30), nullable=False),
            sa.Column("opening_date", sa.Date(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("rate", sa.Numeric(12, 4), server_default="0"),
            sa.Column("value", sa.Numeric(12, 2), server_default="0"),
            sa.Column("notes", sa.Text()),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_stock_openings_product_id"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name="fk_stock_openings_warehouse_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_stock_openings_created_by"),
            sa.UniqueConstraint("opening_no", name="uq_stock_openings_opening_no"),
        )

    if not _has_table("composite_items"):
        op.create_table(
            "composite_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("status", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_composite_items_product_id"),
        )

    if not _has_table("composite_item_components"):
        op.create_table(
            "composite_item_components",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("composite_item_id", sa.Integer(), nullable=False),
            sa.Column("component_product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.ForeignKeyConstraint(["composite_item_id"], ["composite_items.id"], ondelete="CASCADE", name="fk_composite_components_item_id"),
            sa.ForeignKeyConstraint(["component_product_id"], ["products.id"], name="fk_composite_components_product_id"),
        )

    if not _has_table("repacking_transactions"):
        op.create_table(
            "repacking_transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("repack_no", sa.String(30), nullable=False),
            sa.Column("repack_date", sa.Date(), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("notes", sa.Text()),
            sa.Column("status", sa.String(20), server_default="Completed"),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name="fk_repacking_transactions_warehouse_id"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_repacking_transactions_created_by"),
            sa.UniqueConstraint("repack_no", name="uq_repacking_transactions_repack_no"),
        )

    if not _has_table("repacking_items"):
        op.create_table(
            "repacking_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("repacking_id", sa.Integer(), nullable=False),
            sa.Column("line_type", sa.String(10), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("rate", sa.Numeric(12, 4), server_default="0"),
            sa.ForeignKeyConstraint(["repacking_id"], ["repacking_transactions.id"], ondelete="CASCADE", name="fk_repacking_items_repacking_id"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_repacking_items_product_id"),
        )


def downgrade():
    for table in [
        "repacking_items",
        "repacking_transactions",
        "composite_item_components",
        "composite_items",
        "stock_openings",
        "product_price_lists",
        "serial_numbers",
        "batches",
        "product_variants",
    ]:
        if _has_table(table):
            op.drop_table(table)
