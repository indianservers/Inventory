from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Branch, PriceList, PriceListItem, Product

bp = Blueprint("price_lists", __name__, url_prefix="/price-lists")


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        pl = PriceList(name=request.form["name"], description=request.form.get("description"), discount_pct=request.form.get("discount_pct") or 0, price_type=request.form.get("price_type") or "Retail", customer_group=request.form.get("customer_group"), branch_id=request.form.get("branch_id") or None, currency=request.form.get("currency") or "INR", valid_from=_date_or_none(request.form.get("valid_from")), valid_to=_date_or_none(request.form.get("valid_to")), is_default=bool(request.form.get("is_default")), status=True)
        db.session.add(pl); db.session.commit(); flash("Price list saved.", "success")
        return redirect(url_for("price_lists.edit", id=pl.id))
    return render_template("price_lists/index.html", title="Price Lists", price_lists=PriceList.query.order_by(PriceList.id.desc()).all(), branches=Branch.query.order_by(Branch.name).all(), price_types=PRICE_TYPES)


@bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit(id):
    pl = PriceList.query.get_or_404(id)
    if request.method == "POST":
        pl.name = request.form["name"]; pl.description = request.form.get("description"); pl.discount_pct = request.form.get("discount_pct") or 0; pl.price_type = request.form.get("price_type") or "Retail"; pl.customer_group = request.form.get("customer_group"); pl.branch_id = request.form.get("branch_id") or None; pl.currency = request.form.get("currency") or "INR"; pl.valid_from = _date_or_none(request.form.get("valid_from")); pl.valid_to = _date_or_none(request.form.get("valid_to")); pl.is_default = bool(request.form.get("is_default")); pl.status = bool(request.form.get("status"))
        db.session.commit(); flash("Price list updated.", "success")
        return redirect(url_for("price_lists.edit", id=pl.id))
    return render_template("price_lists/edit.html", title=f"Edit {pl.name}", price_list=pl, products=Product.query.order_by(Product.name).all(), branches=Branch.query.order_by(Branch.name).all(), price_types=PRICE_TYPES)


@bp.route("/<int:id>/items", methods=["POST"])
@login_required
def items(id):
    pl = PriceList.query.get_or_404(id)
    product_id = request.form.get("product_id")
    if request.form.get("delete_id"):
        PriceListItem.query.filter_by(id=request.form["delete_id"], price_list_id=pl.id).delete()
    elif product_id:
        item = PriceListItem.query.filter_by(price_list_id=pl.id, product_id=product_id, min_qty=request.form.get("min_qty") or 1).first() or PriceListItem(price_list_id=pl.id, product_id=product_id, min_qty=request.form.get("min_qty") or 1)
        item.sales_price = request.form["sales_price"]
        db.session.add(item)
    db.session.commit()
    return redirect(url_for("price_lists.edit", id=pl.id))


def _date_or_none(value):
    return date.fromisoformat(value) if value else None


PRICE_TYPES = ["Retail", "Wholesale", "Customer Group", "Branch", "Discount"]
