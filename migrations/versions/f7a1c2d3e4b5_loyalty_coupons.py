"""loyalty coupons

Revision ID: f7a1c2d3e4b5
Revises: e4c8a40b3b6f
Create Date: 2026-05-21 22:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f7a1c2d3e4b5"
down_revision = "e4c8a40b3b6f"
branch_labels = None
depends_on = None


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade():
    if not _has_table("loyalty_settings"):
        op.create_table(
            "loyalty_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("is_enabled", sa.Boolean(), server_default=sa.false()),
            sa.Column("earn_points_per_amount", sa.Numeric(12, 2), server_default="100"),
            sa.Column("points_earned", sa.Numeric(12, 2), server_default="1"),
            sa.Column("redemption_value_per_point", sa.Numeric(12, 2), server_default="1"),
            sa.Column("points_expiry_days", sa.Integer(), server_default="365"),
            sa.Column("updated_at", sa.DateTime()),
        )
    if not _has_table("customer_loyalty_accounts"):
        op.create_table(
            "customer_loyalty_accounts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("points_balance", sa.Numeric(12, 2), server_default="0"),
            sa.Column("lifetime_points", sa.Numeric(12, 2), server_default="0"),
            sa.Column("updated_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_customer_loyalty_accounts_customer_id"),
        )
    if not _has_table("loyalty_transactions"):
        op.create_table(
            "loyalty_transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("sale_id", sa.Integer()),
            sa.Column("transaction_type", sa.String(20), nullable=False),
            sa.Column("points", sa.Numeric(12, 2), server_default="0"),
            sa.Column("expiry_date", sa.Date()),
            sa.Column("notes", sa.String(255)),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_loyalty_transactions_customer_id"),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_loyalty_transactions_sale_id"),
        )
    if not _has_table("coupons"):
        op.create_table(
            "coupons",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(40), nullable=False, unique=True),
            sa.Column("description", sa.String(255)),
            sa.Column("discount_type", sa.String(20), server_default="Percentage"),
            sa.Column("discount_value", sa.Numeric(12, 2), server_default="0"),
            sa.Column("valid_from", sa.Date()),
            sa.Column("valid_to", sa.Date()),
            sa.Column("minimum_invoice_amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("customer_group", sa.String(80)),
            sa.Column("product_id", sa.Integer()),
            sa.Column("category_id", sa.Integer()),
            sa.Column("max_usage", sa.Integer()),
            sa.Column("per_customer_usage_limit", sa.Integer()),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_coupons_product_id"),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name="fk_coupons_category_id"),
        )
    if not _has_table("coupon_redemptions"):
        op.create_table(
            "coupon_redemptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("coupon_id", sa.Integer(), nullable=False),
            sa.Column("sale_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer()),
            sa.Column("discount_amount", sa.Numeric(12, 2), server_default="0"),
            sa.Column("redeemed_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["coupon_id"], ["coupons.id"], name="fk_coupon_redemptions_coupon_id"),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_coupon_redemptions_sale_id"),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_coupon_redemptions_customer_id"),
        )
    if not _has_table("promotions"):
        op.create_table(
            "promotions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("valid_from", sa.Date()),
            sa.Column("valid_to", sa.Date()),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
    if not _has_table("promotion_rules"):
        op.create_table(
            "promotion_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("promotion_id", sa.Integer(), nullable=False),
            sa.Column("rule_type", sa.String(40), nullable=False),
            sa.Column("config_json", sa.Text()),
            sa.ForeignKeyConstraint(["promotion_id"], ["promotions.id"], name="fk_promotion_rules_promotion_id"),
        )


def downgrade():
    for table in [
        "promotion_rules",
        "promotions",
        "coupon_redemptions",
        "coupons",
        "loyalty_transactions",
        "customer_loyalty_accounts",
        "loyalty_settings",
    ]:
        if _has_table(table):
            op.drop_table(table)
