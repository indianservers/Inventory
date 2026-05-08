from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import InventoryLedger, Product, ProductBatch, StockAdjustment, StockAdjustmentItem, StockTransfer, StockTransferItem, Warehouse
from app.services.numbering_service import next_number
from app.services.stock_service import apply_stock_adjustment, apply_stock_transfer

bp = Blueprint("stock", __name__, url_prefix="/stock")


@bp.route("/current")
@login_required
def current():
    return render_template("stock/current.html", title="Current Stock", products=Product.query.order_by(Product.name).all())


@bp.route("/ledger")
@login_required
def ledger():
    return render_template("stock/ledger.html", title="Inventory Ledger", entries=InventoryLedger.query.order_by(InventoryLedger.id.desc()).all())


@bp.route("/adjustments", methods=["GET", "POST"])
@login_required
def adjustments():
    if request.method == "POST":
        adj = StockAdjustment(adjustment_no=request.form.get("adjustment_no") or next_number("stock_adjustment"), adjustment_date=date.fromisoformat(request.form["adjustment_date"]), warehouse_id=request.form["warehouse_id"], reason=request.form.get("reason"), notes=request.form.get("notes"), created_by=current_user.id)
        db.session.add(adj); db.session.flush()
        for pid, qi, qo, rate in zip(request.form.getlist("product_id[]"), request.form.getlist("qty_in[]"), request.form.getlist("qty_out[]"), request.form.getlist("rate[]")):
            if pid:
                db.session.add(StockAdjustmentItem(adjustment_id=adj.id, product_id=pid, qty_in=qi or 0, qty_out=qo or 0, rate=rate or 0))
                apply_stock_adjustment(pid, adj.warehouse_id, qi or 0, qo or 0, rate or 0, adj.id, adj.adjustment_no, adj.reason)
        db.session.commit(); flash("Stock adjusted.", "success")
        return redirect(url_for("stock.ledger"))
    return render_template("stock/adjustment.html", title="Stock Adjustment", products=Product.query.all(), warehouses=Warehouse.query.all(), adjustment_no=next_number("stock_adjustment"), today=date.today())


@bp.route("/transfers")
@login_required
def transfers():
    return render_template("stock/transfers.html", title="Stock Transfers", transfers=StockTransfer.query.order_by(StockTransfer.id.desc()).all())


@bp.route("/batches", methods=["GET", "POST"])
@login_required
def batches():
    if request.method == "POST":
        batch = ProductBatch(
            product_id=request.form["product_id"],
            warehouse_id=request.form.get("warehouse_id") or None,
            batch_no=request.form["batch_no"].strip(),
            serial_no=request.form.get("serial_no"),
            manufacture_date=_date_or_none(request.form.get("manufacture_date")),
            expiry_date=_date_or_none(request.form.get("expiry_date")),
            quantity=request.form.get("quantity") or 0,
            cost_rate=request.form.get("cost_rate") or 0,
            notes=request.form.get("notes"),
        )
        db.session.add(batch)
        db.session.commit()
        flash("Batch/serial record saved.", "success")
        return redirect(url_for("stock.batches"))
    return render_template(
        "stock/batches.html",
        title="Batch, Serial & Expiry",
        batches=ProductBatch.query.order_by(ProductBatch.expiry_date.asc(), ProductBatch.id.desc()).all(),
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

        transfer = StockTransfer(
            transfer_no=request.form.get("transfer_no") or next_number("stock_transfer"),
            transfer_date=date.fromisoformat(request.form["transfer_date"]),
            from_warehouse_id=from_warehouse_id,
            to_warehouse_id=to_warehouse_id,
            notes=request.form.get("notes"),
            status="Completed",
            created_by=current_user.id,
        )
        db.session.add(transfer)
        db.session.flush()
        for product_id, quantity, rate in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]")):
            if product_id and quantity:
                db.session.add(StockTransferItem(transfer_id=transfer.id, product_id=product_id, quantity=quantity, rate=rate or 0))
                apply_stock_transfer(product_id, from_warehouse_id, to_warehouse_id, quantity, rate or 0, transfer.id, transfer.transfer_no, transfer.notes)
        db.session.commit()
        flash("Stock transfer completed.", "success")
        return redirect(url_for("stock.transfers"))

    return render_template(
        "stock/transfer_form.html",
        title="Create Stock Transfer",
        products=Product.query.order_by(Product.name).all(),
        warehouses=Warehouse.query.order_by(Warehouse.name).all(),
        transfer_no=next_number("stock_transfer"),
        today=date.today(),
    )
