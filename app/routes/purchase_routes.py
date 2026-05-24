import os
from datetime import date
from urllib.parse import quote_plus

import requests

from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Batch, Currency, ITCEntry, Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem, SerialNumber, Supplier, SupplierLedger, TDSEntry, VendorCredit, VendorCreditItem, Warehouse
from app.services.accounting_service import account, create_journal, post_purchase
from app.services.audit_service import record_audit
from app.services.invoice_service import calculate_document, line_totals
from app.services.numbering_service import next_number
from app.services.stock_service import apply_purchase_item, apply_purchase_return_item
from app.utils.pdf_generator import render_pdf

bp = Blueprint("purchases", __name__, url_prefix="/purchases")


def parse_items():
    items = []
    for product_id, q, r, d, t in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]"), request.form.getlist("discount[]"), request.form.getlist("tax_rate[]")):
        if not product_id:
            continue
        totals = line_totals(q, r, d, t)
        items.append({"product_id": int(product_id), "quantity": q, "rate": r, "discount": d, "tax_rate": t, **totals})
    if not items:
        raise ValueError("At least one item is required.")
    return items


def parse_return_items():
    items = []
    for product_id, q, r, t in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("rate[]"), request.form.getlist("tax_rate[]")):
        if not product_id:
            continue
        totals = line_totals(q, r, 0, t)
        items.append({"product_id": int(product_id), "quantity": q, "rate": r, "tax_rate": t, **totals})
    if not items:
        raise ValueError("At least one item is required.")
    return items


