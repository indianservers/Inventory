import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from io import StringIO
from xml.sax.saxutils import escape

from flask import Blueprint, Response, render_template, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import extract, func

from app.extensions import db
from app.models import AccountGroup, AuditLog, Batch, Branch, Category, ChartOfAccounts, CreditNote, Customer, CustomerLedger, Expense, ITCEntry, InventoryLedger, PaymentMade, PaymentReceived, POSSession, Product, ProductBatch, Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem, Register, Sale, SaleItem, SalesReturn, SalesReturnItem, SerialNumber, Supplier, SupplierLedger, Tax, Warehouse
from app.utils.excel_export import export_to_excel

bp = Blueprint("reports", __name__, url_prefix="/reports")
XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@bp.route("/")
@login_required
def index():
    return render_template("reports/index.html", title="Reports")


@bp.route("/tally-export")
@login_required
def tally_export():
    export_type = request.args.get("type", "sales")
    start = parse_date_arg("start") or date.today().replace(day=1)
    end = parse_date_arg("end") or date.today()
    if request.args.get("download") == "xml":
        xml = build_tally_xml(export_type, start, end)
        db.session.add(AuditLog(user_id=current_user.id, action="Export", module="Tally", new_data=json.dumps({"type": export_type, "start": str(start), "end": str(end)})))
        db.session.commit()
        return Response(xml, mimetype="application/xml", headers={"Content-Disposition": f"attachment; filename=tally-{export_type}-{start}-{end}.xml"})
    return render_template("reports/tally_export.html", title="Tally XML Export", export_type=export_type, start=start, end=end)


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
    query = Product.query.filter(Product.min_stock > 0, Product.current_stock <= Product.min_stock)
    if request.args.get("warehouse_id"):
        query = query.filter(Product.warehouse_id == request.args["warehouse_id"])
    if request.args.get("category_id"):
        query = query.filter(Product.category_id == request.args["category_id"])
    products = query.order_by(Product.name).all()
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
    query = Product.query
    if request.args.get("warehouse_id"):
        query = query.filter(Product.warehouse_id == request.args["warehouse_id"])
    products = query.order_by(Product.name).all()
    total_value = sum(product.stock_value for product in products)
    if request.args.get("export") == "xlsx":
        rows = [[p.sku, p.name, p.warehouse.name if p.warehouse else "", p.current_stock, p.average_cost, p.stock_value] for p in products]
        return excel_response("stock-valuation.xlsx", "Valuation", ["SKU", "Product", "Warehouse", "Qty", "Average Cost", "Stock Value"], rows)
    return render_template("reports/valuation.html", title="Stock Valuation", products=products, total_value=total_value)


@bp.route("/expiry")
@login_required
def expiry_report():
    alert_until = date.today() + timedelta(days=30)
    query = ProductBatch.query.filter(ProductBatch.expiry_date.isnot(None))
    if request.args.get("date_from"):
        query = query.filter(ProductBatch.expiry_date >= date.fromisoformat(request.args["date_from"]))
    if request.args.get("date_to"):
        query = query.filter(ProductBatch.expiry_date <= date.fromisoformat(request.args["date_to"]))
    if not request.args.get("date_to"):
        query = query.filter(ProductBatch.expiry_date <= alert_until)
    if request.args.get("warehouse_id"):
        query = query.filter(ProductBatch.warehouse_id == request.args["warehouse_id"])
    batches = query.order_by(ProductBatch.expiry_date.asc()).all()
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


