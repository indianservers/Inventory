from datetime import date, timedelta

from flask import Blueprint, Response, render_template
from flask_login import login_required
from sqlalchemy import func

from app.models import AccountGroup, ChartOfAccounts, CustomerLedger, Expense, InventoryLedger, PaymentMade, PaymentReceived, Product, ProductBatch, Purchase, Sale, SupplierLedger

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
@login_required
def index():
    return render_template("reports/index.html", title="Reports")


@bp.route("/sales")
@login_required
def sales_report():
    return render_template("reports/table.html", title="Invoice Sales Report", rows=Sale.query.filter(Sale.status.notin_(["Draft", "Cancelled"])).order_by(Sale.invoice_date.desc()).all(), columns=["invoice_no", "invoice_date", "grand_total", "paid_amount", "balance_amount", "status"])


@bp.route("/purchases")
@login_required
def purchase_report():
    return render_template("reports/table.html", title="Purchase Report", rows=Purchase.query.order_by(Purchase.purchase_date.desc()).all(), columns=["purchase_no", "purchase_date", "grand_total", "payment_status"])


@bp.route("/stock")
@login_required
def stock_report():
    return render_template("reports/table.html", title="Stock Report", rows=Product.query.order_by(Product.name).all(), columns=["sku", "name", "current_stock", "average_cost"])


@bp.route("/low-stock")
@login_required
def low_stock_report():
    products = Product.query.filter(Product.min_stock > 0, Product.current_stock <= Product.min_stock).order_by(Product.name).all()
    return render_template("reports/stock_health.html", title="Low Stock Report", products=products, mode="low")


@bp.route("/reorder")
@login_required
def reorder_report():
    products = Product.query.filter(Product.reorder_level > 0, Product.current_stock <= Product.reorder_level).order_by(Product.name).all()
    return render_template("reports/stock_health.html", title="Reorder Report", products=products, mode="reorder")


@bp.route("/valuation")
@login_required
def valuation_report():
    products = Product.query.order_by(Product.name).all()
    total_value = sum(product.stock_value for product in products)
    return render_template("reports/valuation.html", title="Stock Valuation", products=products, total_value=total_value)


@bp.route("/expiry")
@login_required
def expiry_report():
    alert_until = date.today() + timedelta(days=30)
    batches = ProductBatch.query.filter(ProductBatch.expiry_date.isnot(None), ProductBatch.expiry_date <= alert_until).order_by(ProductBatch.expiry_date.asc()).all()
    return render_template("reports/expiry.html", title="Expiry Alerts", batches=batches, today=date.today())


@bp.route("/inventory-ledger")
@login_required
def inventory_ledger():
    return render_template("reports/table.html", title="Inventory Ledger Report", rows=InventoryLedger.query.order_by(InventoryLedger.id.desc()).all(), columns=["date", "reference_no", "movement_type", "qty_in", "qty_out", "balance_qty"])


@bp.route("/profit-loss")
@login_required
def profit_loss():
    sales = sum(float(s.grand_total or 0) for s in Sale.query.filter(Sale.status.notin_(["Draft", "Cancelled"])).all())
    purchases = sum(float(p.grand_total or 0) for p in Purchase.query.all())
    return render_template("reports/profit_loss.html", title="Profit and Loss", sales=sales, purchases=purchases, profit=sales - purchases)


@bp.route("/receivables-aging")
@login_required
def receivables_aging():
    rows = []
    for sale in Sale.query.filter(Sale.balance_amount > 0).order_by(Sale.due_date.asc()).all():
        basis = sale.due_date or sale.invoice_date
        rows.append(_aging_row(sale.customer.name, sale.invoice_no, basis, sale.balance_amount))
    return render_template("reports/aging.html", title="Accounts Receivable Aging", rows=rows, party_label="Customer")


