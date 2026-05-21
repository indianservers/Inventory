"""custom modules

Revision ID: a8b9c0d1e2f3
Revises: f7a1c2d3e4b5
Create Date: 2026-05-21 23:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a8b9c0d1e2f3"
down_revision = "f7a1c2d3e4b5"
branch_labels = None
depends_on = None


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade():
    if not _has_table("custom_modules"):
        op.create_table(
            "custom_modules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("module_key", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("plural_name", sa.String(length=140)),
            sa.Column("description", sa.Text()),
            sa.Column("icon", sa.String(length=50), server_default="bi-grid"),
            sa.Column("show_in_sidebar", sa.Boolean(), server_default=sa.true()),
            sa.Column("allow_import", sa.Boolean(), server_default=sa.true()),
            sa.Column("allow_export", sa.Boolean(), server_default=sa.true()),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.UniqueConstraint("module_key"),
        )
    if not _has_table("custom_module_fields"):
        op.create_table(
            "custom_module_fields",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("module_id", sa.Integer(), nullable=False),
            sa.Column("field_key", sa.String(length=80), nullable=False),
            sa.Column("label", sa.String(length=120), nullable=False),
            sa.Column("field_type", sa.String(length=30), server_default="Text"),
            sa.Column("options", sa.Text()),
            sa.Column("is_required", sa.Boolean(), server_default=sa.false()),
            sa.Column("show_in_list", sa.Boolean(), server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), server_default="0"),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["module_id"], ["custom_modules.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("module_id", "field_key", name="uq_custom_module_field"),
        )
    if not _has_table("custom_module_records"):
        op.create_table(
            "custom_module_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("module_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("data_json", sa.Text()),
            sa.Column("status", sa.String(length=30), server_default="Active"),
            sa.Column("created_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["module_id"], ["custom_modules.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        )


def downgrade():
    for table in ["custom_module_records", "custom_module_fields", "custom_modules"]:
        if _has_table(table):
            op.drop_table(table)
