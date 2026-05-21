from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Batch, GoodsReceiptItem, GoodsReceiptNote, Product, Purchase, PurchaseItem, PurchaseOrder, PurchaseOrderItem, SerialNumber, Supplier, Warehouse
from app.services.accounting_service import post_purchase
from app.services.invoice_service import calculate_document, line_totals
from app.services.numbering_service import next_number
from app.services.stock_service import apply_purchase_item

bp = Blueprint("purchase_orders", __name__, url_prefix="")


def parse_po_items():
    items = []
    for product_id, q, r, d, t in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]"), request.form.getlist("discount[]"), request.form.getlist("tax_rate[]")):
        if product_id:
            totals = line_totals(q, r, d or 0, t)
            items.append({"product_id": int(product_id), "quantity": q, "rate": r, "discount": d or 0, "tax_rate": t, **totals})
    if not items:
        raise ValueError("At least one item is required.")
    return items


@bp.route("/purchase-orders/")
@login_required
def index():
    return render_template("purchase_orders/index.html", title="Purchase Orders", orders=PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).all())


@bp.route("/purchase-orders/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        try:
            items = parse_po_items()
            totals = calculate_document(items)
            po = PurchaseOrder(po_no=request.form.get("po_no") or next_number("purchase_order"), po_date=date.fromisoformat(request.form["po_date"]), expected_date=date.fromisoformat(request.form["expected_date"]) if request.form.get("expected_date") else None, supplier_id=request.form["supplier_id"], warehouse_id=request.form["warehouse_id"], notes=request.form.get("notes"), terms=request.form.get("terms"), created_by=current_user.id, subtotal=totals["subtotal"], discount_total=totals["discount_total"], tax_total=totals["tax_total"], grand_total=totals["grand_total"])
            db.session.add(po); db.session.flush()
            for item in items:
                db.session.add(PurchaseOrderItem(po_id=po.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], discount=item.get("discount", 0), discount_amount=item.get("discount_amount", 0), tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
            db.session.commit(); flash("Purchase order saved.", "success")
            return redirect(url_for("purchase_orders.detail", id=po.id))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("purchase_orders/form.html", title="Create Purchase Order", po_no=next_number("purchase_order"), today=date.today(), suppliers=Supplier.query.all(), warehouses=Warehouse.query.all())


@bp.route("/purchase-orders/<int:id>")
@login_required
def detail(id):
    po = PurchaseOrder.query.get_or_404(id)
    return render_template("purchase_orders/detail.html", title=f"PO {po.po_no}", po=po)


@bp.route("/purchase-orders/<int:id>/send", methods=["POST"])
@login_required
def send(id):
    po = PurchaseOrder.query.get_or_404(id)
    po.status = "Issued"
    db.session.commit()
    flash("Purchase order marked as sent.", "success")
    return redirect(url_for("purchase_orders.detail", id=po.id))


@bp.route("/purchase-orders/<int:id>/cancel", methods=["POST"])
@login_required
def cancel(id):
    po = PurchaseOrder.query.get_or_404(id)
    po.status = "Cancelled"
    db.session.commit()
    flash("Purchase order cancelled.", "success")
    return redirect(url_for("purchase_orders.detail", id=po.id))


@bp.route("/purchase-orders/<int:id>/print")
@login_required
def print_po(id):
    po = PurchaseOrder.query.get_or_404(id)
    return render_template("purchase_orders/print.html", title=f"PO {po.po_no}", po=po)


@bp.route("/purchase-orders/<int:id>/convert-bill", methods=["POST"])
@login_required
def convert_bill(id):
    po = PurchaseOrder.query.get_or_404(id)
    try:
        purchase = Purchase(purchase_no=next_number("purchases"), purchase_date=date.today(), supplier_id=po.supplier_id, warehouse_id=po.warehouse_id, due_date=po.expected_date, supplier_invoice_no=request.form.get("supplier_invoice_no"), status="Approved", subtotal=po.subtotal, discount_total=po.discount_total, tax_total=po.tax_total, grand_total=po.grand_total, paid_amount=0, balance_amount=po.grand_total, payment_status="Unpaid", notes=f"Converted from PO {po.po_no}", created_by=current_user.id)
        db.session.add(purchase); db.session.flush()
        for item in po.items:
            db.session.add(PurchaseItem(purchase_id=purchase.id, product_id=item.product_id, quantity=item.quantity, rate=item.rate, discount=item.discount, discount_amount=item.discount_amount, tax_rate=item.tax_rate, tax_amount=item.tax_amount, line_total=item.line_total))
            remaining = max(0, float(item.quantity or 0) - float(item.received_qty or 0))
            if remaining:
                apply_purchase_item(item.product_id, purchase.warehouse_id, remaining, item.rate, purchase.id, purchase.purchase_no)
            item.received_qty = item.quantity
        po.status = "Received"
        post_purchase(purchase, current_user.id)
        db.session.commit()
        flash(f"Purchase bill {purchase.purchase_no} created from PO.", "success")
        return redirect(url_for("purchases.index"))
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
        return redirect(url_for("purchase_orders.detail", id=po.id))


@bp.route("/purchase-orders/<int:id>/grn", methods=["GET", "POST"])
@login_required
def grn_from_po(id):
    po = PurchaseOrder.query.get_or_404(id)
    if request.method == "POST":
        return save_grn(po)
    return render_template("purchase_orders/grn_form.html", title=f"GRN for {po.po_no}", po=po, grn_no=next_number("grn"), today=date.today(), suppliers=Supplier.query.all(), warehouses=Warehouse.query.all(), products=Product.query.order_by(Product.name).all())


@bp.route("/grn/create", methods=["GET", "POST"])
@login_required
def grn_create():
    if request.method == "POST":
        return save_grn(None)
    return render_template("purchase_orders/grn_form.html", title="Direct Goods Receipt", po=None, grn_no=next_number("grn"), today=date.today(), suppliers=Supplier.query.all(), warehouses=Warehouse.query.all(), products=Product.query.order_by(Product.name).all())


def save_grn(po):
    try:
        grn = GoodsReceiptNote(grn_no=request.form.get("grn_no") or next_number("grn"), grn_date=date.fromisoformat(request.form["grn_date"]), po_id=po.id if po else None, supplier_id=request.form.get("supplier_id") or po.supplier_id, warehouse_id=request.form.get("warehouse_id") or po.warehouse_id, notes=request.form.get("notes"), created_by=current_user.id)
        db.session.add(grn); db.session.flush()
        for index, (product_id, po_item_id, expected_qty, received_qty, rate, tax_rate) in enumerate(zip(request.form.getlist("product_id[]"), request.form.getlist("po_item_id[]"), request.form.getlist("expected_qty[]"), request.form.getlist("received_qty[]"), request.form.getlist("rate[]"), request.form.getlist("tax_rate[]"))):
            if not product_id or not received_qty or float(received_qty or 0) <= 0:
                continue
            totals = line_totals(received_qty, rate, 0, tax_rate)
            item = GoodsReceiptItem(grn_id=grn.id, product_id=product_id, po_item_id=po_item_id or None, expected_qty=expected_qty or 0, received_qty=received_qty, rate=rate, tax_rate=tax_rate, tax_amount=totals["tax_amount"], line_total=totals["line_total"])
            db.session.add(item)
            apply_purchase_item(product_id, grn.warehouse_id, received_qty, rate, grn.id, grn.grn_no)
            capture_grn_tracking(index, product_id, grn.warehouse_id, received_qty, rate, grn.id, grn.grn_no)
            if po_item_id:
                po_item = PurchaseOrderItem.query.get(po_item_id)
                po_item.received_qty = float(po_item.received_qty or 0) + float(received_qty or 0)
        if po:
            total = sum(float(item.quantity or 0) for item in po.items)
            received = sum(float(item.received_qty or 0) for item in po.items)
            po.status = "Received" if received >= total else "Partially Received"
        db.session.commit(); flash(f"Goods receipt {grn.grn_no} saved and stock updated.", "success")
        return redirect(url_for("purchase_orders.detail", id=po.id) if po else url_for("purchase_orders.index"))
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
        return redirect(request.referrer or url_for("purchase_orders.index"))


def capture_grn_tracking(index, product_id, warehouse_id, quantity, rate, grn_id, grn_no):
    batch_no = request.form.getlist("batch_no[]")[index] if index < len(request.form.getlist("batch_no[]")) else ""
    mfg = request.form.getlist("manufacture_date[]")[index] if index < len(request.form.getlist("manufacture_date[]")) else ""
    exp = request.form.getlist("expiry_date[]")[index] if index < len(request.form.getlist("expiry_date[]")) else ""
    if batch_no:
        batch = Batch.query.filter_by(product_id=product_id, warehouse_id=warehouse_id, batch_no=batch_no).first()
        if not batch:
            batch = Batch(product_id=product_id, warehouse_id=warehouse_id, batch_no=batch_no, manufacture_date=date.fromisoformat(mfg) if mfg else None, expiry_date=date.fromisoformat(exp) if exp else None, purchase_reference=grn_no, cost=rate or 0, quantity=0)
            db.session.add(batch)
        batch.quantity = float(batch.quantity or 0) + float(quantity or 0)
    serials = request.form.getlist("serial_numbers[]")[index] if index < len(request.form.getlist("serial_numbers[]")) else ""
    for serial in [s.strip() for s in serials.replace("\n", ",").split(",") if s.strip()]:
        if not SerialNumber.query.filter_by(serial_no=serial).first():
            db.session.add(SerialNumber(product_id=product_id, warehouse_id=warehouse_id, serial_no=serial, status="Available"))
