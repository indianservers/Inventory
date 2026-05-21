from datetime import date, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Category, Customer, PaymentReceived, POSSession, Product, Sale, SaleItem, Warehouse
from app.services.accounting_service import post_customer_receipt, post_sale
from app.services.invoice_service import calculate_document, line_totals
from app.services.numbering_service import next_number
from app.services.stock_service import apply_sale_item
from app.utils.helpers import money

bp = Blueprint("pos", __name__, url_prefix="/pos")


@bp.route("/")
@login_required
def index():
    active = current_session()
    if active:
        return redirect(url_for("pos.terminal"))
    return render_template("pos/open_session.html", title="Open POS Session")


@bp.route("/open-session", methods=["POST"])
@login_required
def open_session():
    pos_session = POSSession(session_no=next_number("pos_session"), opened_by=current_user.id, opening_cash=request.form.get("opening_cash") or 0, status="Open")
    db.session.add(pos_session)
    db.session.commit()
    session["pos_session_id"] = pos_session.id
    flash("POS session opened.", "success")
    return redirect(url_for("pos.terminal"))


@bp.route("/terminal")
@login_required
def terminal():
    active = current_session()
    if not active:
        return redirect(url_for("pos.index"))
    walkin = Customer.query.order_by(Customer.id).first()
    warehouse = Warehouse.query.order_by(Warehouse.id).first()
    return render_template("pos/terminal.html", title="POS Terminal", pos_session=active, products=Product.query.filter_by(is_active=True).order_by(Product.name).all(), categories=Category.query.order_by(Category.name).all(), customers=Customer.query.order_by(Customer.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all(), walkin=walkin, warehouse=warehouse)


@bp.route("/sale", methods=["POST"])
@login_required
def sale():
    active = current_session()
    if not active:
        return jsonify({"error": "No open POS session"}), 400
    data = request.get_json(force=True)
    items = []
    for item in data.get("items", []):
        totals = line_totals(item["qty"], item["rate"], item.get("discount", 0), item.get("tax_rate", 0))
        items.append({"product_id": int(item["product_id"]), "quantity": item["qty"], "rate": item["rate"], "discount": item.get("discount", 0), "tax_rate": item.get("tax_rate", 0), **totals})
    if not items:
        return jsonify({"error": "Cart is empty"}), 400
    totals = calculate_document(items, paid=0)
    discount_total = money(data.get("discount_total") or 0)
    totals["discount_total"] = money(totals["discount_total"]) + discount_total
    totals["grand_total"] = money(totals["grand_total"]) - discount_total
    totals["balance_amount"] = 0
    totals["paid_amount"] = totals["grand_total"]
    totals["payment_status"] = "Paid"
    sale = Sale(invoice_no=next_number("sales"), invoice_date=date.today(), customer_id=data.get("customer_id") or Customer.query.first().id, warehouse_id=data.get("warehouse_id") or Warehouse.query.first().id, sale_type="Cash", status="Paid", created_by=current_user.id, issued_at=datetime.utcnow(), **totals)
    db.session.add(sale); db.session.flush()
    for item in items:
        cost = apply_sale_item(item["product_id"], sale.warehouse_id, item["quantity"], sale.id, sale.invoice_no)
        db.session.add(SaleItem(sale_id=sale.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], discount=item["discount"], discount_amount=item["discount_amount"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"], cost_price=cost))
    post_sale(sale, current_user.id)
    mode = data.get("payment_mode") or "Cash"
    receipt = PaymentReceived(receipt_no=next_number("receipt"), receipt_date=date.today(), customer_id=sale.customer_id, amount=sale.grand_total, payment_mode=mode, reference_no=data.get("reference_no"), sale_id=sale.id, created_by=current_user.id)
    db.session.add(receipt); db.session.flush(); post_customer_receipt(receipt, current_user.id)
    cash = money(data.get("cash_tendered") or (sale.grand_total if mode == "Cash" else 0))
    card = money(data.get("card_amount") or (sale.grand_total if mode == "Card" else 0))
    upi = money(data.get("upi_amount") or (sale.grand_total if mode == "UPI" else 0))
    active.total_sales = money(active.total_sales) + money(sale.grand_total)
    active.total_cash = money(active.total_cash) + (money(sale.grand_total) if mode == "Cash" else cash)
    active.total_card = money(active.total_card) + card
    active.total_upi = money(active.total_upi) + upi
    db.session.commit()
    change_due = max(float(cash - money(sale.grand_total)), 0) if mode in ["Cash", "Split"] else 0
    return jsonify({"invoice_no": sale.invoice_no, "grand_total": float(sale.grand_total), "change_due": change_due, "sale_id": sale.id})


@bp.route("/close-session", methods=["POST"])
@login_required
def close_session():
    active = current_session()
    if not active:
        return redirect(url_for("pos.index"))
    active.closing_cash = request.form.get("closing_cash") or 0
    active.closed_at = datetime.utcnow()
    active.status = "Closed"
    session.pop("pos_session_id", None)
    db.session.commit()
    return render_template("pos/z_report.html", title=f"Z Report {active.session_no}", pos_session=active)


@bp.route("/sessions")
@login_required
def sessions():
    return render_template("pos/sessions.html", title="POS Sessions", sessions=POSSession.query.order_by(POSSession.id.desc()).all())


@bp.route("/receipt/<int:id>")
@login_required
def receipt(id):
    sale = Sale.query.get_or_404(id)
    return render_template("pos/receipt.html", title=f"Receipt {sale.invoice_no}", sale=sale)


def current_session():
    pos_id = session.get("pos_session_id")
    if pos_id:
        active = POSSession.query.filter_by(id=pos_id, status="Open").first()
        if active:
            return active
    active = POSSession.query.filter_by(opened_by=current_user.id, status="Open").order_by(POSSession.id.desc()).first()
    if active:
        session["pos_session_id"] = active.id
    return active
