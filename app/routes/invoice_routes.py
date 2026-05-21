import hmac
import json
import os
from datetime import date, datetime, timedelta
from hashlib import sha256

try:
    import razorpay
except ImportError:  # pragma: no cover - dependency is declared for deployments
    razorpay = None
from flask import Blueprint, flash, jsonify, redirect, render_template, render_template_string, request, send_file, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import CommunicationLog, Currency, Customer, IntegrationSetting, PaymentReceived, PrintTemplate, Product, Sale, Warehouse
from app.services.document_service import hsn_summary
from app.services.invoice_service import cancel_invoice, create_or_update_invoice, issue_invoice, line_totals, record_invoice_payment
from app.services.numbering_service import next_number
from app.services.audit_service import record_audit
from app.utils.pdf_generator import render_pdf

bp = Blueprint("invoices", __name__, url_prefix="/invoices")


def parse_invoice_items():
    items = []
    for product_id, q, r, d, t in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]"), request.form.getlist("discount[]"), request.form.getlist("tax_rate[]")):
        if not product_id:
            continue
        totals = line_totals(q, r, d, t)
        items.append({"product_id": int(product_id), "quantity": q, "rate": r, "discount": d, "tax_rate": t, **totals})
    return items


@bp.route("/")
@login_required
def index():
    query = Sale.query
    if request.args.get("status"):
        status = request.args["status"]
        if status == "Overdue":
            query = query.filter(Sale.status.in_(["Issued", "Partially Paid"]), Sale.balance_amount > 0, Sale.due_date < date.today())
        else:
            query = query.filter(Sale.status == status)
    if request.args.get("customer_id"):
        query = query.filter(Sale.customer_id == request.args["customer_id"])
    if request.args.get("date_from"):
        query = query.filter(Sale.invoice_date >= date.fromisoformat(request.args["date_from"]))
    if request.args.get("date_to"):
        query = query.filter(Sale.invoice_date <= date.fromisoformat(request.args["date_to"]))
    return render_template("invoices/index.html", title="Invoices", invoices=query.order_by(Sale.id.desc()).all(), customers=Customer.query.order_by(Customer.name).all(), statuses=["Draft", "Issued", "Partially Paid", "Paid", "Overdue", "Cancelled"])


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    sale = Sale(invoice_no=next_number("sales"), invoice_date=date.today(), due_date=date.today() + timedelta(days=30), status="Draft")
    if request.method == "POST":
        try:
            sale = create_or_update_invoice(sale, request.form, parse_invoice_items(), current_user.id)
            if request.form.get("action") == "issue":
                issue_invoice(sale, current_user.id)
                flash("Invoice issued, stock updated, and accounts posted.", "success")
            else:
                flash("Draft invoice saved.", "success")
            db.session.commit()
            return redirect(url_for("invoices.detail", id=sale.id))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("invoices/form.html", title="Create Invoice", invoice=sale, customers=Customer.query.order_by(Customer.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all(), products=Product.query.filter_by(is_active=True).order_by(Product.name).all(), currencies=Currency.query.order_by(Currency.code).all(), form_action=url_for("invoices.create"))


@bp.route("/<int:id>")
@login_required
def detail(id):
    invoice = Sale.query.get_or_404(id)
    return render_template("invoices/detail.html", title=f"Invoice {invoice.invoice_no}", invoice=invoice, payments=PaymentReceived.query.filter_by(sale_id=invoice.id).order_by(PaymentReceived.receipt_date.desc()).all(), today=date.today())


@bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit(id):
    invoice = Sale.query.get_or_404(id)
    if invoice.status != "Draft":
        flash("Only draft invoices can be edited.", "warning")
        return redirect(url_for("invoices.detail", id=invoice.id))
    if request.method == "POST":
        try:
            create_or_update_invoice(invoice, request.form, parse_invoice_items(), current_user.id)
            if request.form.get("action") == "issue":
                issue_invoice(invoice, current_user.id)
                flash("Invoice issued, stock updated, and accounts posted.", "success")
            else:
                flash("Draft invoice updated.", "success")
            db.session.commit()
            return redirect(url_for("invoices.detail", id=invoice.id))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("invoices/form.html", title=f"Edit {invoice.invoice_no}", invoice=invoice, customers=Customer.query.order_by(Customer.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all(), products=Product.query.filter_by(is_active=True).order_by(Product.name).all(), currencies=Currency.query.order_by(Currency.code).all(), form_action=url_for("invoices.edit", id=invoice.id))


@bp.route("/<int:id>/issue", methods=["POST"])
@login_required
def issue(id):
    invoice = Sale.query.get_or_404(id)
    try:
        issue_invoice(invoice, current_user.id)
        db.session.commit()
        flash("Invoice issued, stock updated, and accounts posted.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("invoices.detail", id=invoice.id))


@bp.route("/<int:id>/payments", methods=["POST"])
@login_required
def payment(id):
    invoice = Sale.query.get_or_404(id)
    try:
        payment_date = date.fromisoformat(request.form["payment_date"])
        record_invoice_payment(invoice, request.form["amount"], payment_date, request.form.get("payment_mode"), request.form.get("reference_no"), request.form.get("notes"), current_user.id)
        record_audit("Payment Update", "Sale", invoice.id, new_data={"invoice_no": invoice.invoice_no, "amount": request.form["amount"]})
        db.session.commit()
        flash("Payment recorded and invoice balance updated.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("invoices.detail", id=invoice.id))


@bp.route("/<int:id>/cancel", methods=["POST"])
@login_required
def cancel(id):
    invoice = Sale.query.get_or_404(id)
    try:
        cancel_invoice(invoice, request.form.get("reason"), current_user.id)
        record_audit("Invoice Cancellation", "Sale", invoice.id, new_data={"invoice_no": invoice.invoice_no, "reason": request.form.get("reason")})
        db.session.commit()
        flash("Invoice cancelled.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("invoices.detail", id=invoice.id))


@bp.route("/<int:id>/print")
@login_required
def print_invoice(id):
    invoice = Sale.query.get_or_404(id)
    template = PrintTemplate.query.filter_by(template_type="sales_invoice", is_default=True).first()
    if template and template.html:
        return render_template_string(template.html, title=f"Invoice {invoice.invoice_no}", invoice=invoice, sale=invoice, items=invoice.items, hsn_rows=hsn_summary(invoice))
    return render_template("sales/print.html", title=f"Invoice {invoice.invoice_no}", sale=invoice, hsn_rows=hsn_summary(invoice))


@bp.route("/<int:id>/pdf")
@login_required
def pdf(id):
    invoice = Sale.query.get_or_404(id)
    pdf_file = render_pdf("sales/print.html", sale=invoice, title=f"Invoice {invoice.invoice_no}")
    return send_file(pdf_file, mimetype="application/pdf", download_name=f"{invoice.invoice_no}.pdf")


@bp.route("/api")
@login_required
def api_index():
    query = Sale.query
    if request.args.get("status"):
        query = query.filter(Sale.status == request.args["status"])
    data = []
    for invoice in query.order_by(Sale.id.desc()).all():
        data.append({"id": invoice.id, "invoice_no": invoice.invoice_no, "date": invoice.invoice_date.isoformat(), "due_date": invoice.due_date.isoformat() if invoice.due_date else None, "customer": invoice.customer.name, "status": invoice.display_status, "total": float(invoice.grand_total or 0), "paid": float(invoice.paid_amount or 0), "balance": float(invoice.balance_amount or 0)})
    return jsonify({"data": data})


@bp.route("/api/<int:id>")
@login_required
def api_detail(id):
    invoice = Sale.query.get_or_404(id)
    return jsonify({"id": invoice.id, "invoice_no": invoice.invoice_no, "status": invoice.display_status, "customer": {"id": invoice.customer.id, "name": invoice.customer.name, "outstanding": invoice.customer.outstanding}, "subtotal": float(invoice.subtotal or 0), "discount_total": float(invoice.discount_total or 0), "tax_total": float(invoice.tax_total or 0), "grand_total": float(invoice.grand_total or 0), "paid": float(invoice.paid_amount or 0), "balance": float(invoice.balance_amount or 0), "items": [{"product_id": item.product_id, "product": item.product.name, "quantity": float(item.quantity), "rate": float(item.rate), "tax_rate": float(item.tax_rate or 0), "line_total": float(item.line_total or 0)} for item in invoice.items]})


@bp.route("/<int:id>/pay")
def pay(id):
    invoice = Sale.query.get_or_404(id)
    key_id, _ = razorpay_credentials()
    return render_template("invoices/pay.html", title=f"Pay {invoice.invoice_no}", invoice=invoice, key_id=key_id)


@bp.route("/<int:id>/create-order", methods=["POST"])
def create_order(id):
    invoice = Sale.query.get_or_404(id)
    key_id, key_secret = razorpay_credentials()
    if not key_id or not key_secret or not razorpay:
        return jsonify({"error": "Razorpay is not configured"}), 400
    amount = int(round(float(invoice.balance_amount or invoice.grand_total or 0) * 100))
    if amount <= 0:
        return jsonify({"error": "Invoice has no pending balance"}), 400
    client = razorpay.Client(auth=(key_id, key_secret))
    order = client.order.create({"amount": amount, "currency": "INR", "receipt": invoice.invoice_no, "notes": {"customer": invoice.customer.name, "invoice": invoice.invoice_no}})
    invoice.razorpay_order_id = order["id"]
    record_audit("Create", "RazorpayOrder", invoice.id, new_data={"order_id": order["id"], "amount": amount})
    db.session.commit()
    return jsonify({"order_id": order["id"], "amount": amount, "currency": "INR", "key_id": key_id})


@bp.route("/<int:id>/payment-callback", methods=["POST"])
def payment_callback(id):
    invoice = Sale.query.get_or_404(id)
    _, key_secret = razorpay_credentials()
    order_id = request.form.get("razorpay_order_id", "")
    payment_id = request.form.get("razorpay_payment_id", "")
    signature = request.form.get("razorpay_signature", "")
    expected = hmac.new(key_secret.encode(), f"{order_id}|{payment_id}".encode(), sha256).hexdigest()
    if not key_secret or not hmac.compare_digest(expected, signature):
        record_audit("Payment Verification Failed", "Sale", invoice.id, new_data={"order_id": order_id, "payment_id": payment_id})
        db.session.add(CommunicationLog(channel="payment", recipient=invoice.customer.name, subject=f"Razorpay failed {invoice.invoice_no}", provider="Razorpay", status="Failed", reference_type="invoice", reference_id=invoice.id, error_message="Invalid Razorpay signature"))
        db.session.commit()
        flash("Payment verification failed.", "danger")
        return redirect(url_for("invoices.pay", id=invoice.id))
    if invoice.razorpay_payment_id == payment_id or PaymentReceived.query.filter_by(reference_no=payment_id).first():
        flash("Payment callback was already processed.", "warning")
        return redirect(url_for("invoices.pay", id=invoice.id))
    try:
        record_invoice_payment(invoice, invoice.balance_amount or invoice.grand_total, date.today(), "Razorpay", payment_id, "Online payment", None)
        invoice.razorpay_order_id = order_id
        invoice.razorpay_payment_id = payment_id
        invoice.razorpay_signature = signature
        invoice.razorpay_verified_at = datetime.utcnow()
        record_audit("Payment Verified", "Sale", invoice.id, new_data={"order_id": order_id, "payment_id": payment_id})
        db.session.commit()
        flash("Payment successful.", "success")
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
    return redirect(url_for("invoices.pay", id=invoice.id))


def razorpay_credentials():
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    setting = IntegrationSetting.query.filter_by(provider_type="payment_gateway", provider_name="Razorpay", is_active=True).order_by(IntegrationSetting.id.desc()).first()
    if setting and setting.config_json:
        try:
            config = json.loads(setting.config_json)
            key_id = config.get("key_id") or config.get("RAZORPAY_KEY_ID") or key_id
            key_secret = config.get("key_secret") or config.get("RAZORPAY_KEY_SECRET") or key_secret
        except ValueError:
            pass
    return key_id, key_secret
