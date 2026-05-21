from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Customer, Product, RecurringInvoice, RecurringInvoiceItem, Sale, Warehouse
from app.services.invoice_service import calculate_document, line_totals
from app.services.recurring_service import generate_due_recurring, generate_sale_from_recurring

bp = Blueprint("recurring", __name__, url_prefix="/recurring")


def _items_from_form():
    items = []
    for product_id, qty, rate, discount, tax_rate in zip(
        request.form.getlist("product_id[]"),
        request.form.getlist("quantity[]"),
        request.form.getlist("rate[]"),
        request.form.getlist("discount[]"),
        request.form.getlist("tax_rate[]"),
    ):
        if product_id:
            items.append({"product_id": int(product_id), "quantity": qty or 0, "rate": rate or 0, "discount": discount or 0, "tax_rate": tax_rate or 0})
    if not items:
        raise ValueError("At least one recurring invoice item is required.")
    return items


@bp.route("/")
@login_required
def index():
    rows = RecurringInvoice.query.order_by(RecurringInvoice.next_run_date.asc()).all()
    return render_template("recurring/index.html", title="Recurring Invoices", rows=rows)


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        try:
            recurring = RecurringInvoice(
                name=request.form["name"],
                customer_id=request.form["customer_id"],
                warehouse_id=request.form["warehouse_id"],
                frequency=request.form.get("frequency") or "Monthly",
                interval_value=request.form.get("interval_value") or 1,
                next_run_date=date.fromisoformat(request.form["next_run_date"]),
                end_date=date.fromisoformat(request.form["end_date"]) if request.form.get("end_date") else None,
                auto_send=bool(request.form.get("auto_send")),
                auto_collect=bool(request.form.get("auto_collect")),
                notes=request.form.get("notes"),
                terms=request.form.get("terms"),
                created_by=current_user.id,
            )
            db.session.add(recurring)
            db.session.flush()
            for item in _items_from_form():
                db.session.add(RecurringInvoiceItem(recurring_id=recurring.id, **item))
            db.session.commit()
            flash("Recurring invoice created.", "success")
            return redirect(url_for("recurring.index"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return _form("Create Recurring Invoice", RecurringInvoice(next_run_date=date.today(), interval_value=1))


@bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit(id):
    recurring = RecurringInvoice.query.get_or_404(id)
    if request.method == "POST":
        try:
            recurring.name = request.form["name"]
            recurring.customer_id = request.form["customer_id"]
            recurring.warehouse_id = request.form["warehouse_id"]
            recurring.frequency = request.form.get("frequency") or "Monthly"
            recurring.interval_value = request.form.get("interval_value") or 1
            recurring.next_run_date = date.fromisoformat(request.form["next_run_date"])
            recurring.end_date = date.fromisoformat(request.form["end_date"]) if request.form.get("end_date") else None
            recurring.auto_send = bool(request.form.get("auto_send"))
            recurring.auto_collect = bool(request.form.get("auto_collect"))
            recurring.notes = request.form.get("notes")
            recurring.terms = request.form.get("terms")
            RecurringInvoiceItem.query.filter_by(recurring_id=recurring.id).delete()
            for item in _items_from_form():
                db.session.add(RecurringInvoiceItem(recurring_id=recurring.id, **item))
            db.session.commit()
            flash("Recurring invoice updated.", "success")
            return redirect(url_for("recurring.index"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return _form("Edit Recurring Invoice", recurring)


@bp.route("/<int:id>/pause", methods=["POST"])
@login_required
def pause(id):
    recurring = RecurringInvoice.query.get_or_404(id)
    recurring.status = "Active" if recurring.status == "Paused" else "Paused"
    db.session.commit()
    flash(f"{recurring.name} is now {recurring.status}.", "success")
    return redirect(url_for("recurring.index"))


@bp.route("/<int:id>/run-now", methods=["POST"])
@login_required
def run_now(id):
    recurring = RecurringInvoice.query.get_or_404(id)
    sale = generate_sale_from_recurring(recurring, current_user.id)
    db.session.commit()
    flash(f"Generated invoice {sale.invoice_no}.", "success")
    return redirect(url_for("invoices.detail", id=sale.id))


@bp.route("/<int:id>/history")
@login_required
def history(id):
    recurring = RecurringInvoice.query.get_or_404(id)
    marker = f"Recurring template #{recurring.id}"
    sales = Sale.query.filter(Sale.notes.like(f"%{marker}%")).order_by(Sale.invoice_date.desc()).all()
    return render_template("recurring/history.html", title=f"History - {recurring.name}", recurring=recurring, sales=sales)


@bp.route("/run-due", methods=["POST"])
@login_required
def run_due():
    generated = generate_due_recurring()
    flash(f"Generated {len(generated)} due recurring invoice(s).", "success")
    return redirect(url_for("recurring.index"))


def _form(title, recurring):
    products = Product.query.order_by(Product.name).all()
    product_options = [{"id": p.id, "text": f"{p.sku} - {p.name}", "rate": float(p.sales_price or 0), "tax": float(p.tax.rate if p.tax else 0)} for p in products]
    total_items = []
    for item in recurring.items if getattr(recurring, "id", None) else []:
        data = {"product_id": item.product_id, "product_name": item.product.name, "quantity": item.quantity, "rate": item.rate, "discount": item.discount, "tax_rate": item.tax_rate}
        total_items.append({**data, **line_totals(item.quantity, item.rate, item.discount, item.tax_rate)})
    totals = calculate_document(total_items) if total_items else {}
    return render_template(
        "recurring/form.html",
        title=title,
        recurring=recurring,
        customers=Customer.query.order_by(Customer.name).all(),
        warehouses=Warehouse.query.order_by(Warehouse.name).all(),
        product_options=product_options,
        items=total_items,
        totals=totals,
        frequencies=["Daily", "Weekly", "Monthly", "Quarterly", "Yearly"],
    )
