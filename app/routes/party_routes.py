from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Customer, CustomerLedger, Supplier, SupplierLedger

bp = Blueprint("parties", __name__, url_prefix="/parties")


def save_customer(obj):
    for field in ["customer_code", "name", "business_name", "email", "phone", "alt_phone", "billing_address", "shipping_address", "city", "state", "country", "postal_code", "gst_number", "pan_number", "payment_terms"]:
        setattr(obj, field, request.form.get(field))
    obj.credit_limit = request.form.get("credit_limit") or 0
    obj.opening_balance = request.form.get("opening_balance") or 0
    obj.current_balance = obj.current_balance or obj.opening_balance
    obj.status = bool(request.form.get("status"))
    if not obj.id:
        obj.created_by = current_user.id


def save_supplier(obj):
    for field in ["supplier_code", "name", "business_name", "email", "phone", "alt_phone", "address", "city", "state", "country", "postal_code", "gst_number", "pan_number", "payment_terms"]:
        setattr(obj, field, request.form.get(field))
    obj.opening_balance = request.form.get("opening_balance") or 0
    obj.current_balance = obj.current_balance or obj.opening_balance
    obj.status = bool(request.form.get("status"))
    if not obj.id:
        obj.created_by = current_user.id


@bp.route("/customers")
@login_required
def customers():
    return render_template("parties/customers.html", title="Customers", items=Customer.query.order_by(Customer.id.desc()).all())


@bp.route("/customers/create", methods=["GET", "POST"])
@login_required
def customer_create():
    obj = Customer(country="India", status=True)
    if request.method == "POST":
        save_customer(obj); db.session.add(obj); db.session.commit(); flash("Customer saved.", "success")
        return redirect(url_for("parties.customers"))
    return render_template("parties/customer_form.html", title="Create Customer", item=obj)


@bp.route("/customers/<int:id>/edit", methods=["GET", "POST"])
@login_required
def customer_edit(id):
    obj = Customer.query.get_or_404(id)
    if request.method == "POST":
        save_customer(obj); db.session.commit(); flash("Customer updated.", "success")
        return redirect(url_for("parties.customers"))
    return render_template("parties/customer_form.html", title="Edit Customer", item=obj)


@bp.route("/customers/<int:id>/ledger")
@login_required
def customer_ledger(id):
    obj = Customer.query.get_or_404(id)
    return render_template("parties/ledger.html", title=f"Customer Ledger - {obj.name}", party=obj, entries=CustomerLedger.query.filter_by(customer_id=id).order_by(CustomerLedger.date).all())


@bp.route("/suppliers")
@login_required
def suppliers():
    return render_template("parties/suppliers.html", title="Suppliers", items=Supplier.query.order_by(Supplier.id.desc()).all())


@bp.route("/suppliers/create", methods=["GET", "POST"])
@login_required
def supplier_create():
    obj = Supplier(country="India", status=True)
    if request.method == "POST":
        save_supplier(obj); db.session.add(obj); db.session.commit(); flash("Supplier saved.", "success")
        return redirect(url_for("parties.suppliers"))
    return render_template("parties/supplier_form.html", title="Create Supplier", item=obj)


@bp.route("/suppliers/<int:id>/edit", methods=["GET", "POST"])
@login_required
def supplier_edit(id):
    obj = Supplier.query.get_or_404(id)
    if request.method == "POST":
        save_supplier(obj); db.session.commit(); flash("Supplier updated.", "success")
        return redirect(url_for("parties.suppliers"))
    return render_template("parties/supplier_form.html", title="Edit Supplier", item=obj)


@bp.route("/suppliers/<int:id>/ledger")
@login_required
def supplier_ledger(id):
    obj = Supplier.query.get_or_404(id)
    return render_template("parties/ledger.html", title=f"Supplier Ledger - {obj.name}", party=obj, entries=SupplierLedger.query.filter_by(supplier_id=id).order_by(SupplierLedger.date).all())

