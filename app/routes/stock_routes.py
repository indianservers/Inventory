from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Batch, CompositeItem, CompositeItemComponent, InventoryLedger, Product, ProductBatch, PurchaseOrder, PurchaseOrderItem, RepackingItem, RepackingTransaction, SerialNumber, StockAdjustment, StockAdjustmentItem, StockOpening, StockTransfer, StockTransferItem, Supplier, Warehouse
from app.services.numbering_service import next_number
from app.services.audit_service import record_audit
from app.services.stock_service import apply_repacking_line, apply_stock_adjustment, apply_stock_opening, apply_stock_transfer, apply_stock_transfer_in, apply_stock_transfer_out

bp = Blueprint("stock", __name__, url_prefix="/stock")


@bp.route("/current")
@login_required
def current():
    return render_template("stock/current.html", title="Current Stock", products=Product.query.order_by(Product.name).all())


@bp.route("/ledger")
@login_required
def ledger():
    return render_template("stock/ledger.html", title="Inventory Ledger", entries=InventoryLedger.query.order_by(InventoryLedger.id.desc()).all())


@bp.route("/reorder-suggestions", methods=["GET", "POST"])
@login_required
def reorder_suggestions():
    products = Product.query.filter(Product.track_inventory.is_(True), Product.current_stock <= Product.reorder_level).order_by(Product.name).all()
    if request.method == "POST":
        supplier_id = request.form.get("supplier_id")
        selected = {int(pid) for pid in request.form.getlist("product_id[]")}
        supplier = Supplier.query.get_or_404(supplier_id)
        po = PurchaseOrder(po_no=next_number("purchase_order"), po_date=date.today(), supplier_id=supplier.id, warehouse_id=request.form.get("warehouse_id") or (Warehouse.query.first().id if Warehouse.query.first() else None), status="Draft", created_by=current_user.id)
        db.session.add(po); db.session.flush()
        subtotal = tax_total = grand_total = 0
        for product in products:
            if product.id not in selected or product.preferred_supplier_id != supplier.id:
                continue
            qty = max(float(product.max_stock or product.reorder_level or 0) - float(product.current_stock or 0), float(product.reorder_level or 0))
            rate = float(product.purchase_price or product.average_cost or 0)
            line_total = qty * rate
            db.session.add(PurchaseOrderItem(po_id=po.id, product_id=product.id, quantity=qty, rate=rate, tax_rate=0, tax_amount=0, line_total=line_total))
            subtotal += line_total; grand_total += line_total
        po.subtotal = subtotal; po.tax_total = tax_total; po.grand_total = grand_total
        record_audit("Create", "PurchaseOrder", po.id, new_data={"source": "reorder_suggestions", "po_no": po.po_no})
        db.session.commit()
        flash(f"Purchase Order {po.po_no} created from reorder suggestions.", "success")
        return redirect(url_for("purchase_orders.detail", id=po.id))
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("stock/reorder_suggestions.html", title="Reorder Suggestions", products=products, suppliers=suppliers, warehouses=Warehouse.query.order_by(Warehouse.name).all())


@bp.route("/adjustments", methods=["GET", "POST"])
@login_required
def adjustments():
    if request.method == "POST":
        adj = StockAdjustment(adjustment_no=request.form.get("adjustment_no") or next_number("stock_adjustment"), adjustment_date=date.fromisoformat(request.form["adjustment_date"]), warehouse_id=request.form["warehouse_id"], adjustment_type=request.form.get("adjustment_type") or "Other", reason=request.form.get("reason"), notes=request.form.get("notes"), created_by=current_user.id)
        db.session.add(adj); db.session.flush()
        for pid, qi, qo, rate in zip(request.form.getlist("product_id[]"), request.form.getlist("qty_in[]"), request.form.getlist("qty_out[]"), request.form.getlist("rate[]")):
            if pid:
                db.session.add(StockAdjustmentItem(adjustment_id=adj.id, product_id=pid, qty_in=qi or 0, qty_out=qo or 0, rate=rate or 0))
                apply_stock_adjustment(pid, adj.warehouse_id, qi or 0, qo or 0, rate or 0, adj.id, adj.adjustment_no, adj.reason)
        record_audit("Stock Adjustment", "StockAdjustment", adj.id, new_data={"adjustment_no": adj.adjustment_no, "warehouse_id": adj.warehouse_id})
        db.session.commit(); flash("Stock adjusted.", "success")
        return redirect(url_for("stock.ledger"))
    return render_template("stock/adjustment.html", title="Stock Adjustment", products=Product.query.all(), warehouses=Warehouse.query.all(), adjustment_no=next_number("stock_adjustment"), today=date.today(), adjustment_types=ADJUSTMENT_TYPES)


