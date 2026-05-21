import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from io import StringIO

from flask import Blueprint, Response, render_template, request, send_file
from flask_login import login_required
from sqlalchemy import extract, func

from app.extensions import db
from app.models import AccountGroup, ChartOfAccounts, CreditNote, CustomerLedger, Expense, InventoryLedger, PaymentMade, PaymentReceived, Product, ProductBatch, Purchase, Sale, SaleItem, SupplierLedger
from app.utils.excel_export import export_to_excel

bp = Blueprint("reports", __name__, url_prefix="/reports")
XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@bp.route("/")
@login_required
def index():
    return render_template("reports/index.html", title="Reports")


@bp.route("/sales")
@login_required
def sales_report():
    rows = Sale.query.filter(Sale.status.notin_(["Draft", "Cancelled"])).order_by(Sale.invoice_date.desc()).all()
    columns = ["invoice_no", "invoice_date", "grand_total", "paid_amount", "balance_amount", "status"]
    if request.args.get("export") == "xlsx":
        return excel_response("sales-report.xlsx", "Sales", [c.replace("_", " ").title() for c in columns], [[getattr(r, c) for c in columns] for r in rows])
    return render_template("reports/table.html", title="Invoice Sales Report", rows=rows, columns=columns)


@bp.route("/purchases")
@login_required
def purchase_report():
    rows = Purchase.query.order_by(Purchase.purchase_date.desc()).all()
    columns = ["purchase_no", "purchase_date", "grand_total", "payment_status"]
    if request.args.get("export") == "xlsx":
        return excel_response("purchase-report.xlsx", "Purchases", [c.replace("_", " ").title() for c in columns], [[getattr(r, c) for c in columns] for r in rows])
    return render_template("reports/table.html", title="Purchase Report", rows=rows, columns=columns)


@bp.route("/stock")
@login_required
def stock_report():
    rows = Product.query.order_by(Product.name).all()
    columns = ["sku", "name", "current_stock", "average_cost"]
    if request.args.get("export") == "xlsx":
        return excel_response("stock-report.xlsx", "Stock", [c.replace("_", " ").title() for c in columns], [[getattr(r, c) for c in columns] for r in rows])
    return render_template("reports/table.html", title="Stock Report", rows=rows, columns=columns)


@bp.route("/low-stock")
@login_required
def low_stock_report():
    products = Product.query.filter(Product.min_stock > 0, Product.current_stock <= Product.min_stock).order_by(Product.name).all()
    if request.args.get("export") == "xlsx":
        return stock_health_excel("low-stock.xlsx", "Low Stock", products)
    return render_template("reports/stock_health.html", title="Low Stock Report", products=products, mode="low")


@bp.route("/reorder")
@login_required
def reorder_report():
    products = Product.query.filter(Product.reorder_level > 0, Product.current_stock <= Product.reorder_level).order_by(Product.name).all()
    if request.args.get("export") == "xlsx":
        return stock_health_excel("reorder-report.xlsx", "Reorder", products)
    return render_template("reports/stock_health.html", title="Reorder Report", products=products, mode="reorder")


@bp.route("/valuation")
@login_required
def valuation_report():
    products = Product.query.order_by(Product.name).all()
    total_value = sum(product.stock_value for product in products)
    if request.args.get("export") == "xlsx":
        rows = [[p.sku, p.name, p.warehouse.name if p.warehouse else "", p.current_stock, p.average_cost, p.stock_value] for p in products]
        return excel_response("stock-valuation.xlsx", "Valuation", ["SKU", "Product", "Warehouse", "Qty", "Average Cost", "Stock Value"], rows)
    return render_template("reports/valuation.html", title="Stock Valuation", products=products, total_value=total_value)


@bp.route("/expiry")
@login_required
def expiry_report():
    alert_until = date.today() + timedelta(days=30)
    batches = ProductBatch.query.filter(ProductBatch.expiry_date.isnot(None), ProductBatch.expiry_date <= alert_until).order_by(ProductBatch.expiry_date.asc()).all()
    if request.args.get("export") == "xlsx":
        rows = [[b.product.name, b.batch_no, b.expiry_date, b.quantity, b.warehouse.name if b.warehouse else ""] for b in batches]
        return excel_response("expiry-alerts.xlsx", "Expiry", ["Product", "Batch", "Expiry", "Qty", "Warehouse"], rows)
    return render_template("reports/expiry.html", title="Expiry Alerts", batches=batches, today=date.today())


