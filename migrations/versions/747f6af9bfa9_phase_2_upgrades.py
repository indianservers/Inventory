"""phase 2 upgrades

Revision ID: 747f6af9bfa9
Revises: f6d5eeba8950
Create Date: 2026-05-21 16:06:35.356413

"""
from alembic import op
import sqlalchemy as sa


revision = "747f6af9bfa9"
down_revision = "f6d5eeba8950"
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
    if "price_lists" not in existing:
        op.create_table("price_lists", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("description", sa.Text()), sa.Column("discount_pct", sa.Numeric(5, 2)), sa.Column("is_default", sa.Boolean()), sa.Column("currency", sa.String(10)), sa.Column("valid_from", sa.Date()), sa.Column("valid_to", sa.Date()), sa.Column("status", sa.Boolean()), sa.Column("created_at", sa.DateTime()))
    if "price_list_items" not in existing:
        op.create_table("price_list_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("price_list_id", sa.Integer(), nullable=False), sa.Column("product_id", sa.Integer(), nullable=False), sa.Column("sales_price", sa.Numeric(12, 2), nullable=False), sa.Column("min_qty", sa.Numeric(12, 3)), sa.ForeignKeyConstraint(["price_list_id"], ["price_lists.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["product_id"], ["products.id"]), sa.UniqueConstraint("price_list_id", "product_id", "min_qty", name="uq_price_list_item"))
    add_col("customers", sa.Column("price_list_id", sa.Integer(), nullable=True))
    add_col("users", sa.Column("totp_secret", sa.String(32), nullable=True))
    add_col("users", sa.Column("totp_enabled", sa.Boolean(), nullable=True))
    add_col("users", sa.Column("backup_codes", sa.Text(), nullable=True))

    existing = tables()
    if "pos_sessions" not in existing:
        op.create_table("pos_sessions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_no", sa.String(30), nullable=False, unique=True), sa.Column("opened_by", sa.Integer(), nullable=False), sa.Column("opened_at", sa.DateTime()), sa.Column("closed_at", sa.DateTime()), sa.Column("opening_cash", sa.Numeric(12, 2)), sa.Column("closing_cash", sa.Numeric(12, 2)), sa.Column("total_sales", sa.Numeric(12, 2)), sa.Column("total_cash", sa.Numeric(12, 2)), sa.Column("total_card", sa.Numeric(12, 2)), sa.Column("total_upi", sa.Numeric(12, 2)), sa.Column("status", sa.String(20)), sa.ForeignKeyConstraint(["opened_by"], ["users.id"]))
    if "bank_statement_lines" not in existing:
        op.create_table("bank_statement_lines", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("bank_account_id", sa.Integer(), nullable=False), sa.Column("txn_date", sa.Date(), nullable=False), sa.Column("description", sa.Text()), sa.Column("debit", sa.Numeric(12, 2)), sa.Column("credit", sa.Numeric(12, 2)), sa.Column("balance", sa.Numeric(12, 2)), sa.Column("reference_no", sa.String(80)), sa.Column("matched_to_type", sa.String(30)), sa.Column("matched_to_id", sa.Integer()), sa.Column("is_reconciled", sa.Boolean()), sa.Column("created_at", sa.DateTime()), sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"]))
    if "credit_notes" not in existing:
        op.create_table("credit_notes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("cn_no", sa.String(30), nullable=False, unique=True), sa.Column("cn_date", sa.Date(), nullable=False), sa.Column("customer_id", sa.Integer(), nullable=False), sa.Column("sale_id", sa.Integer()), sa.Column("reason", sa.Text()), sa.Column("adjustment_type", sa.String(20)), sa.Column("subtotal", sa.Numeric(12, 2)), sa.Column("tax_total", sa.Numeric(12, 2)), sa.Column("grand_total", sa.Numeric(12, 2)), sa.Column("status", sa.String(20)), sa.Column("created_by", sa.Integer()), sa.Column("created_at", sa.DateTime()), sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]), sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]), sa.ForeignKeyConstraint(["created_by"], ["users.id"]))
    if "credit_note_items" not in existing:
        op.create_table("credit_note_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("cn_id", sa.Integer(), nullable=False), sa.Column("product_id", sa.Integer(), nullable=False), sa.Column("quantity", sa.Numeric(12, 3), nullable=False), sa.Column("rate", sa.Numeric(12, 4), nullable=False), sa.Column("tax_rate", sa.Numeric(5, 2)), sa.Column("tax_amount", sa.Numeric(12, 2)), sa.Column("line_total", sa.Numeric(12, 2), nullable=False), sa.ForeignKeyConstraint(["cn_id"], ["credit_notes.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["product_id"], ["products.id"]))
    if "debit_notes" not in existing:
        op.create_table("debit_notes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dn_no", sa.String(30), nullable=False, unique=True), sa.Column("dn_date", sa.Date(), nullable=False), sa.Column("supplier_id", sa.Integer(), nullable=False), sa.Column("purchase_id", sa.Integer()), sa.Column("reason", sa.Text()), sa.Column("adjustment_type", sa.String(20)), sa.Column("subtotal", sa.Numeric(12, 2)), sa.Column("tax_total", sa.Numeric(12, 2)), sa.Column("grand_total", sa.Numeric(12, 2)), sa.Column("status", sa.String(20)), sa.Column("created_by", sa.Integer()), sa.Column("created_at", sa.DateTime()), sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]), sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"]), sa.ForeignKeyConstraint(["created_by"], ["users.id"]))
    if "debit_note_items" not in existing:
        op.create_table("debit_note_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dn_id", sa.Integer(), nullable=False), sa.Column("product_id", sa.Integer(), nullable=False), sa.Column("quantity", sa.Numeric(12, 3), nullable=False), sa.Column("rate", sa.Numeric(12, 4), nullable=False), sa.Column("tax_rate", sa.Numeric(5, 2)), sa.Column("tax_amount", sa.Numeric(12, 2)), sa.Column("line_total", sa.Numeric(12, 2), nullable=False), sa.ForeignKeyConstraint(["dn_id"], ["debit_notes.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["product_id"], ["products.id"]))


def downgrade():
    for table in ["debit_note_items", "debit_notes", "credit_note_items", "credit_notes", "bank_statement_lines", "pos_sessions", "price_list_items", "price_lists"]:
        if table in tables():
            op.drop_table(table)
    for table, column in [("customers", "price_list_id"), ("users", "backup_codes"), ("users", "totp_enabled"), ("users", "totp_secret")]:
        if column in cols(table):
            op.drop_column(table, column)
