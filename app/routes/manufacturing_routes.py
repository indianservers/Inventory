from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import BOMItem, BillOfMaterials, ManufacturingOrder, Product, Unit, Warehouse
from app.services.numbering_service import next_number
from app.services.stock_service import add_inventory_entry

bp = Blueprint("manufacturing", __name__, url_prefix="/manufacturing")


@bp.route("/bom/")
@login_required
def bom_index():
    boms = BillOfMaterials.query.order_by(BillOfMaterials.id.desc()).all()
    return render_template("manufacturing/bom_index.html", title="Bills of Materials", boms=boms)


@bp.route("/bom/create", methods=["GET", "POST"])
@login_required
def bom_create():
    return _bom_form(BillOfMaterials(), "Create BOM")


@bp.route("/bom/<int:id>/edit", methods=["GET", "POST"])
@login_required
def bom_edit(id):
    return _bom_form(BillOfMaterials.query.get_or_404(id), "Edit BOM")


@bp.route("/orders/")
@login_required
def order_index():
    orders = ManufacturingOrder.query.order_by(ManufacturingOrder.id.desc()).all()
    return render_template("manufacturing/order_index.html", title="Manufacturing Orders", orders=orders)


@bp.route("/orders/create", methods=["GET", "POST"])
@login_required
def order_create():
    if request.method == "POST":
        try:
            order = ManufacturingOrder(
                mo_no=request.form.get("mo_no") or next_number("manufacturing_order"),
                bom_id=request.form["bom_id"],
                warehouse_id=request.form["warehouse_id"],
                planned_qty=request.form["planned_qty"],
                produced_qty=request.form.get("produced_qty") or request.form["planned_qty"],
                planned_date=date.fromisoformat(request.form["planned_date"]) if request.form.get("planned_date") else date.today(),
                status=request.form.get("status") or "Draft",
                notes=request.form.get("notes"),
                created_by=current_user.id,
            )
            db.session.add(order)
            db.session.commit()
            flash("Manufacturing order created.", "success")
            return redirect(url_for("manufacturing.order_index"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template(
        "manufacturing/order_form.html",
        title="Create Manufacturing Order",
        order=ManufacturingOrder(mo_no=next_number("manufacturing_order"), planned_date=date.today()),
        boms=BillOfMaterials.query.filter_by(is_active=True).order_by(BillOfMaterials.name).all(),
        warehouses=Warehouse.query.order_by(Warehouse.name).all(),
    )


@bp.route("/orders/<int:id>/complete", methods=["POST"])
@login_required
def order_complete(id):
    order = ManufacturingOrder.query.get_or_404(id)
    try:
        produced_qty = request.form.get("produced_qty") or order.produced_qty or order.planned_qty
        order.produced_qty = produced_qty
        for item in order.bom.items:
            required = float(item.quantity or 0) * float(order.planned_qty or 0) * (1 + float(item.waste_pct or 0) / 100)
            add_inventory_entry(item.component, order.warehouse_id, "Manufacturing Issue", "ManufacturingOrder", order.id, order.mo_no, qty_out=required, rate=item.component.average_cost or item.component.purchase_price or 0)
        finished_rate = order.bom.product.average_cost or order.bom.product.purchase_price or 0
        add_inventory_entry(order.bom.product, order.warehouse_id, "Manufacturing Receipt", "ManufacturingOrder", order.id, order.mo_no, qty_in=produced_qty, rate=finished_rate)
        order.status = "Completed"
        order.completed_date = date.today()
        db.session.commit()
        flash(f"Manufacturing order {order.mo_no} completed.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("manufacturing.order_index"))


def _bom_form(bom, title):
    if request.method == "POST":
        try:
            bom.product_id = request.form["product_id"]
            bom.name = request.form["name"]
            bom.yield_qty = request.form.get("yield_qty") or 1
            bom.version = request.form.get("version") or "1"
            bom.is_active = bool(request.form.get("is_active"))
            bom.notes = request.form.get("notes")
            db.session.add(bom)
            db.session.flush()
            BOMItem.query.filter_by(bom_id=bom.id).delete()
            for component_id, qty, unit_id, waste in zip(request.form.getlist("component_id[]"), request.form.getlist("quantity[]"), request.form.getlist("unit_id[]"), request.form.getlist("waste_pct[]")):
                if component_id:
                    db.session.add(BOMItem(bom_id=bom.id, component_id=component_id, quantity=qty or 0, unit_id=unit_id or None, waste_pct=waste or 0))
            db.session.commit()
            flash("BOM saved.", "success")
            return redirect(url_for("manufacturing.bom_index"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template(
        "manufacturing/bom_form.html",
        title=title,
        bom=bom,
        products=Product.query.order_by(Product.name).all(),
        units=Unit.query.order_by(Unit.name).all(),
    )