@bp.route("/inventory-ledger")
@login_required
def inventory_ledger():
    rows = InventoryLedger.query.order_by(InventoryLedger.id.desc()).all()
    columns = ["date", "reference_no", "movement_type", "qty_in", "qty_out", "balance_qty"]
    if request.args.get("export") == "xlsx":
        return excel_response("inventory-ledger.xlsx", "Inventory Ledger", [c.replace("_", " ").title() for c in columns], [[getattr(r, c) for c in columns] for r in rows])
    return render_template("reports/table.html", title="Inventory Ledger Report", rows=rows, columns=columns)


@bp.route("/profit-loss")
@login_required
def profit_loss():
    sales = sum(float(s.grand_total or 0) for s in Sale.query.filter(Sale.status.notin_(["Draft", "Cancelled"])).all())
    purchases = sum(float(p.grand_total or 0) for p in Purchase.query.all())
    rows = [["Sales Income", sales], ["Purchases / Cost", purchases], ["Net Profit", sales - purchases]]
    if request.args.get("export") == "xlsx":
        return excel_response("profit-loss.xlsx", "Profit Loss", ["Particular", "Amount"], rows)
    return render_template("reports/profit_loss.html", title="Profit and Loss", sales=sales, purchases=purchases, profit=sales - purchases)


@bp.route("/receivables-aging")
@login_required
def receivables_aging():
    rows = []
    for sale in Sale.query.filter(Sale.balance_amount > 0).order_by(Sale.due_date.asc()).all():
        basis = sale.due_date or sale.invoice_date
        rows.append(_aging_row(sale.customer.name, sale.invoice_no, basis, sale.balance_amount))
    if request.args.get("export") == "xlsx":
        return aging_excel("receivables-aging.xlsx", "Receivables", rows)
    return render_template("reports/aging.html", title="Accounts Receivable Aging", rows=rows, party_label="Customer")


@bp.route("/payables-aging")
@login_required
def payables_aging():
    rows = []
    for purchase in Purchase.query.filter(Purchase.balance_amount > 0).order_by(Purchase.purchase_date.asc()).all():
        due_date = purchase.purchase_date + timedelta(days=int(purchase.supplier.payment_terms or 0))
        rows.append(_aging_row(purchase.supplier.name, purchase.purchase_no, due_date, purchase.balance_amount))
    if request.args.get("export") == "xlsx":
        return aging_excel("payables-aging.xlsx", "Payables", rows)
    return render_template("reports/aging.html", title="Accounts Payable Aging", rows=rows, party_label="Supplier")


@bp.route("/trial-balance")
@login_required
def trial_balance():
    rows, total_debit, total_credit = trial_balance_rows()
    if request.args.get("export") == "xlsx":
        return excel_response("trial-balance.xlsx", "Trial Balance", ["Code", "Name", "Group", "Type", "Debit", "Credit"], [[r["code"], r["name"], r["group"], r["type"], r["debit"], r["credit"]] for r in rows])
    return render_template("reports/trial_balance.html", title="Trial Balance", rows=rows, total_debit=total_debit, total_credit=total_credit)


@bp.route("/balance-sheet")
@login_required
def balance_sheet():
    sections = _group_account_balances(["Asset", "Liability", "Equity"])
    if request.args.get("export") == "xlsx":
        rows = []
        for section in sections:
            for row in section["rows"]:
                rows.append([section["type"], row["code"], row["name"], row["group"], row["balance"]])
            rows.append([section["type"], "", "Total", "", section["total"]])
        return excel_response("balance-sheet.xlsx", "Balance Sheet", ["Type", "Code", "Account", "Group", "Balance"], rows)
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
    net_cash = receipts - payments - expenses
    if request.args.get("export") == "xlsx":
        return excel_response("cash-flow.xlsx", "Cash Flow", ["Activity", "Inflow", "Outflow"], [[r["label"], r["inflow"], r["outflow"]] for r in rows] + [["Net Cash Flow", net_cash, ""]])
    return render_template("reports/cash_flow.html", title="Cash Flow", rows=rows, net_cash=net_cash)