@bp.route("/")
@login_required
def index():
    query = Purchase.query
    if request.args.get("status"):
        query = query.filter(Purchase.status == request.args["status"])
    if request.args.get("supplier_id"):
        query = query.filter(Purchase.supplier_id == request.args["supplier_id"])
    if request.args.get("date_from"):
        query = query.filter(Purchase.purchase_date >= date.fromisoformat(request.args["date_from"]))
    if request.args.get("date_to"):
        query = query.filter(Purchase.purchase_date <= date.fromisoformat(request.args["date_to"]))
    return render_template("purchases/index.html", title="Purchase Invoices", purchases=query.order_by(Purchase.id.desc()).all(), suppliers=Supplier.query.order_by(Supplier.name).all(), statuses=["Draft", "Approved", "Cancelled"])


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        try:
            items = parse_items()
            totals = calculate_document(items, shipping=request.form.get("shipping_charges"), other=request.form.get("other_charges"), paid=request.form.get("paid_amount"))
            currency = Currency.query.get(request.form.get("currency_id")) if request.form.get("currency_id") else Currency.query.filter_by(is_base=True).first()
            exchange_rate = float(request.form.get("exchange_rate_snapshot") or (currency.exchange_rate if currency else 1) or 1)
            original_total = totals["grand_total"]
            if exchange_rate != 1:
                for key in ["subtotal", "discount_total", "tax_total", "grand_total", "paid_amount", "balance_amount"]:
                    totals[key] = float(totals[key] or 0) * exchange_rate
                for item in items:
                    for key in ["rate", "gross", "discount_amount", "tax_amount", "line_total"]:
                        item[key] = float(item[key] or 0) * exchange_rate
            purchase = Purchase(purchase_no=request.form.get("purchase_no") or next_number("purchases"), purchase_date=date.fromisoformat(request.form["purchase_date"]), supplier_id=request.form["supplier_id"], warehouse_id=request.form["warehouse_id"], currency_id=currency.id if currency else None, exchange_rate_snapshot=exchange_rate, original_currency_total=original_total, supplier_invoice_no=request.form.get("supplier_invoice_no"), supplier_invoice_date=date.fromisoformat(request.form["supplier_invoice_date"]) if request.form.get("supplier_invoice_date") else None, notes=request.form.get("notes"), created_by=current_user.id, **totals)
            purchase.due_date = date.fromisoformat(request.form["due_date"]) if request.form.get("due_date") else purchase.purchase_date
            purchase.status = request.form.get("status") or "Approved"
            purchase.update_payment_status()
            db.session.add(purchase); db.session.flush()
            apply_purchase_tds(purchase)
            for index, item in enumerate(items):
                db.session.add(PurchaseItem(purchase_id=purchase.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], discount=item["discount"], discount_amount=item["discount_amount"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
                if purchase.status != "Draft":
                    apply_purchase_item(item["product_id"], purchase.warehouse_id, item["quantity"], item["rate"], purchase.id, purchase.purchase_no)
                    capture_purchase_tracking(index, item["product_id"], purchase.warehouse_id, item["quantity"], item["rate"], purchase.id, purchase.purchase_no)
            if purchase.status != "Draft":
                post_purchase(purchase, current_user.id)
                create_or_update_itc_entry(purchase)
            record_audit("Create", "Purchase", purchase.id, new_data={"purchase_no": purchase.purchase_no})
            db.session.commit()
            flash("Purchase saved and stock updated.", "success")
            return redirect(url_for("purchases.index"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("purchases/form.html", title="Create Purchase", purchase=None, suppliers=Supplier.query.all(), warehouses=Warehouse.query.all(), currencies=Currency.query.order_by(Currency.code).all(), today=date.today(), purchase_no=next_number("purchases"))


@bp.route("/<int:id>/approve", methods=["POST"])
@login_required
def approve_purchase(id):
    purchase = Purchase.query.get_or_404(id)
    if purchase.status != "Draft":
        flash("Only draft purchases can be approved.", "warning")
        return redirect(url_for("purchases.index"))
    try:
        for item in purchase.items:
            apply_purchase_item(item.product_id, purchase.warehouse_id, item.quantity, item.rate, purchase.id, purchase.purchase_no)
        purchase.status = "Approved"
        post_purchase(purchase, current_user.id)
        create_or_update_itc_entry(purchase)
        record_audit("Update", "Purchase", purchase.id, new_data={"status": "Approved"})
        db.session.commit()
        flash("Purchase approved and stock updated.", "success")
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
    return redirect(url_for("purchases.index"))


@bp.route("/<int:id>/cancel", methods=["POST"])
@login_required
def cancel_purchase(id):
    purchase = Purchase.query.get_or_404(id)
    if purchase.status == "Cancelled":
        flash("Purchase is already cancelled.", "warning")
        return redirect(url_for("purchases.index"))
    if float(purchase.paid_amount or 0) > 0:
        flash("Reverse vendor payments before cancelling a paid purchase.", "warning")
        return redirect(url_for("purchases.index"))
    try:
        for item in purchase.items:
            apply_purchase_return_item(item.product_id, purchase.warehouse_id, item.quantity, item.rate, purchase.id, purchase.purchase_no)
        supplier = purchase.supplier
        supplier.current_balance = float(supplier.current_balance or 0) - float(purchase.balance_amount or 0)
        purchase.status = "Cancelled"
        purchase.cancelled_at = date.today()
        purchase.cancellation_reason = request.form.get("reason")
        purchase.balance_amount = 0
        record_audit("Update", "Purchase", purchase.id, new_data={"status": "Cancelled", "reason": purchase.cancellation_reason})
        db.session.commit()
        flash("Purchase cancelled and stock reversed.", "success")
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
    return redirect(url_for("purchases.index"))


@bp.route("/<int:id>/print")
@login_required
def print_purchase(id):
    purchase = Purchase.query.get_or_404(id)
    return render_template("purchases/print.html", title=f"Purchase {purchase.purchase_no}", purchase=purchase)


@bp.route("/<int:id>/pdf")
@login_required
def purchase_pdf(id):
    purchase = Purchase.query.get_or_404(id)
    pdf = render_pdf("purchases/print.html", purchase=purchase, title=f"Purchase {purchase.purchase_no}")
    return send_file(pdf, mimetype="application/pdf", download_name=f"{purchase.purchase_no}.pdf")


@bp.route("/<int:id>/whatsapp")
@login_required
def whatsapp_purchase(id):
    purchase = Purchase.query.get_or_404(id)
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_ID")
    phone = "".join(ch for ch in (purchase.supplier.phone or "") if ch.isdigit())
    if token and phone_id and phone:
        try:
            pdf = render_pdf("purchases/print.html", purchase=purchase, title=f"Purchase {purchase.purchase_no}")
            media_id = upload_whatsapp_media(token, phone_id, pdf, f"{purchase.purchase_no}.pdf")
            send_whatsapp_document(token, phone_id, phone, media_id, f"{purchase.purchase_no}.pdf", f"Purchase {purchase.purchase_no} - Amount {purchase.grand_total}")
            flash("Purchase sent via WhatsApp", "success")
            return redirect(url_for("purchases.index"))
        except Exception as exc:
            flash(f"WhatsApp send failed: {exc}", "danger")
    purchase_url = url_for("purchases.print_purchase", id=purchase.id, _external=True)
    text = quote_plus(f"Purchase {purchase.purchase_no} amount {purchase.grand_total}. View: {purchase_url}")
    return redirect(f"https://wa.me/{phone}?text={text}" if phone else f"https://wa.me/?text={text}")


@bp.route("/returns")
@login_required
def returns():
    return render_template("purchases/returns.html", title="Purchase Returns", items=PurchaseReturn.query.order_by(PurchaseReturn.id.desc()).all())


@bp.route("/returns/create", methods=["GET", "POST"])
@login_required
def return_create():
    if request.method == "POST":
        try:
            items = parse_return_items()
            totals = calculate_document(items)
            ret = PurchaseReturn(return_no=request.form.get("return_no") or next_number("purchase_return"), return_date=date.fromisoformat(request.form["return_date"]), purchase_id=request.form.get("purchase_id") or None, supplier_id=request.form["supplier_id"], warehouse_id=request.form["warehouse_id"], reason=request.form.get("reason"), refund_mode=request.form.get("refund_mode") or "Debit Note", notes=request.form.get("notes"), created_by=current_user.id, subtotal=totals["subtotal"], tax_total=totals["tax_total"], grand_total=totals["grand_total"])
            db.session.add(ret); db.session.flush()
            supplier = Supplier.query.get(ret.supplier_id)
            balance = supplier.outstanding if supplier else 0
            db.session.add(SupplierLedger(date=ret.return_date, supplier_id=ret.supplier_id, reference_type="PurchaseReturn", reference_id=ret.id, reference_no=ret.return_no, debit=ret.grand_total, credit=0, balance=balance - float(ret.grand_total or 0), narration="Purchase return debit note"))
            vendor_credit = VendorCredit(credit_no=next_number("vendor_credit"), credit_date=ret.return_date, supplier_id=ret.supplier_id, purchase_id=ret.purchase_id, purchase_return_id=ret.id, reason=ret.reason, subtotal=ret.subtotal, tax_total=ret.tax_total, grand_total=ret.grand_total, status="Issued", created_by=current_user.id)
            db.session.add(vendor_credit); db.session.flush()
            for index, item in enumerate(items):
                db.session.add(PurchaseReturnItem(purchase_return_id=ret.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
                db.session.add(VendorCreditItem(vendor_credit_id=vendor_credit.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
                validate_return_tracking(index, item["product_id"])
                apply_purchase_return_item(item["product_id"], ret.warehouse_id, item["quantity"], item["rate"], ret.id, ret.return_no)
            create_journal(ret.return_date, "VendorCredit", vendor_credit.id, f"Vendor credit {vendor_credit.credit_no}", [{"account": account("Accounts Payable"), "debit": ret.grand_total}, {"account": account("Inventory"), "credit": float(ret.grand_total or 0) - float(ret.tax_total or 0)}, {"account": account("Tax Payable"), "credit": ret.tax_total}], current_user.id)
            record_audit("Create", "PurchaseReturn", ret.id, new_data={"return_no": ret.return_no})
            db.session.commit(); flash("Purchase return saved and stock updated.", "success")
            return redirect(url_for("purchases.returns"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("purchases/return_form.html", title="Create Purchase Return", suppliers=Supplier.query.all(), warehouses=Warehouse.query.all(), purchases=Purchase.query.order_by(Purchase.id.desc()).all(), today=date.today(), return_no=next_number("purchase_return"))


@bp.route("/vendor-credits")
@login_required
def vendor_credits():
    return render_template("purchases/vendor_credits.html", title="Vendor Credits", credits=VendorCredit.query.order_by(VendorCredit.id.desc()).all(), purchases=Purchase.query.filter(Purchase.balance_amount > 0).order_by(Purchase.purchase_date.desc()).all())


@bp.route("/vendor-credits/<int:id>/apply", methods=["POST"])
@login_required
def vendor_credit_apply(id):
    credit = VendorCredit.query.get_or_404(id)
    purchase = Purchase.query.get_or_404(request.form["purchase_id"])
    amount = min(float(request.form.get("amount") or 0), float(credit.grand_total or 0) - float(credit.applied_amount or 0) - float(credit.refunded_amount or 0), float(purchase.balance_amount or 0))
    if amount <= 0:
        flash("Enter a valid amount.", "warning")
        return redirect(url_for("purchases.vendor_credits"))
    purchase.paid_amount = float(purchase.paid_amount or 0) + amount
    purchase.update_payment_status()
    credit.applied_amount = float(credit.applied_amount or 0) + amount
    db.session.commit()
    flash("Vendor credit applied.", "success")
    return redirect(url_for("purchases.vendor_credits"))


@bp.route("/vendor-credits/<int:id>/refund", methods=["POST"])
@login_required
def vendor_credit_refund(id):
    credit = VendorCredit.query.get_or_404(id)
    amount = min(float(request.form.get("amount") or 0), float(credit.grand_total or 0) - float(credit.applied_amount or 0) - float(credit.refunded_amount or 0))
    if amount <= 0:
        flash("Enter a valid refund amount.", "warning")
        return redirect(url_for("purchases.vendor_credits"))
    credit.refunded_amount = float(credit.refunded_amount or 0) + amount
    supplier = credit.supplier
    supplier.current_balance = float(supplier.current_balance or 0) + amount
    db.session.add(SupplierLedger(date=date.today(), supplier_id=credit.supplier_id, reference_type="VendorRefund", reference_id=credit.id, reference_no=credit.credit_no, debit=0, credit=amount, balance=supplier.outstanding + amount, narration="Refund from vendor credit"))
    db.session.commit()
    flash("Vendor refund recorded.", "success")
    return redirect(url_for("purchases.vendor_credits"))


def capture_purchase_tracking(index, product_id, warehouse_id, quantity, rate, purchase_id, purchase_no):
    batch_no = request.form.getlist("batch_no[]")[index] if index < len(request.form.getlist("batch_no[]")) else ""
    mfg = request.form.getlist("manufacture_date[]")[index] if index < len(request.form.getlist("manufacture_date[]")) else ""
    exp = request.form.getlist("expiry_date[]")[index] if index < len(request.form.getlist("expiry_date[]")) else ""
    if batch_no:
        batch = Batch.query.filter_by(product_id=product_id, warehouse_id=warehouse_id, batch_no=batch_no).first()
        if not batch:
            batch = Batch(product_id=product_id, warehouse_id=warehouse_id, batch_no=batch_no, manufacture_date=date.fromisoformat(mfg) if mfg else None, expiry_date=date.fromisoformat(exp) if exp else None, purchase_reference=purchase_no, cost=rate or 0, quantity=0)
            db.session.add(batch)
        batch.quantity = float(batch.quantity or 0) + float(quantity or 0)
    serials = request.form.getlist("serial_numbers[]")[index] if index < len(request.form.getlist("serial_numbers[]")) else ""
    for serial in [s.strip() for s in serials.replace("\n", ",").split(",") if s.strip()]:
        if not SerialNumber.query.filter_by(serial_no=serial).first():
            db.session.add(SerialNumber(product_id=product_id, warehouse_id=warehouse_id, serial_no=serial, status="Available", purchase_id=purchase_id))


def validate_return_tracking(index, product_id):
    serials = request.form.getlist("serial_numbers[]")[index] if index < len(request.form.getlist("serial_numbers[]")) else ""
    for serial in [s.strip() for s in serials.replace("\n", ",").split(",") if s.strip()]:
        record = SerialNumber.query.filter_by(product_id=product_id, serial_no=serial).first()
        if record:
            record.status = "Returned"


def upload_whatsapp_media(token, phone_id, pdf_file, filename):
    response = requests.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/media",
        headers={"Authorization": f"Bearer {token}"},
        data={"messaging_product": "whatsapp", "type": "application/pdf"},
        files={"file": (filename, pdf_file.getvalue(), "application/pdf")},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["id"]


def send_whatsapp_document(token, phone_id, phone, media_id, filename, caption):
    response = requests.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": phone, "type": "document", "document": {"id": media_id, "filename": filename, "caption": caption}},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def apply_purchase_tds(purchase):
    supplier = purchase.supplier
    section = supplier.tds_section if supplier and supplier.tds_applicable else None
    if not section:
        return
    base = float(purchase.grand_total or 0)
    if base <= float(section.threshold_amount or 0):
        return
    rate = float(section.default_rate or 0)
    amount = round(base * rate / 100, 2)
    purchase.balance_amount = float(purchase.balance_amount or purchase.grand_total or 0) - amount
    db.session.add(TDSEntry(
        entry_date=purchase.purchase_date,
        party_type="Supplier",
        party_id=purchase.supplier_id,
        reference_type="Purchase",
        reference_id=purchase.id,
        reference_no=purchase.purchase_no,
        section_id=section.id,
        base_amount=base,
        tds_rate=rate,
        tds_amount=amount,
        status="Deducted",
        created_by=current_user.id,
    ))


def create_or_update_itc_entry(purchase):
    if float(purchase.tax_total or 0) <= 0:
        return None
    entry = ITCEntry.query.filter_by(purchase_id=purchase.id).first() or ITCEntry(purchase_id=purchase.id, supplier_id=purchase.supplier_id)
    tax_total = float(purchase.tax_total or 0)
    taxable = float(purchase.subtotal or 0) - float(purchase.discount_total or 0)
    entry.supplier_id = purchase.supplier_id
    entry.invoice_no = purchase.supplier_invoice_no or purchase.purchase_no
    entry.invoice_date = purchase.supplier_invoice_date or purchase.purchase_date
    entry.taxable_value = taxable
    entry.input_tax_cgst = tax_total / 2
    entry.input_tax_sgst = tax_total / 2
    entry.input_tax_igst = 0
    entry.input_tax_vat = 0
    entry.eligible_itc_amount = tax_total
    entry.blocked_itc_amount = 0
    entry.itc_status = entry.itc_status or "Eligible"
    entry.claim_period = purchase.purchase_date.strftime("%Y-%m") if purchase.purchase_date else None
    db.session.add(entry)
    return entry