@bp.route("/gstr3b")
@login_required
def gstr3b_report():
    month = int(request.args.get("month") or date.today().month)
    year = int(request.args.get("year") or date.today().year)
    quarter = request.args.get("quarter")
    if quarter:
        q = int(quarter)
        months = [(q - 1) * 3 + 1, (q - 1) * 3 + 2, (q - 1) * 3 + 3]
    else:
        months = [month]
    sales = Sale.query.filter(extract("year", Sale.invoice_date) == year, extract("month", Sale.invoice_date).in_(months), Sale.status.notin_(["Draft", "Cancelled"])).all()
    purchases = Purchase.query.filter(extract("year", Purchase.purchase_date) == year, extract("month", Purchase.purchase_date).in_(months), Purchase.status != "Cancelled").all()
    itc_entries = ITCEntry.query.filter(extract("year", ITCEntry.invoice_date) == year, extract("month", ITCEntry.invoice_date).in_(months)).all()
    outward = sum(float(s.subtotal or 0) for s in sales)
    outward_tax = sum(float(s.tax_total or 0) for s in sales)
    exempt = sum(float(s.grand_total or 0) for s in sales if float(s.tax_total or 0) == 0)
    inward_reverse_charge = 0
    eligible_itc = sum(float(i.eligible_itc_amount or 0) for i in itc_entries if i.itc_status in {"Eligible", "Claimed"})
    reversed_itc = sum(float(i.eligible_itc_amount or 0) for i in itc_entries if i.itc_status == "Reversed")
    blocked_itc = sum(float(i.blocked_itc_amount or 0) for i in itc_entries)
    net_itc = max(eligible_itc - reversed_itc, 0)
    tax_payable = max(outward_tax - net_itc, 0)
    summary = {
        "outward_taxable_supplies": outward,
        "zero_rated_supplies": 0,
        "exempt_nil_non_gst": exempt,
        "inward_reverse_charge": inward_reverse_charge,
        "eligible_itc": eligible_itc,
        "itc_reversed": reversed_itc,
        "blocked_itc": blocked_itc,
        "net_itc_available": net_itc,
        "tax_payable": outward_tax,
        "tax_paid_itc": min(outward_tax, net_itc),
        "tax_paid_cash": tax_payable,
        "interest_late_fee": 0,
        "purchase_tax_total": sum(float(p.tax_total or 0) for p in purchases),
    }
    if request.args.get("export") == "xlsx":
        return excel_response("gstr3b.xlsx", "GSTR-3B", ["Section", "Amount"], [[k.replace("_", " ").title(), v] for k, v in summary.items()])
    if request.args.get("download") == "json":
        return Response(json.dumps({"year": year, "months": months, "summary": summary}, indent=2), mimetype="application/json", headers={"Content-Disposition": f"attachment; filename=gstr3b-{year}.json"})
    return render_template("reports/gstr3b.html", title="GSTR-3B", month=month, year=year, quarter=quarter, summary=summary)


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


@bp.route("/sales-summary")
@login_required
def sales_summary():
    query = Sale.query.filter(Sale.status.notin_(["Draft", "Cancelled"]))
    query = date_filter(query, Sale.invoice_date)
    if request.args.get("customer_id"):
        query = query.filter(Sale.customer_id == request.args["customer_id"])
    if request.args.get("branch_id"):
        query = query.join(Warehouse).filter(Warehouse.branch_id == request.args["branch_id"])
    rows = [{"Invoice": s.invoice_no, "Date": s.invoice_date, "Customer": s.customer.name, "Branch": s.warehouse.branch.name if s.warehouse and s.warehouse.branch else "", "Total": s.grand_total, "Paid": s.paid_amount, "Balance": s.balance_amount} for s in query.order_by(Sale.invoice_date.desc()).all()]
    return report_response("Sales Summary", rows)


@bp.route("/item-wise-sales")
@login_required
def item_wise_sales():
    query = db.session.query(SaleItem).join(Sale).join(Product)
    query = date_filter(query, Sale.invoice_date)
    if request.args.get("category_id"):
        query = query.filter(Product.category_id == request.args["category_id"])
    if request.args.get("product_id"):
        query = query.filter(SaleItem.product_id == request.args["product_id"])
    rows = [{"Date": i.sale.invoice_date, "Invoice": i.sale.invoice_no, "Product": i.product.name, "Category": i.product.category.name if i.product.category else "", "Qty": i.quantity, "Rate": i.rate, "Tax": i.tax_amount, "Total": i.line_total} for i in query.order_by(Sale.invoice_date.desc()).all()]
    return report_response("Item-wise Sales", rows)


@bp.route("/customer-wise-sales")
@login_required
def customer_wise_sales():
    query = db.session.query(Customer.name, func.coalesce(func.sum(Sale.grand_total), 0), func.count(Sale.id)).join(Sale).filter(Sale.status.notin_(["Draft", "Cancelled"]))
    query = date_filter(query, Sale.invoice_date)
    if request.args.get("customer_id"):
        query = query.filter(Customer.id == request.args["customer_id"])
    rows = [{"Customer": name, "Invoices": count, "Total Sales": total} for name, total, count in query.group_by(Customer.id, Customer.name).all()]
    return report_response("Customer-wise Sales", rows)