@bp.route("/payables-aging")
@login_required
def payables_aging():
    rows = []
    for purchase in Purchase.query.filter(Purchase.balance_amount > 0).order_by(Purchase.purchase_date.asc()).all():
        due_date = purchase.purchase_date + timedelta(days=int(purchase.supplier.payment_terms or 0))
        rows.append(_aging_row(purchase.supplier.name, purchase.purchase_no, due_date, purchase.balance_amount))
    return render_template("reports/aging.html", title="Accounts Payable Aging", rows=rows, party_label="Supplier")


@bp.route("/trial-balance")
@login_required
def trial_balance():
    rows = []
    total_debit = total_credit = 0
    for account in ChartOfAccounts.query.join(AccountGroup).order_by(AccountGroup.type, ChartOfAccounts.account_code).all():
        balance = float(account.current_balance or 0)
        debit = balance if balance >= 0 else 0
        credit = abs(balance) if balance < 0 else 0
        rows.append({"code": account.account_code, "name": account.account_name, "group": account.group.name, "type": account.group.type, "debit": debit, "credit": credit})
        total_debit += debit
        total_credit += credit
    return render_template("reports/trial_balance.html", title="Trial Balance", rows=rows, total_debit=total_debit, total_credit=total_credit)


@bp.route("/balance-sheet")
@login_required
def balance_sheet():
    sections = _group_account_balances(["Asset", "Liability", "Equity"])
    return render_template("reports/balance_sheet.html", title="Balance Sheet", sections=sections)


@bp.route("/cash-flow")
@login_required
def cash_flow():
    receipts = float(db_sum(PaymentReceived.amount))
    payments = float(db_sum(PaymentMade.amount))
    expenses = float(db_sum(Expense.amount))
    rows = [
        {"label": "Customer receipts", "inflow": receipts, "outflow": 0},
        {"label": "Supplier payments", "inflow": 0, "outflow": payments},
        {"label": "Expenses", "inflow": 0, "outflow": expenses},
    ]
    return render_template("reports/cash_flow.html", title="Cash Flow", rows=rows, net_cash=receipts - payments - expenses)


@bp.route("/tax-summary")
@login_required
def tax_summary():
    sales_tax = float(db.session.query(func.coalesce(func.sum(Sale.tax_total), 0)).filter(Sale.status.notin_(["Draft", "Cancelled"])).scalar())
    purchase_tax = float(db_sum(Purchase.tax_total))
    expense_tax = float(db_sum(Expense.tax_amount))
    return render_template("reports/tax_summary.html", title="Tax Summary", sales_tax=sales_tax, purchase_tax=purchase_tax, expense_tax=expense_tax, net_tax=sales_tax - purchase_tax - expense_tax)


def db_sum(column):
    return column.class_.query.with_entities(func.coalesce(func.sum(column), 0)).scalar()


def _aging_row(party, reference_no, due_date, amount):
    days = max((date.today() - due_date).days, 0)
    buckets = {"current": 0, "days_1_30": 0, "days_31_60": 0, "days_61_90": 0, "over_90": 0}
    amount = float(amount or 0)
    if days == 0:
        buckets["current"] = amount
    elif days <= 30:
        buckets["days_1_30"] = amount
    elif days <= 60:
        buckets["days_31_60"] = amount
    elif days <= 90:
        buckets["days_61_90"] = amount
    else:
        buckets["over_90"] = amount
    return {"party": party, "reference_no": reference_no, "due_date": due_date, "days": days, "amount": amount, **buckets}


def _group_account_balances(types):
    sections = []
    for group_type in types:
        accounts = ChartOfAccounts.query.join(AccountGroup).filter(AccountGroup.type == group_type).order_by(ChartOfAccounts.account_code).all()
        rows = [{"code": account.account_code, "name": account.account_name, "group": account.group.name, "balance": float(account.current_balance or 0)} for account in accounts]
        sections.append({"type": group_type, "rows": rows, "total": sum(row["balance"] for row in rows)})
    return sections
