from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import GoodsReceiptItem, GoodsReceiptNote, Product, PurchaseOrder, PurchaseOrderItem, Supplier, Warehouse
from app.services.invoice_service import calculate_document, line_totals
from app.services.numbering_service import next_number
from app.services.stock_service import apply_purchase_item

bp = Blueprint("purchase_orders", __name__, url_prefix="")


def parse_po_items():
    items = []
    for product_id, q, r, d, t in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]"), request.form.getlist("discount[]"), request.form.getlist("tax_rate[]")):
        if product_id:
            totals = line_totals(q, r, d or 0, t)
            items.append({"product_id": int(product_id), "quantity": q, "rate": r, "tax_rate": t, **totals})
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
            po = PurchaseOrder(po_no=request.form.get("po_no") or next_number("purchase_order"), po_date=date.fromisoformat(request.form["po_date"]), expected_date=date.fromisoformat(request.form["expected_date"]) if request.form.get("expected_date") else None, supplier_id=request.form["supplier_id"], warehouse_id=request.form["warehouse_id"], notes=request.form.get("notes"), terms=request.form.get("terms"), created_by=current_user.id, subtotal=totals["subtotal"], tax_total=totals["tax_total"], grand_total=totals["grand_total"])
            db.session.add(po); db.session.flush()
            for item in items:
                db.session.add(PurchaseOrderItem(po_id=po.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
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
    po.status = "Sent"
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
        for product_id, po_item_id, expected_qty, received_qty, rate, tax_rate in zip(request.form.getlist("product_id[]"), request.form.getlist("po_item_id[]"), request.form.getlist("expected_qty[]"), request.form.getlist("received_qty[]"), request.form.getlist("rate[]"), request.form.getlist("tax_rate[]")):
            if not product_id or not received_qty or float(received_qty or 0) <= 0:
                continue
            totals = line_totals(received_qty, rate, 0, tax_rate)
            item = GoodsReceiptItem(grn_id=grn.id, product_id=product_id, po_item_id=po_item_id or None, expected_qty=expected_qty or 0, received_qty=received_qty, rate=rate, tax_rate=tax_rate, tax_amount=totals["tax_amount"], line_total=totals["line_total"])
            db.session.add(item)
            apply_purchase_item(product_id, grn.warehouse_id, received_qty, rate, grn.id, grn.grn_no)
            if po_item_id:
                po_item = PurchaseOrderItem.query.get(po_item_id)
                po_item.received_qty = float(po_item.received_qty or 0) + float(received_qty or 0)
        if po:
            total = sum(float(item.quantity or 0) for item in po.items)
            received = sum(float(item.received_qty or 0) for item in po.items)
            po.status = "Received" if received >= total else "Partial"
        db.session.commit(); flash(f"Goods receipt {grn.grn_no} saved and stock updated.", "success")
        return redirect(url_for("purchase_orders.detail", id=po.id) if po else url_for("purchase_orders.index"))
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
        return redirect(request.referrer or url_for("purchase_orders.index"))
