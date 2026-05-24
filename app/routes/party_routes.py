from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Customer, CustomerLedger, Purchase, Sale, Supplier, SupplierLedger, TDSSection
from app.utils.excel_export import export_to_excel
from app.utils.tax_validation import is_valid_gstin, is_valid_pan

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PARTY_TAGS = ["VIP", "New", "On Hold", "Wholesale"]

bp = Blueprint("parties", __name__, url_prefix="/parties")


def save_customer(obj):
    if not is_valid_gstin(request.form.get("gst_number")):
        raise ValueError("Invalid GSTIN format or checksum.")
    if not is_valid_pan(request.form.get("pan_number")):
        raise ValueError("Invalid PAN format.")
    for field in ["customer_code", "name", "business_name", "email", "phone", "alt_phone", "billing_address", "shipping_address", "city", "state", "country", "postal_code", "gst_number", "pan_number", "customer_type", "payment_terms"]:
        setattr(obj, field, request.form.get(field))
    obj.credit_limit = request.form.get("credit_limit") or 0
    obj.tags = ",".join(tag for tag in PARTY_TAGS if tag in request.form.getlist("tags"))
    obj.opening_balance = request.form.get("opening_balance") or 0
    obj.current_balance = obj.current_balance or obj.opening_balance
    obj.status = bool(request.form.get("status"))
    if not obj.id:
        obj.created_by = current_user.id


def save_supplier(obj):
    if not is_valid_gstin(request.form.get("gst_number")):
        raise ValueError("Invalid GSTIN format or checksum.")
    if not is_valid_pan(request.form.get("pan_number")):
        raise ValueError("Invalid PAN format.")
    for field in ["supplier_code", "name", "business_name", "contact_person", "email", "phone", "alt_phone", "address", "billing_address", "city", "state", "country", "postal_code", "gst_number", "pan_number", "tax_treatment", "payment_terms"]:
        setattr(obj, field, request.form.get(field))
    obj.opening_balance = request.form.get("opening_balance") or 0
    obj.tags = ",".join(tag for tag in PARTY_TAGS if tag in request.form.getlist("tags"))
    obj.current_balance = obj.current_balance or obj.opening_balance
    obj.tds_applicable = bool(request.form.get("tds_applicable"))
    obj.tds_section_id = request.form.get("tds_section_id") or None
    obj.status = bool(request.form.get("status"))
    if not obj.id:
        obj.created_by = current_user.id


@bp.route("/customers")
@login_required
def customers():
    query = Customer.query
    if request.args.get("tag"):
        query = query.filter(Customer.tags.like(f"%{request.args['tag']}%"))
    return render_template("parties/customers.html", title="Customers", items=query.order_by(Customer.id.desc()).all(), party_tags=PARTY_TAGS)


@bp.route("/customers/create", methods=["GET", "POST"])
@login_required
def customer_create():
    obj = Customer(country="India", status=True)
    if request.method == "POST":
        try:
            save_customer(obj); db.session.add(obj); db.session.commit(); flash("Customer saved.", "success")
            return redirect(url_for("parties.customers"))
        except ValueError as exc:
            flash(str(exc), "danger")
    return render_template("parties/customer_form.html", title="Create Customer", item=obj, party_tags=PARTY_TAGS)


@bp.route("/customers/<int:id>/edit", methods=["GET", "POST"])
@login_required
def customer_edit(id):
    obj = Customer.query.get_or_404(id)
    if request.method == "POST":
        try:
            save_customer(obj); db.session.commit(); flash("Customer updated.", "success")
            return redirect(url_for("parties.customers"))
        except ValueError as exc:
            flash(str(exc), "danger")
    return render_template("parties/customer_form.html", title="Edit Customer", item=obj, party_tags=PARTY_TAGS)