@bp.route("/tax-summary")
@login_required
def tax_summary():
    sales_tax = float(db.session.query(func.coalesce(func.sum(Sale.tax_total), 0)).filter(Sale.status.notin_(["Draft", "Cancelled"])).scalar())
    purchase_tax = float(db_sum(Purchase.tax_total))
    expense_tax = float(db_sum(Expense.tax_amount))
    rows = [["Output tax on sales", sales_tax], ["Input tax on purchases", purchase_tax], ["Input tax on expenses", expense_tax], ["Net Tax Payable", sales_tax - purchase_tax - expense_tax]]
    if request.args.get("export") == "xlsx":
        return excel_response("tax-summary.xlsx", "Tax Summary", ["Particular", "Amount"], rows)
    return render_template("reports/tax_summary.html", title="Tax Summary", sales_tax=sales_tax, purchase_tax=purchase_tax, expense_tax=expense_tax, net_tax=sales_tax - purchase_tax - expense_tax)


@bp.route("/gstr1")
@login_required
def gstr1_report():
    month = int(request.args.get("month") or date.today().month)
    year = int(request.args.get("year") or date.today().year)
    sales = Sale.query.filter(extract("month", Sale.invoice_date) == month, extract("year", Sale.invoice_date) == year, Sale.tax_total > 0).order_by(Sale.invoice_date, Sale.invoice_no).all()
    payload, preview = build_gstr1_payload(sales, month, year)

    if request.args.get("download") == "json":
        return Response(json.dumps(payload, indent=2), mimetype="application/json", headers={"Content-Disposition": f"attachment; filename=gstr1-{year}-{month:02d}.json"})
    if request.args.get("download") == "csv":
        return Response(gstr1_csv(preview), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=gstr1-{year}-{month:02d}.csv"})
    return render_template("reports/gstr1.html", title="GSTR-1", month=month, year=year, payload=payload, preview=preview)


@bp.route("/abc-analysis")
@login_required
def abc_analysis():
    since = date.today() - timedelta(days=90)
    data = db.session.query(Product, func.coalesce(func.sum(SaleItem.line_total), 0).label("revenue")).outerjoin(SaleItem, SaleItem.product_id == Product.id).outerjoin(Sale, Sale.id == SaleItem.sale_id).filter((Sale.invoice_date >= since) | (Sale.id.is_(None))).group_by(Product.id).all()
    total = sum(float(revenue or 0) for _, revenue in data)
    rows = []
    cumulative = 0
    for product, revenue in sorted(data, key=lambda row: float(row[1] or 0), reverse=True):
        revenue = float(revenue or 0)
        pct = (revenue / total * 100) if total else 0
        cumulative += pct
        grade = "A" if cumulative <= 80 else ("B" if cumulative <= 95 else "C")
        rows.append({"sku": product.sku, "name": product.name, "revenue": revenue, "pct": pct, "cumulative": cumulative, "grade": grade})
    if request.args.get("export") == "xlsx":
        return excel_response("abc-analysis.xlsx", "ABC", ["SKU", "Name", "Revenue", "Revenue %", "Cumulative %", "Grade"], [[r["sku"], r["name"], r["revenue"], r["pct"], r["cumulative"], r["grade"]] for r in rows])
    return render_template("reports/abc_analysis.html", title="ABC Analysis", rows=rows)


@bp.route("/dead-stock")
@login_required
def dead_stock():
    days = int(request.args.get("days") or 90)
    min_value = float(request.args.get("min_value") or 0)
    since = date.today() - timedelta(days=days)
    last_sales = dict(db.session.query(SaleItem.product_id, func.max(Sale.invoice_date)).join(Sale).group_by(SaleItem.product_id).all())
    products = []
    for product in Product.query.filter(Product.current_stock > 0).order_by(Product.name).all():
        last = last_sales.get(product.id)
        stock_value = product.stock_value
        if (not last or last < since) and stock_value >= min_value:
            products.append({"product": product, "stock_value": stock_value, "last_sale": last, "days_since": (date.today() - last).days if last else None})
    if request.args.get("export") == "xlsx":
        return excel_response("dead-stock.xlsx", "Dead Stock", ["SKU", "Name", "Stock", "Value", "Last Sale", "Days Since"], [[r["product"].sku, r["product"].name, r["product"].current_stock, r["stock_value"], r["last_sale"], r["days_since"] or "Never"] for r in products])
    return render_template("reports/dead_stock.html", title="Dead Stock", rows=products, days=days, min_value=min_value)


@bp.route("/stock-health")
@login_required
def stock_health_dashboard():
    alert_until = date.today() + timedelta(days=30)
    low = Product.query.filter(Product.min_stock > 0, Product.current_stock <= Product.min_stock).all()
    overstock = Product.query.filter(Product.max_stock > 0, Product.current_stock > Product.max_stock * 2).all()
    negative = Product.query.filter(Product.current_stock < 0).all()
    near_expiry = ProductBatch.query.filter(ProductBatch.expiry_date.isnot(None), ProductBatch.expiry_date <= alert_until).all()
    dead = _dead_stock_products(90)
    return render_template("reports/stock_health_dashboard.html", title="Stock Health", low=low, overstock=overstock, negative=negative, near_expiry=near_expiry, dead=dead)


@bp.route("/sales-velocity")
@login_required
def sales_velocity():
    since = date.today() - timedelta(days=90)
    sold = dict(db.session.query(SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0)).join(Sale).filter(Sale.invoice_date >= since).group_by(SaleItem.product_id).all())
    rows = []
    for product in Product.query.order_by(Product.name):
        units = float(sold.get(product.id) or 0)
        avg_daily = units / 90
        stock = float(product.current_stock or 0)
        days_left = stock / avg_daily if avg_daily else None
        rows.append({"product": product, "daily": avg_daily, "weekly": avg_daily * 7, "monthly": avg_daily * 30, "days_left": days_left})
    if request.args.get("export") == "xlsx":
        return excel_response("sales-velocity.xlsx", "Velocity", ["SKU", "Name", "Daily", "Weekly", "Monthly", "Days Left"], [[r["product"].sku, r["product"].name, r["daily"], r["weekly"], r["monthly"], r["days_left"] or ""] for r in rows])
    return render_template("reports/sales_velocity.html", title="Sales Velocity", rows=rows)


