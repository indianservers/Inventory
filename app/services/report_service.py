from datetime import date
from sqlalchemy import func
from app.extensions import db
from app.models import CustomerLedger, PaymentReceived, Product, Purchase, Sale, SaleItem, SupplierLedger, Warehouse


def dashboard_metrics():
    today = date.today()
    sales_today = db.session.query(func.coalesce(func.sum(Sale.grand_total), 0)).filter(Sale.invoice_date == today, Sale.status.notin_(["Draft", "Cancelled"])).scalar()
    purchases_today = db.session.query(func.coalesce(func.sum(Purchase.grand_total), 0)).filter(Purchase.purchase_date == today).scalar()
    receivables = db.session.query(func.coalesce(func.sum(CustomerLedger.debit - CustomerLedger.credit), 0)).scalar()
    payables = db.session.query(func.coalesce(func.sum(SupplierLedger.credit - SupplierLedger.debit), 0)).scalar()
    stock_value = sum(p.stock_value for p in Product.query.filter_by(is_active=True).all())
    gross_profit = sum(float(item.line_total or 0) - (float(item.cost_price or 0) * float(item.quantity or 0)) for item in SaleItem.query.join(Sale).filter(Sale.invoice_date == today, Sale.status.notin_(["Draft", "Cancelled"])).all())
    cash_in_hand = db.session.query(func.coalesce(func.sum(PaymentReceived.amount), 0)).filter(PaymentReceived.payment_mode == "Cash").scalar()
    card_collection = db.session.query(func.coalesce(func.sum(PaymentReceived.amount), 0)).filter(PaymentReceived.payment_mode == "Card").scalar()
    upi_collection = db.session.query(func.coalesce(func.sum(PaymentReceived.amount), 0)).filter(PaymentReceived.payment_mode == "UPI").scalar()
    warehouse_stock_value = [(w.name, sum(p.stock_value for p in w.products)) for w in Warehouse.query.order_by(Warehouse.name).all()]
    low_stock = Product.query.filter(Product.current_stock <= Product.min_stock, Product.min_stock > 0).limit(10).all()
    return {
        "sales_today": sales_today,
        "purchases_today": purchases_today,
        "gross_profit": gross_profit,
        "cash_in_hand": cash_in_hand,
        "card_collection": card_collection,
        "upi_collection": upi_collection,
        "receivables": receivables,
        "payables": payables,
        "stock_value": stock_value,
        "warehouse_stock_value": warehouse_stock_value,
        "low_stock": low_stock,
    }