@bp.route("/customers/<int:id>/ledger")
@login_required
def customer_ledger(id):
    obj = Customer.query.get_or_404(id)
    entries = CustomerLedger.query.filter_by(customer_id=id).order_by(CustomerLedger.date).all()
    if request.args.get("export") == "xlsx":
        return ledger_excel(f"customer-ledger-{obj.customer_code}.xlsx", obj.name, entries)
    return render_template("parties/ledger.html", title=f"Customer Ledger - {obj.name}", party=obj, entries=entries)


@bp.route("/suppliers")
@login_required
def suppliers():
    query = Supplier.query
    if request.args.get("tag"):
        query = query.filter(Supplier.tags.like(f"%{request.args['tag']}%"))
    return render_template("parties/suppliers.html", title="Suppliers", items=query.order_by(Supplier.id.desc()).all(), party_tags=PARTY_TAGS)


@bp.route("/suppliers/create", methods=["GET", "POST"])
@login_required
def supplier_create():
    obj = Supplier(country="India", status=True)
    if request.method == "POST":
        try:
            save_supplier(obj); db.session.add(obj); db.session.commit(); flash("Supplier saved.", "success")
            return redirect(url_for("parties.suppliers"))
        except ValueError as exc:
            flash(str(exc), "danger")
    return render_template("parties/supplier_form.html", title="Create Supplier", item=obj, tds_sections=TDSSection.query.filter_by(is_active=True).all(), party_tags=PARTY_TAGS)


@bp.route("/suppliers/<int:id>/edit", methods=["GET", "POST"])
@login_required
def supplier_edit(id):
    obj = Supplier.query.get_or_404(id)
    if request.method == "POST":
        try:
            save_supplier(obj); db.session.commit(); flash("Supplier updated.", "success")
            return redirect(url_for("parties.suppliers"))
        except ValueError as exc:
            flash(str(exc), "danger")
    return render_template("parties/supplier_form.html", title="Edit Supplier", item=obj, tds_sections=TDSSection.query.filter_by(is_active=True).all(), party_tags=PARTY_TAGS)


@bp.route("/hover-card/<party_type>/<int:id>")
@login_required
def hover_card(party_type, id):
    if party_type == "customer":
        party = Customer.query.get_or_404(id)
        last_txn = Sale.query.filter_by(customer_id=id).order_by(Sale.invoice_date.desc(), Sale.id.desc()).first()
        credit_limit = float(party.credit_limit or 0)
    elif party_type == "supplier":
        party = Supplier.query.get_or_404(id)
        last_txn = Purchase.query.filter_by(supplier_id=id).order_by(Purchase.purchase_date.desc(), Purchase.id.desc()).first()
        credit_limit = 0
    else:
        return jsonify({"error": "Unknown party type"}), 404
    txn_date = getattr(last_txn, "invoice_date", None) or getattr(last_txn, "purchase_date", None) if last_txn else None
    return jsonify({
        "name": party.name,
        "outstanding": float(party.outstanding or 0),
        "credit_limit": credit_limit,
        "last_transaction_date": txn_date.isoformat() if txn_date else "No transactions",
        "phone": party.phone or "Not set",
        "tags": party.tag_list,
    })


@bp.route("/suppliers/<int:id>/ledger")
@login_required
def supplier_ledger(id):
    obj = Supplier.query.get_or_404(id)
    entries = SupplierLedger.query.filter_by(supplier_id=id).order_by(SupplierLedger.date).all()
    if request.args.get("export") == "xlsx":
        return ledger_excel(f"supplier-ledger-{obj.supplier_code}.xlsx", obj.name, entries)
    return render_template("parties/ledger.html", title=f"Supplier Ledger - {obj.name}", party=obj, entries=entries)


def ledger_excel(filename, sheet_name, entries):
    output = export_to_excel(["Date", "Reference", "Narration", "Debit", "Credit", "Balance"], [[e.date, e.reference_no, e.narration, e.debit, e.credit, e.balance] for e in entries], sheet_name)
    return send_file(output, mimetype=XLSX_MIMETYPE, as_attachment=True, download_name=filename)
