from datetime import date
from sqlalchemy import func
from app.extensions import db
from app.models import CustomerLedger, Product, Purchase, Sale, SupplierLedger


def dashboard_metrics():
    today = date.today()
    sales_today = db.session.query(func.coalesce(func.sum(Sale.grand_total), 0)).filter(Sale.invoice_date == today).scalar()
    purchases_today = db.session.query(func.coalesce(func.sum(Purchase.grand_total), 0)).filter(Purchase.purchase_date == today).scalar()
    receivables = db.session.query(func.coalesce(func.sum(CustomerLedger.debit - CustomerLedger.credit), 0)).scalar()
    payables = db.session.query(func.coalesce(func.sum(SupplierLedger.credit - SupplierLedger.debit), 0)).scalar()
    stock_value = sum(p.stock_value for p in Product.query.filter_by(is_active=True).all())
    low_stock = Product.query.filter(Product.current_stock <= Product.min_stock, Product.min_stock > 0).limit(10).all()
    return {
        "sales_today": sales_today,
        "purchases_today": purchases_today,
        "receivables": receivables,
        "payables": payables,
        "stock_value": stock_value,
        "low_stock": low_stock,
    }