@bp.route("/opening-stock", methods=["GET", "POST"])
@login_required
def opening_stock():
    if request.method == "POST":
        opening = StockOpening(
            opening_no=request.form.get("opening_no") or next_number("stock_opening"),
            opening_date=date.fromisoformat(request.form["opening_date"]),
            product_id=request.form["product_id"],
            warehouse_id=request.form["warehouse_id"],
            quantity=request.form["quantity"],
            rate=request.form.get("rate") or 0,
            value=float(request.form["quantity"] or 0) * float(request.form.get("rate") or 0),
            notes=request.form.get("notes"),
            created_by=current_user.id,
        )
        db.session.add(opening); db.session.flush()
        apply_stock_opening(opening.product_id, opening.warehouse_id, opening.quantity, opening.rate, opening.id, opening.opening_no, opening.notes)
        record_audit("Create", "StockOpening", opening.id, new_data={"opening_no": opening.opening_no})
        db.session.commit()
        flash("Opening stock posted to inventory ledger.", "success")
        return redirect(url_for("stock.opening_stock"))
    return render_template("stock/opening_stock.html", title="Opening Stock", openings=StockOpening.query.order_by(StockOpening.id.desc()).all(), products=Product.query.order_by(Product.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all(), opening_no=next_number("stock_opening"), today=date.today())


@bp.route("/transfers")
@login_required
def transfers():
    return render_template("stock/transfers.html", title="Stock Transfers", transfers=StockTransfer.query.order_by(StockTransfer.id.desc()).all())


@bp.route("/batches", methods=["GET", "POST"])
@login_required
def batches():
    if request.method == "POST":
        batch = Batch(
            product_id=request.form["product_id"],
            warehouse_id=request.form.get("warehouse_id"),
            batch_no=request.form["batch_no"].strip(),
            manufacture_date=_date_or_none(request.form.get("manufacture_date")),
            expiry_date=_date_or_none(request.form.get("expiry_date")),
            purchase_reference=request.form.get("purchase_reference"),
            quantity=request.form.get("quantity") or 0,
            cost=request.form.get("cost_rate") or 0,
        )
        db.session.add(batch)
        db.session.commit()
        flash("Batch record saved.", "success")
        return redirect(url_for("stock.batches"))
    return render_template(
        "stock/batches.html",
        title="Batch, Serial & Expiry",
        batches=Batch.query.order_by(Batch.expiry_date.asc(), Batch.id.desc()).all(),
        products=Product.query.order_by(Product.name).all(),
        warehouses=Warehouse.query.order_by(Warehouse.name).all(),
    )


def _date_or_none(value):
    return date.fromisoformat(value) if value else None


@bp.route("/transfers/create", methods=["GET", "POST"])
@login_required
def transfer_create():
    if request.method == "POST":
        from_warehouse_id = request.form["from_warehouse_id"]
        to_warehouse_id = request.form["to_warehouse_id"]
        if from_warehouse_id == to_warehouse_id:
            flash("From and to warehouses must be different.", "danger")
            return redirect(url_for("stock.transfer_create"))

        status = request.form.get("status") or "Draft"
        transfer = StockTransfer(
            transfer_no=request.form.get("transfer_no") or next_number("stock_transfer"),
            transfer_date=date.fromisoformat(request.form["transfer_date"]),
            from_warehouse_id=from_warehouse_id,
            to_warehouse_id=to_warehouse_id,
            notes=request.form.get("notes"),
            status=status,
            created_by=current_user.id,
        )
        db.session.add(transfer)
        db.session.flush()
        for product_id, quantity, rate in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]")):
            if product_id and quantity:
                db.session.add(StockTransferItem(transfer_id=transfer.id, product_id=product_id, quantity=quantity, rate=rate or 0))
                if status == "Sent":
                    apply_stock_transfer_out(product_id, from_warehouse_id, quantity, rate or 0, transfer.id, transfer.transfer_no, transfer.notes)
                elif status == "Received":
                    apply_stock_transfer(product_id, from_warehouse_id, to_warehouse_id, quantity, rate or 0, transfer.id, transfer.transfer_no, transfer.notes)
        db.session.commit()
        flash("Stock transfer saved.", "success")
        return redirect(url_for("stock.transfers"))

    return render_template(
        "stock/transfer_form.html",
        title="Create Stock Transfer",
        products=Product.query.order_by(Product.name).all(),
        warehouses=Warehouse.query.order_by(Warehouse.name).all(),
        transfer_no=next_number("stock_transfer"),
        today=date.today(),
    )


@bp.route("/transfers/<int:id>/send", methods=["POST"])
@login_required
def transfer_send(id):
    transfer = StockTransfer.query.get_or_404(id)
    if transfer.status != "Draft":
        flash("Only draft transfers can be sent.", "warning")
        return redirect(url_for("stock.transfers"))
    for item in transfer.items:
        apply_stock_transfer_out(item.product_id, transfer.from_warehouse_id, item.quantity, item.rate, transfer.id, transfer.transfer_no, transfer.notes)
    transfer.status = "Sent"
    db.session.commit()
    flash("Transfer sent and source stock reduced.", "success")
    return redirect(url_for("stock.transfers"))


