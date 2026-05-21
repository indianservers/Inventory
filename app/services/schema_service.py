from sqlalchemy import inspect, text

from app.extensions import db


SALE_COLUMNS = {
    "status": "VARCHAR(20) DEFAULT 'Issued'",
    "updated_by": "INTEGER",
    "issued_at": "DATETIME",
    "cancelled_at": "DATETIME",
    "cancellation_reason": "TEXT",
    "irn": "VARCHAR(64)",
    "irn_ack_no": "VARCHAR(64)",
    "irn_ack_dt": "DATETIME",
    "qr_code_data": "TEXT",
    "e_invoice_status": "VARCHAR(20) DEFAULT 'Pending'",
}


def ensure_invoice_schema(app):
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        if "sales" not in inspector.get_table_names():
            return
        existing = {column["name"] for column in inspector.get_columns("sales")}
        dialect = db.engine.dialect.name
        for column, column_type in SALE_COLUMNS.items():
            if column not in existing:
                db.session.execute(text(f"ALTER TABLE sales ADD COLUMN {column} {column_type}"))
        db.session.execute(text("UPDATE sales SET status = CASE WHEN payment_status = 'Paid' THEN 'Paid' WHEN payment_status = 'Partial' THEN 'Partially Paid' ELSE 'Issued' END WHERE status IS NULL OR status = ''"))
        if dialect != "sqlite":
            db.session.execute(text("UPDATE sales SET issued_at = created_at WHERE issued_at IS NULL AND status <> 'Draft'"))
        db.session.commit()
