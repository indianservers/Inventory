from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import extract, func

from app.extensions import db
from app.models import PaymentMade, PaymentReceived, Product, Purchase, Sale, SaleItem
from app.services.report_service import dashboard_metrics

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    metrics = dashboard_metrics()
    sales_monthly = [0] * 12
    purchase_monthly = [0] * 12
    for month, total in db.session.query(extract("month", Sale.invoice_date), func.sum(Sale.grand_total)).group_by(extract("month", Sale.invoice_date)):
        sales_monthly[int(month) - 1] = float(total or 0)
    for month, total in db.session.query(extract("month", Purchase.purchase_date), func.sum(Purchase.grand_total)).group_by(extract("month", Purchase.purchase_date)):
        purchase_monthly[int(month) - 1] = float(total or 0)
    recent_invoices = Sale.query.order_by(Sale.id.desc()).limit(8).all()
    recent_payments = PaymentReceived.query.order_by(PaymentReceived.id.desc()).limit(8).all()
    top_products = db.session.query(Product.name, func.coalesce(func.sum(SaleItem.quantity), 0)).join(SaleItem, SaleItem.product_id == Product.id, isouter=True).group_by(Product.id).limit(10).all()
    cash_balance = sum(float(p.amount or 0) for p in PaymentReceived.query.all()) - sum(float(p.amount or 0) for p in PaymentMade.query.all())
    return render_template("dashboard/index.html", title="Dashboard", metrics=metrics, sales_monthly=sales_monthly, purchase_monthly=purchase_monthly, recent_invoices=recent_invoices, recent_payments=recent_payments, top_products=top_products, cash_balance=cash_balance)
