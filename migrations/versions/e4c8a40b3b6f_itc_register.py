"""itc register

Revision ID: e4c8a40b3b6f
Revises: d9b2b9b6e1f1
Create Date: 2026-05-21 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e4c8a40b3b6f"
down_revision = "d9b2b9b6e1f1"
branch_labels = None
depends_on = None


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade():
    if not _has_table("itc_entries"):
        op.create_table(
            "itc_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("purchase_id", sa.Integer(), nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("invoice_no", sa.String(50)),
            sa.Column("invoice_date", sa.Date()),
            sa.Column("taxable_value", sa.Numeric(12, 2), server_default="0"),
            sa.Column("input_tax_cgst", sa.Numeric(12, 2), server_default="0"),
            sa.Column("input_tax_sgst", sa.Numeric(12, 2), server_default="0"),
            sa.Column("input_tax_igst", sa.Numeric(12, 2), server_default="0"),
            sa.Column("input_tax_vat", sa.Numeric(12, 2), server_default="0"),
            sa.Column("eligible_itc_amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("blocked_itc_amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("ineligible_reason", sa.String(255)),
            sa.Column("itc_status", sa.String(20), server_default="Eligible"),
            sa.Column("claim_period", sa.String(7)),
            sa.Column("reversal_reason", sa.String(255)),
            sa.Column("remarks", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], name="fk_itc_entries_purchase_id"),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_itc_entries_supplier_id"),
        )


def downgrade():
    if _has_table("itc_entries"):
        op.drop_table("itc_entries")
