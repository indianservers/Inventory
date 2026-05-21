from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import CreditNote, CreditNoteItem, Customer, CustomerLedger, DebitNote, DebitNoteItem, Product, Purchase, Refund, Sale, Supplier
from app.services.audit_service import record_audit
from app.services.accounting_service import account, create_journal
from app.services.invoice_service import calculate_document, line_totals
from app.services.numbering_service import next_number
from app.utils.pdf_generator import render_pdf

bp = Blueprint("notes", __name__, url_prefix="")


def parse_note_items():
    items = []
    for product_id, q, r, t in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]"), request.form.getlist("tax_rate[]")):
        if product_id:
            totals = line_totals(q, r, 0, t)
            items.append({"product_id": product_id, "quantity": q, "rate": r, "tax_rate": t, **totals})
    if not items:
        raise ValueError("At least one item is required.")
    return items


@bp.route("/credit-notes/")
@login_required
def credit_notes():
    return render_template("notes/index.html", title="Credit Notes", items=CreditNote.query.order_by(CreditNote.id.desc()).all(), kind="credit")


@bp.route("/credit-notes/create", methods=["GET", "POST"])
@login_required
def credit_note_create():
    if request.method == "POST":
        try:
            items = parse_note_items(); totals = calculate_document(items)
            note = CreditNote(cn_no=request.form.get("cn_no") or next_number("credit_note"), cn_date=date.fromisoformat(request.form["cn_date"]), customer_id=request.form["customer_id"], sale_id=request.form.get("sale_id") or None, reason=request.form.get("reason"), adjustment_type=request.form.get("adjustment_type") or "Other", status="Issued", created_by=current_user.id, subtotal=totals["subtotal"], tax_total=totals["tax_total"], grand_total=totals["grand_total"])
            db.session.add(note); db.session.flush()
            for item in items:
                db.session.add(CreditNoteItem(cn_id=note.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
            create_journal(note.cn_date, "CreditNote", note.id, f"Credit note {note.cn_no}", [{"account": account("Sales"), "debit": note.grand_total - note.tax_total}, {"account": account("Tax Payable"), "debit": note.tax_total}, {"account": account("Accounts Receivable"), "credit": note.grand_total}], current_user.id)
            customer = Customer.query.get(note.customer_id)
            customer.current_balance = float(customer.current_balance or 0) - float(note.grand_total or 0)
            db.session.add(CustomerLedger(date=note.cn_date, customer_id=note.customer_id, reference_type="CreditNote", reference_id=note.id, reference_no=note.cn_no, debit=0, credit=note.grand_total, balance=customer.outstanding - float(note.grand_total or 0), narration="Credit note issued"))
            db.session.commit(); flash("Credit note issued.", "success")
            return redirect(url_for("notes.credit_notes"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("notes/form.html", title="Create Credit Note", kind="credit", number=next_number("credit_note"), today=date.today(), customers=Customer.query.all(), sales=Sale.query.all(), products=Product.query.order_by(Product.name).all())


@bp.route("/credit-notes/<int:id>/print")
@login_required
def credit_note_print(id):
    return render_template("notes/print.html", title="Credit Note", note=CreditNote.query.get_or_404(id), kind="credit")


@bp.route("/credit-notes/<int:id>/pdf")
@login_required
def credit_note_pdf(id):
    note = CreditNote.query.get_or_404(id)
    return send_file(render_pdf("notes/print.html", note=note, kind="credit", title="Credit Note"), mimetype="application/pdf", download_name=f"{note.cn_no}.pdf")


@bp.route("/credit-notes/<int:id>/apply", methods=["POST"])
@login_required
def credit_note_apply(id):
    note = CreditNote.query.get_or_404(id)
    sale = Sale.query.get_or_404(request.form["sale_id"])
    amount = min(float(request.form.get("amount") or 0), float(note.grand_total or 0) - float(note.applied_amount or 0) - float(note.refunded_amount or 0), float(sale.balance_amount or 0))
    if amount <= 0:
        flash("Enter a valid amount to apply.", "warning")
        return redirect(url_for("notes.credit_notes"))
    sale.paid_amount = float(sale.paid_amount or 0) + amount
    sale.update_payment_status()
    note.applied_amount = float(note.applied_amount or 0) + amount
    record_audit("Payment Update", "CreditNote", note.id, new_data={"applied_to": sale.invoice_no, "amount": amount})
    db.session.commit()
    flash("Credit note applied to invoice.", "success")
    return redirect(url_for("notes.credit_notes"))


@bp.route("/credit-notes/<int:id>/refund", methods=["POST"])
@login_required
def credit_note_refund(id):
    note = CreditNote.query.get_or_404(id)
    amount = min(float(request.form.get("amount") or 0), float(note.grand_total or 0) - float(note.applied_amount or 0) - float(note.refunded_amount or 0))
    if amount <= 0:
        flash("Enter a valid refund amount.", "warning")
        return redirect(url_for("notes.credit_notes"))
    refund = Refund(refund_no=next_number("refund"), refund_date=date.today(), customer_id=note.customer_id, credit_note_id=note.id, amount=amount, refund_mode=request.form.get("refund_mode") or "Cash", reference_no=request.form.get("reference_no"), approval_status="Approved", notes=f"Refund against {note.cn_no}", created_by=current_user.id)
    db.session.add(refund)
    note.refunded_amount = float(note.refunded_amount or 0) + amount
    customer = Customer.query.get(note.customer_id)
    customer.current_balance = float(customer.current_balance or 0) + amount
    db.session.add(CustomerLedger(date=refund.refund_date, customer_id=note.customer_id, reference_type="Refund", reference_id=refund.id, reference_no=refund.refund_no, debit=amount, credit=0, balance=customer.outstanding + amount, narration=f"Refund against {note.cn_no}"))
    record_audit("Payment Update", "Refund", refund.id, new_data={"credit_note": note.cn_no, "amount": amount})
    db.session.commit()
    flash("Credit note refunded.", "success")
    return redirect(url_for("notes.credit_notes"))


@bp.route("/debit-notes/")
@login_required
def debit_notes():
    return render_template("notes/index.html", title="Debit Notes", items=DebitNote.query.order_by(DebitNote.id.desc()).all(), kind="debit")


@bp.route("/debit-notes/create", methods=["GET", "POST"])
@login_required
def debit_note_create():
    if request.method == "POST":
        try:
            items = parse_note_items(); totals = calculate_document(items)
            note = DebitNote(dn_no=request.form.get("dn_no") or next_number("debit_note"), dn_date=date.fromisoformat(request.form["dn_date"]), supplier_id=request.form["supplier_id"], purchase_id=request.form.get("purchase_id") or None, reason=request.form.get("reason"), adjustment_type=request.form.get("adjustment_type") or "Other", status="Issued", created_by=current_user.id, subtotal=totals["subtotal"], tax_total=totals["tax_total"], grand_total=totals["grand_total"])
            db.session.add(note); db.session.flush()
            for item in items:
                db.session.add(DebitNoteItem(dn_id=note.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
            db.session.commit(); flash("Debit note issued.", "success")
            return redirect(url_for("notes.debit_notes"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("notes/form.html", title="Create Debit Note", kind="debit", number=next_number("debit_note"), today=date.today(), suppliers=Supplier.query.all(), purchases=Purchase.query.all(), products=Product.query.order_by(Product.name).all())


@bp.route("/debit-notes/<int:id>/print")
@login_required
def debit_note_print(id):
    return render_template("notes/print.html", title="Debit Note", note=DebitNote.query.get_or_404(id), kind="debit")


@bp.route("/debit-notes/<int:id>/pdf")
@login_required
def debit_note_pdf(id):
    note = DebitNote.query.get_or_404(id)
    return send_file(render_pdf("notes/print.html", note=note, kind="debit", title="Debit Note"), mimetype="application/pdf", download_name=f"{note.dn_no}.pdf")