@bp.route("/sales-returns")
@login_required
def sales_return_report():
    query = SalesReturn.query
    query = date_filter(query, SalesReturn.return_date)
    if request.args.get("customer_id"):
        query = query.filter(SalesReturn.customer_id == request.args["customer_id"])
    rows = [{"Return No": r.return_no, "Date": r.return_date, "Customer": r.sales_return_customer.name, "Restock": r.restock, "Status": r.status, "Total": r.grand_total} for r in query.order_by(SalesReturn.return_date.desc()).all()]
    return report_response("Sales Return Report", rows)


@bp.route("/payments-received")
@login_required
def payments_received_report():
    query = PaymentReceived.query
    query = date_filter(query, PaymentReceived.receipt_date)
    if request.args.get("payment_mode"):
        query = query.filter(PaymentReceived.payment_mode == request.args["payment_mode"])
    rows = [{"Receipt": p.receipt_no, "Date": p.receipt_date, "Customer": p.customer.name, "Mode": p.payment_mode, "Amount": p.amount, "Unallocated": p.unallocated_amount, "Status": p.status} for p in query.order_by(PaymentReceived.receipt_date.desc()).all()]
    return report_response("Payment Received Report", rows)


@bp.route("/purchase-summary")
@login_required
def purchase_summary():
    query = Purchase.query
    query = date_filter(query, Purchase.purchase_date)
    if request.args.get("vendor_id"):
        query = query.filter(Purchase.supplier_id == request.args["vendor_id"])
    rows = [{"Bill": p.purchase_no, "Date": p.purchase_date, "Vendor": p.supplier.name, "Vendor Bill": p.supplier_invoice_no, "Total": p.grand_total, "Paid": p.paid_amount, "Balance": p.balance_amount, "Status": p.status or p.payment_status} for p in query.order_by(Purchase.purchase_date.desc()).all()]
    return report_response("Purchase Summary", rows)


@bp.route("/vendor-wise-purchase")
@login_required
def vendor_wise_purchase():
    query = db.session.query(Supplier.name, func.coalesce(func.sum(Purchase.grand_total), 0), func.count(Purchase.id)).join(Purchase)
    query = date_filter(query, Purchase.purchase_date)
    if request.args.get("vendor_id"):
        query = query.filter(Supplier.id == request.args["vendor_id"])
    rows = [{"Vendor": name, "Bills": count, "Total Purchases": total} for name, total, count in query.group_by(Supplier.id, Supplier.name).all()]
    return report_response("Vendor-wise Purchase", rows)


@bp.route("/purchase-returns")
@login_required
def purchase_return_report():
    query = PurchaseReturn.query
    query = date_filter(query, PurchaseReturn.return_date)
    if request.args.get("vendor_id"):
        query = query.filter(PurchaseReturn.supplier_id == request.args["vendor_id"])
    rows = [{"Return No": r.return_no, "Date": r.return_date, "Vendor": r.supplier.name if hasattr(r, "supplier") and r.supplier else (r.purchase.supplier.name if r.purchase else ""), "Mode": r.refund_mode, "Total": r.grand_total} for r in query.order_by(PurchaseReturn.return_date.desc()).all()]
    return report_response("Purchase Return Report", rows)


@bp.route("/vendor-payments")
@login_required
def vendor_payment_report():
    query = PaymentMade.query
    query = date_filter(query, PaymentMade.voucher_date)
    if request.args.get("vendor_id"):
        query = query.filter(PaymentMade.supplier_id == request.args["vendor_id"])
    if request.args.get("payment_mode"):
        query = query.filter(PaymentMade.payment_mode == request.args["payment_mode"])
    rows = [{"Voucher": p.voucher_no, "Date": p.voucher_date, "Vendor": p.supplier.name if p.supplier else "", "Mode": p.payment_mode, "Amount": p.amount, "Unallocated": p.unallocated_amount, "Status": p.status} for p in query.order_by(PaymentMade.voucher_date.desc()).all()]
    return report_response("Vendor Payment Report", rows)


