"""razorpay fields

Revision ID: d9b2b9b6e1f1
Revises: ec2eab559ca6
Create Date: 2026-05-21 21:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d9b2b9b6e1f1"
down_revision = "ec2eab559ca6"
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
    _add_column("sales", sa.Column("razorpay_order_id", sa.String(100)))
    _add_column("sales", sa.Column("razorpay_payment_id", sa.String(100)))
    _add_column("sales", sa.Column("razorpay_signature", sa.String(255)))
    _add_column("sales", sa.Column("razorpay_verified_at", sa.DateTime()))


def downgrade():
    for column in ["razorpay_verified_at", "razorpay_signature", "razorpay_payment_id", "razorpay_order_id"]:
        if column in _columns("sales"):
            op.drop_column("sales", column)