def build_gstr1_payload(sales, month, year):
    b2b_map = {}
    b2c_summary = defaultdict(lambda: {"txval": 0, "iamt": 0, "camt": 0, "samt": 0, "csamt": 0, "val": 0})
    hsn_map = defaultdict(lambda: {"desc": "", "uqc": "NOS", "qty": 0, "val": 0, "txval": 0, "iamt": 0, "camt": 0, "samt": 0, "csamt": 0})
    preview = []

    for sale in sales:
        gstin = (sale.customer.gst_number or "").strip()
        pos = sale.customer.state or "NA"
        invoice_items = []
        for idx, item in enumerate(sale.items, start=1):
            gross = float(item.quantity or 0) * float(item.rate or 0)
            txval = gross - float(getattr(item, "discount_amount", 0) or 0)
            tax = float(item.tax_amount or 0)
            camt = round(tax / 2, 2)
            samt = round(tax - camt, 2)
            invoice_items.append({"num": idx, "itm_det": {"txval": round(txval, 2), "rt": float(item.tax_rate or 0), "iamt": 0, "camt": camt, "samt": samt, "csamt": 0}})
            hsn = item.product.hsn_code or "NA"
            hsn_map[hsn]["desc"] = item.product.name
            hsn_map[hsn]["uqc"] = item.product.unit.short_name if item.product.unit else "NOS"
            hsn_map[hsn]["qty"] += float(item.quantity or 0)
            hsn_map[hsn]["val"] += float(item.line_total or 0)
            hsn_map[hsn]["txval"] += txval
            hsn_map[hsn]["camt"] += camt
            hsn_map[hsn]["samt"] += samt
            preview.append({"invoice_no": sale.invoice_no, "date": sale.invoice_date, "customer": sale.customer.name, "gstin": gstin, "hsn": hsn, "taxable": txval, "tax": tax, "total": float(item.line_total or 0)})
        if gstin:
            b2b_map.setdefault(gstin, {"ctin": gstin, "gstin": gstin, "inv": []})["inv"].append({"inum": sale.invoice_no, "idt": sale.invoice_date.strftime("%d-%m-%Y"), "inv_no": sale.invoice_no, "inv_dt": sale.invoice_date.strftime("%d-%m-%Y"), "val": float(sale.grand_total or 0), "pos": pos, "rchrg": "N", "inv_typ": "R", "itms": invoice_items})
        else:
            key = (pos, "OE")
            b2c_summary[key]["val"] += float(sale.grand_total or 0)
            for invoice_item in invoice_items:
                details = invoice_item["itm_det"]
                b2c_summary[key]["txval"] += details["txval"]
                b2c_summary[key]["camt"] += details["camt"]
                b2c_summary[key]["samt"] += details["samt"]

    b2cs = [{"sply_ty": supply_type, "pos": pos, "typ": "OE", **round_money(values)} for (pos, supply_type), values in b2c_summary.items()]
    hsn_data = [{"num": idx, "hsn_sc": hsn, **round_money(values)} for idx, (hsn, values) in enumerate(sorted(hsn_map.items()), start=1)]
    payload = {"gstin": "", "fp": f"{month:02d}{year}", "version": "GST3.2.1", "hash": "hash", "b2b": list(b2b_map.values()), "b2cs": b2cs, "hsn": {"data": hsn_data}}
    credit_notes = CreditNote.query.filter(extract("month", CreditNote.cn_date) == month, extract("year", CreditNote.cn_date) == year, CreditNote.status == "Issued").all()
    payload["cdnr"] = [{"ctin": cn.customer.gst_number, "nt": [{"nt_num": cn.cn_no, "nt_dt": cn.cn_date.strftime("%d-%m-%Y"), "ntty": "C", "val": float(cn.grand_total or 0), "itms": [{"num": idx, "itm_det": {"txval": float(item.line_total or 0) - float(item.tax_amount or 0), "rt": float(item.tax_rate or 0), "iamt": 0, "camt": round(float(item.tax_amount or 0) / 2, 2), "samt": round(float(item.tax_amount or 0) / 2, 2), "csamt": 0}} for idx, item in enumerate(cn.items, start=1)]}]} for cn in credit_notes if cn.customer.gst_number]
    return payload, preview