@bp.route("/stock-summary")
@login_required
def stock_summary():
    query = Product.query
    if request.args.get("warehouse_id"):
        query = query.filter(Product.warehouse_id == request.args["warehouse_id"])
    if request.args.get("category_id"):
        query = query.filter(Product.category_id == request.args["category_id"])
    if request.args.get("product_id"):
        query = query.filter(Product.id == request.args["product_id"])
    rows = [{"SKU": p.sku, "Product": p.name, "Warehouse": p.warehouse.name if p.warehouse else "", "Category": p.category.name if p.category else "", "Stock": p.current_stock, "Avg Cost": p.average_cost, "Value": p.stock_value} for p in query.order_by(Product.name).all()]
    return report_response("Stock Summary", rows)


@bp.route("/stock-movement")
@login_required
def stock_movement_report():
    query = InventoryLedger.query
    query = date_filter(query, InventoryLedger.date)
    if request.args.get("warehouse_id"):
        query = query.filter(InventoryLedger.warehouse_id == request.args["warehouse_id"])
    if request.args.get("product_id"):
        query = query.filter(InventoryLedger.product_id == request.args["product_id"])
    if request.args.get("transaction_type"):
        query = query.filter(InventoryLedger.movement_type == request.args["transaction_type"])
    rows = [{"Date": r.date, "Product": r.product.name, "Warehouse": r.warehouse.name if r.warehouse else "", "Type": r.movement_type, "Reference": r.reference_no, "In": r.qty_in, "Out": r.qty_out, "Balance": r.balance_qty} for r in query.order_by(InventoryLedger.date.desc(), InventoryLedger.id.desc()).all()]
    return report_response("Stock Movement", rows)


@bp.route("/serial-numbers")
@login_required
def serial_number_report():
    query = SerialNumber.query
    if request.args.get("product_id"):
        query = query.filter(SerialNumber.product_id == request.args["product_id"])
    if request.args.get("status"):
        query = query.filter(SerialNumber.status == request.args["status"])
    rows = [{"Product": s.product.name, "Serial": s.serial_no, "Status": s.status, "Warehouse": s.warehouse.name if s.warehouse else "", "Purchase": s.purchase_id, "Sale": s.sale_id} for s in query.order_by(SerialNumber.serial_no).all()]
    return report_response("Serial Number Report", rows)


@bp.route("/tax-report")
@login_required
def tax_report():
    sales_rows = [{"Date": s.invoice_date, "Type": "Sale", "Reference": s.invoice_no, "Party": s.customer.name, "Tax": s.tax_total, "Total": s.grand_total} for s in date_filter(Sale.query, Sale.invoice_date).filter(Sale.tax_total != 0).all()]
    purchase_rows = [{"Date": p.purchase_date, "Type": "Purchase", "Reference": p.purchase_no, "Party": p.supplier.name, "Tax": p.tax_total, "Total": p.grand_total} for p in date_filter(Purchase.query, Purchase.purchase_date).filter(Purchase.tax_total != 0).all()]
    tx_type = request.args.get("transaction_type")
    rows = sales_rows + purchase_rows
    if tx_type:
        rows = [row for row in rows if row["Type"].lower() == tx_type.lower()]
    return report_response("Tax Report", rows)


@bp.route("/cashier-closing")
@login_required
def cashier_closing_report():
    query = POSSession.query
    if request.args.get("date_from"):
        query = query.filter(POSSession.opened_at >= request.args["date_from"])
    rows = [{"Session": s.session_no, "Opened": s.opened_at, "Closed": s.closed_at, "Cash": s.total_cash, "Card": s.total_card, "UPI": s.total_upi, "Expected": s.expected_closing_cash, "Closing": s.closing_cash, "Difference": s.cash_difference, "Status": s.status} for s in query.order_by(POSSession.id.desc()).all()]
    return report_response("Cashier Closing Report", rows)


@bp.route("/activity-log")
@login_required
def activity_log_report():
    query = AuditLog.query
    if request.args.get("date_from"):
        query = query.filter(AuditLog.created_at >= request.args["date_from"])
    if request.args.get("action"):
        query = query.filter(AuditLog.action == request.args["action"])
    rows = [{"Date": a.created_at, "User": a.user.name if a.user else "", "Action": a.action, "Module": a.module, "Reference": a.record_id, "IP": a.ip_address} for a in query.order_by(AuditLog.id.desc()).all()]
    return report_response("Activity Log Report", rows)


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


