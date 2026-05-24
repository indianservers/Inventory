"""party tags

Revision ID: 0d4e5f6a7b8c
Revises: a8b9c0d1e2f3
Create Date: 2026-05-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "0d4e5f6a7b8c"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def _has_column(table, column):
    return column in [col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)]


def upgrade():
    if not _has_column("customers", "tags"):
        op.add_column("customers", sa.Column("tags", sa.String(length=255), server_default=""))
    if not _has_column("suppliers", "tags"):
        op.add_column("suppliers", sa.Column("tags", sa.String(length=255), server_default=""))


def downgrade():
    if _has_column("suppliers", "tags"):
        op.drop_column("suppliers", "tags")
    if _has_column("customers", "tags"):
        op.drop_column("customers", "tags")