def round_money(row):
    return {key: round(value, 2) if isinstance(value, float) else value for key, value in row.items()}


def gstr1_csv(rows):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Invoice No", "Date", "Customer", "GSTIN", "HSN", "Taxable", "Tax", "Total"])
    for row in rows:
        writer.writerow([row["invoice_no"], row["date"], row["customer"], row["gstin"], row["hsn"], f"{row['taxable']:.2f}", f"{row['tax']:.2f}", f"{row['total']:.2f}"])
    return output.getvalue()


def excel_response(filename, sheet_name, headers, rows):
    output = export_to_excel(headers, rows, sheet_name)
    return send_file(output, mimetype=XLSX_MIMETYPE, as_attachment=True, download_name=filename)


def aging_excel(filename, sheet_name, rows):
    headers = ["Party", "Reference", "Due Date", "Days", "Current", "1-30", "31-60", "61-90", "90+", "Total"]
    data = [[r["party"], r["reference_no"], r["due_date"], r["days"], r["current"], r["days_1_30"], r["days_31_60"], r["days_61_90"], r["over_90"], r["amount"]] for r in rows]
    return excel_response(filename, sheet_name, headers, data)


def stock_health_excel(filename, sheet_name, products):
    rows = [[p.sku, p.name, p.warehouse.name if p.warehouse else "", p.rack_bin or "", p.current_stock, p.min_stock, p.reorder_level, (p.max_stock or p.reorder_level or p.min_stock or 0) - (p.current_stock or 0)] for p in products]
    return excel_response(filename, sheet_name, ["SKU", "Product", "Warehouse", "Rack/Bin", "Current", "Minimum", "Reorder", "Suggested Qty"], rows)


def trial_balance_rows():
    rows = []
    total_debit = total_credit = 0
    for account in ChartOfAccounts.query.join(AccountGroup).order_by(AccountGroup.type, ChartOfAccounts.account_code).all():
        balance = float(account.current_balance or 0)
        debit = balance if balance >= 0 else 0
        credit = abs(balance) if balance < 0 else 0
        rows.append({"code": account.account_code, "name": account.account_name, "group": account.group.name, "type": account.group.type, "debit": debit, "credit": credit})
        total_debit += debit
        total_credit += credit
    return rows, total_debit, total_credit


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


def _dead_stock_products(days):
    since = date.today() - timedelta(days=days)
    last_sales = dict(db.session.query(SaleItem.product_id, func.max(Sale.invoice_date)).join(Sale).group_by(SaleItem.product_id).all())
    products = []
    for product in Product.query.filter(Product.current_stock > 0).all():
        last = last_sales.get(product.id)
        if not last or last < since:
            products.append(product)
    return products


def _group_account_balances(types):
    sections = []
    for group_type in types:
        accounts = ChartOfAccounts.query.join(AccountGroup).filter(AccountGroup.type == group_type).order_by(ChartOfAccounts.account_code).all()
        rows = [{"code": account.account_code, "name": account.account_name, "group": account.group.name, "balance": float(account.current_balance or 0)} for account in accounts]
        sections.append({"type": group_type, "rows": rows, "total": sum(row["balance"] for row in rows)})
    return sections
