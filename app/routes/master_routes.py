from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Brand, Category, Tax, TaxGroup, TaxRate, Unit, Warehouse

bp = Blueprint("masters", __name__, url_prefix="/masters")


def save_category(obj):
    obj.name = request.form["name"]
    obj.parent_id = request.form.get("parent_id") or None
    obj.description = request.form.get("description")
    obj.status = bool(request.form.get("status"))


def save_brand(obj):
    obj.name = request.form["name"]
    obj.description = request.form.get("description")
    obj.status = bool(request.form.get("status"))


def save_unit(obj):
    obj.name = request.form["name"]
    obj.short_name = request.form["short_name"]
    obj.decimal_allowed = bool(request.form.get("decimal_allowed"))
    obj.status = bool(request.form.get("status"))


def save_warehouse(obj):
    obj.name = request.form["name"]
    obj.code = request.form["code"]
    obj.address = request.form.get("address")
    obj.contact_person = request.form.get("contact_person")
    obj.phone = request.form.get("phone")
    obj.email = request.form.get("email")
    obj.status = bool(request.form.get("status"))


def save_tax(obj):
    obj.name = request.form["name"]
    obj.rate = request.form.get("rate") or 0
    obj.tax_type = request.form.get("tax_type") or "GST"
    obj.is_inclusive = bool(request.form.get("is_inclusive"))
    obj.status = bool(request.form.get("status"))


@bp.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    if request.method == "POST":
        obj = Category()
        save_category(obj)
        db.session.add(obj); db.session.commit(); flash("Category saved.", "success")
        return redirect(url_for("masters.categories"))
    return render_template("masters/simple.html", title="Categories", items=Category.query.all(), fields=[("name","Name"),("description","Description")], endpoint="masters.categories", parents=Category.query.all())


@bp.route("/categories/<int:id>/delete")
@login_required
def delete_category(id):
    Category.query.filter_by(id=id).delete(); db.session.commit(); flash("Category deleted.", "success")
    return redirect(url_for("masters.categories"))


@bp.route("/brands", methods=["GET", "POST"])
@login_required
def brands():
    if request.method == "POST":
        obj = Brand(); save_brand(obj); db.session.add(obj); db.session.commit(); flash("Brand saved.", "success")
        return redirect(url_for("masters.brands"))
    return render_template("masters/simple.html", title="Brands", items=Brand.query.all(), fields=[("name","Name"),("description","Description")], endpoint="masters.brands")


@bp.route("/brands/<int:id>/delete")
@login_required
def delete_brand(id):
    Brand.query.filter_by(id=id).delete(); db.session.commit(); flash("Brand deleted.", "success")
    return redirect(url_for("masters.brands"))


@bp.route("/units", methods=["GET", "POST"])
@login_required
def units():
    if request.method == "POST":
        obj = Unit(); save_unit(obj); db.session.add(obj); db.session.commit(); flash("Unit saved.", "success")
        return redirect(url_for("masters.units"))
    return render_template("masters/simple.html", title="Units", items=Unit.query.all(), fields=[("name","Name"),("short_name","Short Name")], endpoint="masters.units")


@bp.route("/units/<int:id>/delete")
@login_required
def delete_unit(id):
    Unit.query.filter_by(id=id).delete(); db.session.commit(); flash("Unit deleted.", "success")
    return redirect(url_for("masters.units"))


@bp.route("/warehouses", methods=["GET", "POST"])
@login_required
def warehouses():
    return redirect(url_for("settings.warehouses"))


@bp.route("/warehouses/<int:id>/delete")
@login_required
def delete_warehouse(id):
    warehouse = Warehouse.query.get_or_404(id)
    warehouse.status = False
    db.session.commit()
    flash("Warehouse deactivated.", "success")
    return redirect(url_for("settings.warehouses"))


@bp.route("/taxes", methods=["GET", "POST"])
@login_required
def taxes():
    if request.method == "POST":
        obj = Tax(); save_tax(obj); db.session.add(obj); db.session.commit(); flash("Tax saved.", "success")
        return redirect(url_for("masters.taxes"))
    return render_template("masters/taxes.html", title="Tax Settings", items=Tax.query.all(), groups=TaxGroup.query.order_by(TaxGroup.name).all(), rates=TaxRate.query.order_by(TaxRate.name).all())


@bp.route("/tax-groups", methods=["POST"])
@login_required
def tax_groups():
    group = TaxGroup(name=request.form["name"], description=request.form.get("description"), status=bool(request.form.get("status")))
    db.session.add(group)
    db.session.commit()
    flash("Tax group saved.", "success")
    return redirect(url_for("masters.taxes"))


@bp.route("/tax-rates", methods=["POST"])
@login_required
def tax_rates():
    rate = TaxRate(tax_group_id=request.form.get("tax_group_id") or None, name=request.form["name"], rate=request.form.get("rate") or 0, tax_type=request.form.get("tax_type") or "GST", treatment=request.form.get("treatment") or "Taxable", status=bool(request.form.get("status")))
    db.session.add(rate)
    db.session.commit()
    flash("Tax rate saved.", "success")
    return redirect(url_for("masters.taxes"))