@bp.route("/transfers/<int:id>/receive", methods=["POST"])
@login_required
def transfer_receive(id):
    transfer = StockTransfer.query.get_or_404(id)
    if transfer.status == "Draft":
        for item in transfer.items:
            apply_stock_transfer(item.product_id, transfer.from_warehouse_id, transfer.to_warehouse_id, item.quantity, item.rate, transfer.id, transfer.transfer_no, transfer.notes)
    elif transfer.status == "Sent":
        for item in transfer.items:
            apply_stock_transfer_in(item.product_id, transfer.to_warehouse_id, item.quantity, item.rate, transfer.id, transfer.transfer_no, transfer.notes)
    else:
        flash("Only draft or sent transfers can be received.", "warning")
        return redirect(url_for("stock.transfers"))
    transfer.status = "Received"
    db.session.commit()
    flash("Transfer received and destination stock increased.", "success")
    return redirect(url_for("stock.transfers"))


@bp.route("/transfers/<int:id>/cancel", methods=["POST"])
@login_required
def transfer_cancel(id):
    transfer = StockTransfer.query.get_or_404(id)
    if transfer.status != "Draft":
        flash("Only draft transfers can be cancelled without stock reversal.", "warning")
        return redirect(url_for("stock.transfers"))
    transfer.status = "Cancelled"
    db.session.commit()
    flash("Transfer cancelled.", "success")
    return redirect(url_for("stock.transfers"))


@bp.route("/serial-numbers", methods=["GET", "POST"])
@login_required
def serial_numbers():
    if request.method == "POST":
        serial = SerialNumber(
            product_id=request.form["product_id"],
            warehouse_id=request.form.get("warehouse_id") or None,
            serial_no=request.form["serial_no"].strip(),
            status=request.form.get("status") or "Available",
            notes=request.form.get("notes"),
        )
        db.session.add(serial)
        db.session.commit()
        flash("Serial number saved.", "success")
        return redirect(url_for("stock.serial_numbers"))
    return render_template("stock/serial_numbers.html", title="Serial Numbers", serials=SerialNumber.query.order_by(SerialNumber.id.desc()).all(), products=Product.query.order_by(Product.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all(), statuses=SERIAL_STATUSES)


@bp.route("/composite-items", methods=["GET", "POST"])
@login_required
def composite_items():
    if request.method == "POST":
        composite = CompositeItem(product_id=request.form["product_id"], name=request.form["name"], description=request.form.get("description"), status=bool(request.form.get("status")))
        db.session.add(composite); db.session.flush()
        for component_id, quantity in zip(request.form.getlist("component_product_id[]"), request.form.getlist("component_quantity[]")):
            if component_id and quantity:
                db.session.add(CompositeItemComponent(composite_item_id=composite.id, component_product_id=component_id, quantity=quantity))
        db.session.commit()
        flash("Composite item saved.", "success")
        return redirect(url_for("stock.composite_items"))
    return render_template("stock/composite_items.html", title="Composite Items", composites=CompositeItem.query.order_by(CompositeItem.id.desc()).all(), products=Product.query.order_by(Product.name).all())


@bp.route("/repacking", methods=["GET", "POST"])
@login_required
def repacking():
    if request.method == "POST":
        repack = RepackingTransaction(repack_no=request.form.get("repack_no") or next_number("repacking"), repack_date=date.fromisoformat(request.form["repack_date"]), warehouse_id=request.form["warehouse_id"], notes=request.form.get("notes"), status="Completed", created_by=current_user.id)
        db.session.add(repack); db.session.flush()
        for line_type, product_id, quantity, rate in zip(request.form.getlist("line_type[]"), request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]")):
            if product_id and quantity:
                db.session.add(RepackingItem(repacking_id=repack.id, line_type=line_type, product_id=product_id, quantity=quantity, rate=rate or 0))
                apply_repacking_line(product_id, repack.warehouse_id, line_type, quantity, rate or 0, repack.id, repack.repack_no, repack.notes)
        db.session.commit()
        flash("Repacking posted to inventory ledger.", "success")
        return redirect(url_for("stock.repacking"))
    return render_template("stock/repacking.html", title="Item Repacking", transactions=RepackingTransaction.query.order_by(RepackingTransaction.id.desc()).all(), products=Product.query.order_by(Product.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all(), repack_no=next_number("repacking"), today=date.today())


ADJUSTMENT_TYPES = ["Physical count difference", "Damage", "Wastage", "Internal use", "Correction", "Other"]
SERIAL_STATUSES = ["Available", "Sold", "Returned", "Damaged"]