def parse_date_arg(name):
    value = request.args.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def build_tally_xml(export_type, start, end):
    vouchers = []
    if export_type == "purchases":
        for purchase in Purchase.query.filter(Purchase.purchase_date >= start, Purchase.purchase_date <= end).order_by(Purchase.purchase_date).all():
            vouchers.append(_tally_voucher("Purchase", purchase.purchase_date, purchase.purchase_no, purchase.supplier.name if purchase.supplier else "Supplier", purchase.grand_total))
    elif export_type == "receipts":
        for receipt in PaymentReceived.query.filter(PaymentReceived.payment_date >= start, PaymentReceived.payment_date <= end).order_by(PaymentReceived.payment_date).all():
            vouchers.append(_tally_voucher("Receipt", receipt.payment_date, receipt.receipt_no, receipt.customer.name if receipt.customer else "Customer", receipt.amount))
    elif export_type == "payments":
        for payment in PaymentMade.query.filter(PaymentMade.payment_date >= start, PaymentMade.payment_date <= end).order_by(PaymentMade.payment_date).all():
            vouchers.append(_tally_voucher("Payment", payment.payment_date, payment.payment_no, payment.supplier.name if payment.supplier else "Supplier", payment.amount))
    elif export_type == "stock_items":
        for product in Product.query.order_by(Product.name).all():
            vouchers.append(f"<STOCKITEM NAME=\"{escape(product.name or '')}\"><BASEUNITS>{escape(product.unit.symbol if product.unit else 'Nos')}</BASEUNITS><OPENINGBALANCE>{float(product.current_stock or 0):.3f}</OPENINGBALANCE><OPENINGVALUE>{float(product.stock_value or 0):.2f}</OPENINGVALUE></STOCKITEM>")
    elif export_type == "customers":
        for customer in Customer.query.order_by(Customer.name).all():
            vouchers.append(f"<LEDGER NAME=\"{escape(customer.name or '')}\"><PARENT>Sundry Debtors</PARENT><GSTIN>{escape(customer.gstin or '')}</GSTIN></LEDGER>")
    elif export_type == "suppliers":
        for supplier in Supplier.query.order_by(Supplier.name).all():
            vouchers.append(f"<LEDGER NAME=\"{escape(supplier.name or '')}\"><PARENT>Sundry Creditors</PARENT><GSTIN>{escape(supplier.gstin or '')}</GSTIN></LEDGER>")
    else:
        for sale in Sale.query.filter(Sale.invoice_date >= start, Sale.invoice_date <= end, Sale.status != "Cancelled").order_by(Sale.invoice_date).all():
            vouchers.append(_tally_voucher("Sales", sale.invoice_date, sale.invoice_no, sale.customer.name if sale.customer else "Customer", sale.grand_total))
    body = "".join(vouchers)
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME></REQUESTDESC><REQUESTDATA>{body}</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"""


def _tally_voucher(voucher_type, txn_date, voucher_no, party, amount):
    amount = float(amount or 0)
    ymd = txn_date.strftime("%Y%m%d") if txn_date else ""
    return (
        f"<TALLYMESSAGE><VOUCHER VCHTYPE=\"{escape(voucher_type)}\" ACTION=\"Create\">"
        f"<DATE>{ymd}</DATE><VOUCHERTYPENAME>{escape(voucher_type)}</VOUCHERTYPENAME>"
        f"<VOUCHERNUMBER>{escape(voucher_no or '')}</VOUCHERNUMBER><PARTYLEDGERNAME>{escape(party or '')}</PARTYLEDGERNAME>"
        f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{escape(party or '')}</LEDGERNAME><AMOUNT>{amount:.2f}</AMOUNT></ALLLEDGERENTRIES.LIST>"
        f"</VOUCHER></TALLYMESSAGE>"
    )


def report_response(title, rows):
    headers = list(rows[0].keys()) if rows else []
    if request.args.get("export") == "xlsx":
        return excel_response(f"{title.lower().replace(' ', '-')}.xlsx", title[:31], headers, [[row.get(header) for header in headers] for row in rows])
    return render_template("reports/custom_table.html", title=title, headers=headers, rows=rows)


def date_filter(query, column):
    if request.args.get("date_from"):
        query = query.filter(column >= date.fromisoformat(request.args["date_from"]))
    if request.args.get("date_to"):
        query = query.filter(column <= date.fromisoformat(request.args["date_to"]))
    return query


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
