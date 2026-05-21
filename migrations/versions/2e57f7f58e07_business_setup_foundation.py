"""business setup foundation

Revision ID: 2e57f7f58e07
Revises: ed0d189147ff
Create Date: 2026-05-21 16:52:58.099990

"""
from alembic import op
import sqlalchemy as sa


revision = "2e57f7f58e07"
down_revision = "ed0d189147ff"
branch_labels = None
depends_on = None


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table):
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)} if _has_table(table) else set()


def _fk_names(table):
    if not _has_table(table):
        return set()
    return {fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys(table) if fk.get("name")}


def _has_fk(table, constrained_columns, referred_table):
    if not _has_table(table):
        return False
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk.get("constrained_columns") == constrained_columns and fk.get("referred_table") == referred_table:
            return True
    return False


def upgrade():
    if not _has_table("companies"):
        op.create_table(
            "companies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("legal_name", sa.String(200), nullable=False, server_default="Vyapara ERP"),
            sa.Column("trade_name", sa.String(200)),
            sa.Column("logo", sa.String(255)),
            sa.Column("address", sa.Text()),
            sa.Column("city", sa.String(100)),
            sa.Column("state", sa.String(100)),
            sa.Column("country", sa.String(100), server_default="India"),
            sa.Column("postal_code", sa.String(20)),
            sa.Column("phone", sa.String(30)),
            sa.Column("email", sa.String(150)),
            sa.Column("website", sa.String(150)),
            sa.Column("tax_number", sa.String(50)),
            sa.Column("currency", sa.String(10), server_default="INR"),
            sa.Column("financial_year_start_month", sa.Integer(), server_default="4"),
            sa.Column("invoice_prefix", sa.String(10), server_default="INV"),
            sa.Column("purchase_prefix", sa.String(10), server_default="PUR"),
            sa.Column("quotation_prefix", sa.String(10), server_default="QUO"),
            sa.Column("receipt_prefix", sa.String(10), server_default="REC"),
            sa.Column("payment_prefix", sa.String(10), server_default="PAY"),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    if not _has_table("branches"):
        op.create_table(
            "branches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("code", sa.String(20), nullable=False),
            sa.Column("address", sa.Text()),
            sa.Column("contact_person", sa.String(100)),
            sa.Column("phone", sa.String(30)),
            sa.Column("email", sa.String(150)),
            sa.Column("tax_number", sa.String(50)),
            sa.Column("status", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.UniqueConstraint("code", name="uq_branches_code"),
        )

    if not _has_table("registers"):
        op.create_table(
            "registers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("code", sa.String(20), nullable=False),
            sa.Column("branch_id", sa.Integer(), nullable=False),
            sa.Column("warehouse_id", sa.Integer(), nullable=False),
            sa.Column("receipt_printer", sa.String(150)),
            sa.Column("status", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], name="fk_registers_branch_id"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], name="fk_registers_warehouse_id"),
            sa.UniqueConstraint("code", name="uq_registers_code"),
        )

    if "branch_id" not in _columns("warehouses"):
        op.add_column("warehouses", sa.Column("branch_id", sa.Integer(), nullable=True))
    if not _has_fk("warehouses", ["branch_id"], "branches"):
        op.create_foreign_key("fk_warehouses_branch_id", "warehouses", "branches", ["branch_id"], ["id"])

    if "register_id" not in _columns("pos_sessions"):
        op.add_column("pos_sessions", sa.Column("register_id", sa.Integer(), nullable=True))
    if not _has_fk("pos_sessions", ["register_id"], "registers"):
        op.create_foreign_key("fk_pos_sessions_register_id", "pos_sessions", "registers", ["register_id"], ["id"])


def downgrade():
    if "fk_pos_sessions_register_id" in _fk_names("pos_sessions"):
        op.drop_constraint("fk_pos_sessions_register_id", "pos_sessions", type_="foreignkey")
    if "register_id" in _columns("pos_sessions"):
        op.drop_column("pos_sessions", "register_id")

    if "fk_warehouses_branch_id" in _fk_names("warehouses"):
        op.drop_constraint("fk_warehouses_branch_id", "warehouses", type_="foreignkey")
    if "branch_id" in _columns("warehouses"):
        op.drop_column("warehouses", "branch_id")

    if _has_table("registers"):
        op.drop_table("registers")
    if _has_table("branches"):
        op.drop_table("branches")
    if _has_table("companies"):
        op.drop_table("companies")
