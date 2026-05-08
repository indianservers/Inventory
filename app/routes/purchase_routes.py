from datetime import date

from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem, Supplier, SupplierLedger, Warehouse
from app.services.accounting_service import post_purchase
from app.services.invoice_service import calculate_document, line_totals
from app.services.numbering_service import next_number
from app.services.stock_service import apply_purchase_item, apply_purchase_return_item
from app.utils.pdf_generator import render_pdf

bp = Blueprint("purchases", __name__, url_prefix="/purchases")


def parse_items():
    items = []
    for product_id, q, r, d, t in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]"), request.form.getlist("discount[]"), request.form.getlist("tax_rate[]")):
        if not product_id:
            continue
        totals = line_totals(q, r, d, t)
        items.append({"product_id": int(product_id), "quantity": q, "rate": r, "discount": d, "tax_rate": t, **totals})
    if not items:
        raise ValueError("At least one item is required.")
    return items


def parse_return_items():
    items = []
    for product_id, q, r, t in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]"), request.form.getlist("tax_rate[]")):
        if not product_id:
            continue
        totals = line_totals(q, r, 0, t)
        items.append({"product_id": int(product_id), "quantity": q, "rate": r, "tax_rate": t, **totals})
    if not items:
        raise ValueError("At least one item is required.")
    return items


@bp.route("/")
@login_required
def index():
    return render_template("purchases/index.html", title="Purchase Invoices", purchases=Purchase.query.order_by(Purchase.id.desc()).all())


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        try:
            items = parse_items()
            totals = calculate_document(items, shipping=request.form.get("shipping_charges"), other=request.form.get("other_charges"), paid=request.form.get("paid_amount"))
            purchase = Purchase(purchase_no=request.form.get("purchase_no") or next_number("purchases"), purchase_date=date.fromisoformat(request.form["purchase_date"]), supplier_id=request.form["supplier_id"], warehouse_id=request.form["warehouse_id"], supplier_invoice_no=request.form.get("supplier_invoice_no"), supplier_invoice_date=date.fromisoformat(request.form["supplier_invoice_date"]) if request.form.get("supplier_invoice_date") else None, notes=request.form.get("notes"), created_by=current_user.id, **totals)
            db.session.add(purchase); db.session.flush()
            for item in items:
                db.session.add(PurchaseItem(purchase_id=purchase.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], discount=item["discount"], discount_amount=item["discount_amount"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
                apply_purchase_item(item["product_id"], purchase.warehouse_id, item["quantity"], item["rate"], purchase.id, purchase.purchase_no)
            post_purchase(purchase, current_user.id)
            db.session.commit()
            flash("Purchase saved and stock updated.", "success")
            return redirect(url_for("purchases.index"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("purchases/form.html", title="Create Purchase", purchase=None, suppliers=Supplier.query.all(), warehouses=Warehouse.query.all(), today=date.today(), purchase_no=next_number("purchases"))


@bp.route("/<int:id>/print")
@login_required
def print_purchase(id):
    purchase = Purchase.query.get_or_404(id)
    return render_template("purchases/print.html", title=f"Purchase {purchase.purchase_no}", purchase=purchase)


@bp.route("/<int:id>/pdf")
@login_required
def purchase_pdf(id):
    purchase = Purchase.query.get_or_404(id)
    pdf = render_pdf("purchases/print.html", purchase=purchase, title=f"Purchase {purchase.purchase_no}")
    return send_file(pdf, mimetype="application/pdf", download_name=f"{purchase.purchase_no}.pdf")


@bp.route("/returns")
@login_required
def returns():
    return render_template("purchases/returns.html", title="Purchase Returns", items=PurchaseReturn.query.order_by(PurchaseReturn.id.desc()).all())


@bp.route("/returns/create", methods=["GET", "POST"])
@login_required
def return_create():
    if request.method == "POST":
        try:
            items = parse_return_items()
            totals = calculate_document(items)
            ret = PurchaseReturn(return_no=request.form.get("return_no") or next_number("purchase_return"), return_date=date.fromisoformat(request.form["return_date"]), purchase_id=request.form.get("purchase_id") or None, supplier_id=request.form["supplier_id"], warehouse_id=request.form["warehouse_id"], reason=request.form.get("reason"), refund_mode=request.form.get("refund_mode") or "Debit Note", notes=request.form.get("notes"), created_by=current_user.id, subtotal=totals["subtotal"], tax_total=totals["tax_total"], grand_total=totals["grand_total"])
            db.session.add(ret); db.session.flush()
            supplier = Supplier.query.get(ret.supplier_id)
            balance = supplier.outstanding if supplier else 0
            db.session.add(SupplierLedger(date=ret.return_date, supplier_id=ret.supplier_id, reference_type="PurchaseReturn", reference_id=ret.id, reference_no=ret.return_no, debit=ret.grand_total, credit=0, balance=balance - float(ret.grand_total or 0), narration="Purchase return debit note"))
            for item in items:
                db.session.add(PurchaseReturnItem(purchase_return_id=ret.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
                apply_purchase_return_item(item["product_id"], ret.warehouse_id, item["quantity"], item["rate"], ret.id, ret.return_no)
            db.session.commit(); flash("Purchase return saved and stock updated.", "success")
            return redirect(url_for("purchases.returns"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("purchases/return_form.html", title="Create Purchase Return", suppliers=Supplier.query.all(), warehouses=Warehouse.query.all(), purchases=Purchase.query.order_by(Purchase.id.desc()).all(), today=date.today(), return_no=next_number("purchase_return"))
