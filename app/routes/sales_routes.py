import base64
import hashlib
import os
from datetime import date, datetime, timedelta
from io import BytesIO

from urllib.parse import quote_plus

import qrcode
import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, render_template_string, send_file, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Currency, CreditNote, CreditNoteItem, Customer, CustomerLedger, DeliveryBill, DeliveryChallan, DeliveryChallanItem, EWayBill, Package, PackageItem, Picklist, PicklistItem, PrintTemplate, Product, ProformaInvoice, ProformaInvoiceItem, PurchaseOrder, PurchaseOrderItem, Quotation, QuotationItem, Refund, Sale, SaleItem, SalesOrder, SalesOrderItem, SalesReturn, SalesReturnItem, Warehouse
from app.services.accounting_service import post_sale
from app.services.audit_service import record_audit
from app.services.document_service import e_invoice_payload, hsn_summary
from app.services.communication_service import send_invoice_email, send_message
from app.services.invoice_service import calculate_document, line_totals
from app.services.numbering_service import next_number
from app.services.stock_service import apply_sale_item, apply_sales_return_item
from app.utils.pdf_generator import render_pdf

bp = Blueprint("sales", __name__, url_prefix="/sales")


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


def create_sale_from_order(order):
    sale = Sale(
        invoice_no=next_number("sales"),
        invoice_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        customer_id=order.customer_id,
        warehouse_id=order.warehouse_id,
        sale_type="Credit",
        status="Draft",
        subtotal=order.subtotal,
        discount_total=order.discount_total,
        tax_total=order.tax_total,
        grand_total=order.grand_total,
        paid_amount=0,
        balance_amount=order.grand_total,
        payment_status="Unpaid",
        notes=f"Converted from Sales Order {order.order_no}",
        created_by=current_user.id,
    )
    db.session.add(sale)
    db.session.flush()
    for item in order.items:
        db.session.add(SaleItem(sale_id=sale.id, product_id=item.product_id, quantity=item.quantity, rate=item.rate, discount=item.discount, discount_amount=0, tax_rate=item.tax_rate, tax_amount=item.tax_amount, line_total=item.line_total, cost_price=0))
    order.status = "Converted"
    return sale


def create_delivery_bill(customer_id, sale_id=None, order_id=None, address=None):
    bill = DeliveryBill(
        delivery_no=next_number("delivery_bill"),
        sale_id=sale_id,
        sales_order_id=order_id,
        customer_id=customer_id,
        delivery_status="Pending",
        delivery_address=address,
        created_by=current_user.id,
    )
    db.session.add(bill)
    return bill


def build_picklist(source, source_type):
    if source_type == "order":
        items = source.items
        customer_id = source.customer_id
        warehouse_id = source.warehouse_id
        kwargs = {"sales_order_id": source.id}
    else:
        items = source.items
        customer_id = source.customer_id
        warehouse_id = source.warehouse_id
        kwargs = {"sale_id": source.id}
    picklist = Picklist(picklist_no=next_number("picklist"), warehouse_id=warehouse_id, created_by=current_user.id, **kwargs)
    db.session.add(picklist)
    db.session.flush()
    for item in items:
        db.session.add(PicklistItem(picklist_id=picklist.id, product_id=item.product_id, quantity=item.quantity, picked_qty=0, is_picked=False))
    return picklist


def save_sales_doc(model, item_model, number_field, date_field, kind):
    items = parse_items()
    totals = calculate_document(items)
    number_kind = {"quotation": "quotations", "proforma": "proforma"}.get(kind, kind)
    doc = model(
        **{
            number_field: request.form.get(number_field) or next_number(number_kind),
            date_field: date.fromisoformat(request.form[date_field]),
            "customer_id": request.form["customer_id"],
            "notes": request.form.get("notes"),
            "terms": request.form.get("terms"),
            "created_by": current_user.id,
            **totals,
        }
    )
    if hasattr(doc, "valid_until"):
        doc.valid_until = date.fromisoformat(request.form["valid_until"]) if request.form.get("valid_until") else None
    db.session.add(doc)
    db.session.flush()
    parent_id_field = f"{kind}_id" if kind != "proforma" else "proforma_id"
    for item in items:
        item_data = {parent_id_field: doc.id, "product_id": item["product_id"], "quantity": item["quantity"], "rate": item["rate"], "tax_rate": item["tax_rate"], "tax_amount": item["tax_amount"], "line_total": item["line_total"]}
        if "discount" in item_model.__table__.columns:
            item_data["discount"] = item.get("discount", 0)
        db.session.add(item_model(**item_data))
    return doc


@bp.route("/")
@login_required
def index():
    return render_template("sales/index.html", title="Sales Invoices", sales=Sale.query.order_by(Sale.id.desc()).all())


@bp.route("/orders")
@login_required
def orders():
    return render_template("sales/orders.html", title="Sales Orders", orders=SalesOrder.query.order_by(SalesOrder.id.desc()).all())


@bp.route("/orders/create", methods=["GET", "POST"])
@login_required
def order_create():
    if request.method == "POST":
        try:
            items = parse_items()
            totals = calculate_document(items)
            order = SalesOrder(
                order_no=request.form.get("order_no") or next_number("sales_order"),
                order_date=date.fromisoformat(request.form["order_date"]),
                customer_id=request.form["customer_id"],
                warehouse_id=request.form["warehouse_id"],
                expected_date=date.fromisoformat(request.form["expected_date"]) if request.form.get("expected_date") else None,
                status=request.form.get("status") or "Draft",
                notes=request.form.get("notes"),
                created_by=current_user.id,
                subtotal=totals["subtotal"],
                discount_total=totals["discount_total"],
                tax_total=totals["tax_total"],
                grand_total=totals["grand_total"],
            )
            db.session.add(order)
            db.session.flush()
            for item in items:
                product = Product.query.get(item["product_id"])
                backorder = max(0, float(item["quantity"]) - float(product.current_stock or 0)) if product else 0
                db.session.add(SalesOrderItem(order_id=order.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], discount=item["discount"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"], backorder_qty=backorder))
            if any(float(item.backorder_qty or 0) > 0 for item in order.items):
                order.status = "Backordered"
            record_audit("Create", "SalesOrder", order.id, new_data={"order_no": order.order_no})
            db.session.commit()
            flash("Sales order saved.", "success")
            return redirect(url_for("sales.orders"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("sales/order_form.html", title="Create Sales Order", order_no=next_number("sales_order"), today=date.today(), customers=Customer.query.order_by(Customer.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all())


@bp.route("/orders/<int:id>")
@login_required
def order_detail(id):
    return render_template("sales/order_detail.html", title="Sales Order", order=SalesOrder.query.get_or_404(id))


@bp.route("/orders/<int:id>/convert-invoice", methods=["POST"])
@login_required
def order_convert_invoice(id):
    order = SalesOrder.query.get_or_404(id)
    try:
        sale = create_sale_from_order(order)
        record_audit("Create", "Sale", sale.id, new_data={"source_order": order.order_no, "invoice_no": sale.invoice_no})
        db.session.commit()
        flash(f"Sales order converted to Invoice {sale.invoice_no}.", "success")
        return redirect(url_for("invoices.detail", id=sale.id))
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("sales.order_detail", id=order.id))


@bp.route("/orders/<int:id>/delivery-bill", methods=["POST"])
@login_required
def order_delivery_bill(id):
    order = SalesOrder.query.get_or_404(id)
    bill = create_delivery_bill(order.customer_id, order_id=order.id, address=request.form.get("delivery_address") or getattr(order.customer, "shipping_address", None))
    order.status = "Delivery Pending"
    record_audit("Create", "DeliveryBill", None, new_data={"source_order": order.order_no})
    db.session.commit()
    flash(f"Delivery bill {bill.delivery_no} created.", "success")
    return redirect(url_for("sales.delivery_bills"))


@bp.route("/orders/<int:id>/purchase-order", methods=["POST"])
@login_required
def order_purchase_order(id):
    order = SalesOrder.query.get_or_404(id)
    shortage_items = [item for item in order.items if float(item.backorder_qty or 0) > 0]
    if not shortage_items:
        flash("No backordered items found for this sales order.", "info")
        return redirect(url_for("sales.order_detail", id=order.id))
    supplier_id = None
    for item in shortage_items:
        supplier_id = supplier_id or getattr(item.product, "preferred_supplier_id", None)
    if not supplier_id:
        flash("Set a preferred vendor on at least one backordered product before creating a purchase order.", "warning")
        return redirect(url_for("sales.order_detail", id=order.id))
    po_items = []
    for item in shortage_items:
        qty = item.backorder_qty
        totals = line_totals(qty, item.rate, 0, item.tax_rate)
        po_items.append({"product_id": item.product_id, "quantity": qty, "rate": item.rate, "tax_rate": item.tax_rate, **totals})
    totals = calculate_document(po_items)
    po = PurchaseOrder(po_no=next_number("purchase_order"), po_date=date.today(), supplier_id=supplier_id, warehouse_id=order.warehouse_id, status="Draft", subtotal=totals["subtotal"], tax_total=totals["tax_total"], grand_total=totals["grand_total"], notes=f"Created from Sales Order {order.order_no}", created_by=current_user.id)
    db.session.add(po)
    db.session.flush()
    for item in po_items:
        db.session.add(PurchaseOrderItem(po_id=po.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
    order.status = "PO Created"
    db.session.commit()
    flash(f"Purchase order {po.po_no} created for backordered items.", "success")
    return redirect(url_for("purchase_orders.detail", id=po.id))


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        try:
            items = parse_items()
            totals = calculate_document(items, shipping=request.form.get("shipping_charges"), round_off=request.form.get("round_off"), paid=request.form.get("paid_amount"))
            currency = Currency.query.get(request.form.get("currency_id")) if request.form.get("currency_id") else Currency.query.filter_by(is_base=True).first()
            exchange_rate = float(request.form.get("exchange_rate_snapshot") or (currency.exchange_rate if currency else 1) or 1)
            original_total = totals["grand_total"]
            if exchange_rate != 1:
                for key in ["subtotal", "discount_total", "tax_total", "grand_total", "paid_amount", "balance_amount"]:
                    totals[key] = float(totals[key] or 0) * exchange_rate
                for item in items:
                    for key in ["rate", "gross", "discount_amount", "tax_amount", "line_total"]:
                        item[key] = float(item[key] or 0) * exchange_rate
            sale = Sale(invoice_no=request.form.get("invoice_no") or next_number("sales"), invoice_date=date.fromisoformat(request.form["invoice_date"]), due_date=date.fromisoformat(request.form["due_date"]) if request.form.get("due_date") else None, customer_id=request.form["customer_id"], warehouse_id=request.form["warehouse_id"], currency_id=currency.id if currency else None, exchange_rate_snapshot=exchange_rate, original_currency_total=original_total, sale_type=request.form.get("sale_type") or "Credit", notes=request.form.get("notes"), terms=request.form.get("terms"), created_by=current_user.id, issued_at=datetime.utcnow(), **totals)
            sale.update_payment_status()
            db.session.add(sale); db.session.flush()
            for item in items:
                cost = apply_sale_item(item["product_id"], sale.warehouse_id, item["quantity"], sale.id, sale.invoice_no)
                db.session.add(SaleItem(sale_id=sale.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], discount=item["discount"], discount_amount=item["discount_amount"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"], cost_price=cost))
            post_sale(sale, current_user.id)
            db.session.commit()
            flash("Sales invoice saved and stock updated.", "success")
            return redirect(url_for("sales.index"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("sales/form.html", title="Create Sales Invoice", customers=Customer.query.all(), warehouses=Warehouse.query.all(), currencies=Currency.query.order_by(Currency.code).all(), today=date.today(), invoice_no=next_number("sales"))


@bp.route("/<int:id>/print")
@login_required
def print_sale(id):
    sale = Sale.query.get_or_404(id)
    template = PrintTemplate.query.filter_by(template_type="sales_invoice", is_default=True).first()
    if template and template.html:
        return render_template_string(template.html, title=f"Invoice {sale.invoice_no}", invoice=sale, sale=sale, items=sale.items, hsn_rows=hsn_summary(sale), qr_image=qr_data_uri(sale.qr_code_data), eway=sale.eway_bills.order_by(EWayBill.id.desc()).first())
    return render_template("sales/print.html", title=f"Invoice {sale.invoice_no}", sale=sale, hsn_rows=hsn_summary(sale), qr_image=qr_data_uri(sale.qr_code_data), eway=sale.eway_bills.order_by(EWayBill.id.desc()).first())


@bp.route("/<int:id>/pdf")
@login_required
def sale_pdf(id):
    sale = Sale.query.get_or_404(id)
    pdf = render_pdf("sales/print.html", sale=sale, title=f"Invoice {sale.invoice_no}", qr_image=qr_data_uri(sale.qr_code_data), eway=sale.eway_bills.order_by(EWayBill.id.desc()).first())
    return send_file(pdf, mimetype="application/pdf", download_name=f"{sale.invoice_no}.pdf")


@bp.route("/<int:id>/e-invoice.json")
@login_required
def e_invoice_json(id):
    from app.models import CompanySetting

    sale = Sale.query.get_or_404(id)
    return jsonify(e_invoice_payload(sale, CompanySetting.query.first()))


@bp.route("/<int:id>/email")
@login_required
def email_invoice(id):
    sale = Sale.query.get_or_404(id)
    pdf = render_pdf("sales/print.html", sale=sale, title=f"Invoice {sale.invoice_no}", qr_image=qr_data_uri(sale.qr_code_data), eway=sale.eway_bills.order_by(EWayBill.id.desc()).first())
    log = send_invoice_email(sale, attachment_bytes=pdf)
    flash("Invoice email sent." if log.status in {"Sent", "Mock Sent"} else log.status, "success" if log.status in {"Sent", "Mock Sent"} else "warning")
    return redirect(url_for("sales.print_sale", id=sale.id))


@bp.route("/<int:id>/receipt-email")
@login_required
def email_receipt(id):
    sale = Sale.query.get_or_404(id)
    log = send_message("email", sale.customer.email or "", f"Receipt for {sale.invoice_no}", f"Payment receipt for invoice {sale.invoice_no}.", "receipt", sale.id)
    flash("Receipt email sent." if log.status in {"Sent", "Mock Sent"} else log.status, "success" if log.status in {"Sent", "Mock Sent"} else "warning")
    return redirect(url_for("sales.print_sale", id=sale.id))


@bp.route("/<int:id>/whatsapp")
@login_required
def whatsapp_invoice(id):
    sale = Sale.query.get_or_404(id)
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_ID")
    phone = "".join(ch for ch in (sale.customer.phone or "") if ch.isdigit())
    if token and phone_id and phone:
        try:
            pdf = render_pdf("sales/print.html", sale=sale, title=f"Invoice {sale.invoice_no}", qr_image=qr_data_uri(sale.qr_code_data), eway=sale.eway_bills.order_by(EWayBill.id.desc()).first())
            media_id = upload_whatsapp_media(token, phone_id, pdf, f"{sale.invoice_no}.pdf")
            send_whatsapp_document(token, phone_id, phone, media_id, f"Invoice {sale.invoice_no}.pdf", f"Invoice {sale.invoice_no} - Amount {sale.grand_total}")
            flash("Invoice sent via WhatsApp", "success")
            return redirect(url_for("sales.index"))
        except Exception as exc:
            flash(f"WhatsApp send failed: {exc}", "danger")
    invoice_url = url_for("sales.print_sale", id=sale.id, _external=True)
    text = quote_plus(f"Invoice {sale.invoice_no} amount {sale.grand_total}. View: {invoice_url}")
    return redirect(f"https://wa.me/{phone}?text={text}" if phone else f"https://wa.me/?text={text}")


@bp.route("/<int:id>/generate-irn", methods=["POST"])
@login_required
def generate_irn(id):
    sale = Sale.query.get_or_404(id)
    client_id = os.environ.get("E_INVOICE_CLIENT_ID")
    client_secret = os.environ.get("E_INVOICE_CLIENT_SECRET")
    base_url = os.environ.get("E_INVOICE_URL", "https://einv-apisandbox.nic.in").rstrip("/")
    ack_dt = datetime.utcnow()
    try:
        if client_id and client_secret:
            from app.models import CompanySetting

            response = requests.post(
                f"{base_url}/eicore/v1.03/Invoice",
                json=e_invoice_payload(sale, CompanySetting.query.first()),
                headers={"client_id": client_id, "client_secret": client_secret, "Content-Type": "application/json"},
                timeout=20,
            )
            response.raise_for_status()
            data = response.json().get("Data") or response.json()
            sale.irn = data.get("Irn") or data.get("irn")
            sale.irn_ack_no = str(data.get("AckNo") or data.get("ack_no") or "")
            sale.qr_code_data = data.get("SignedQRCode") or data.get("qr_code_data") or sale.irn
        else:
            sale.irn = "MOCK-" + hashlib.sha256(sale.invoice_no.encode()).hexdigest()[:20]
            sale.irn_ack_no = "MOCK-" + datetime.utcnow().strftime("%Y%m%d%H%M%S")
            sale.qr_code_data = f"IRN:{sale.irn}|INV:{sale.invoice_no}|AMT:{sale.grand_total}"
        sale.irn_ack_dt = ack_dt
        sale.e_invoice_status = "Generated"
        db.session.commit()
        flash(f"IRN generated for {sale.invoice_no}.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"IRN generation failed: {exc}", "danger")
    return redirect(url_for("sales.index"))


@bp.route("/<int:id>/eway-bill", methods=["GET", "POST"])
@login_required
def eway_bill(id):
    sale = Sale.query.get_or_404(id)
    if request.method == "POST":
        try:
            ewb_no = request_eway_bill(sale)
            bill = EWayBill(
                sale_id=sale.id,
                ewb_no=ewb_no,
                ewb_date=datetime.utcnow(),
                valid_upto=datetime.utcnow() + timedelta(days=1),
                vehicle_no=request.form.get("vehicle_no"),
                transporter_name=request.form.get("transporter_name"),
                transporter_id=request.form.get("transporter_id"),
                supply_type=request.form.get("supply_type") or "Outward",
                sub_type=request.form.get("sub_type") or "Supply",
                distance_km=request.form.get("distance_km") or 0,
                status="Generated",
            )
            db.session.add(bill)
            db.session.commit()
            flash(f"E-Way Bill {bill.ewb_no} generated.", "success")
            return redirect(url_for("sales.index"))
        except Exception as exc:
            db.session.rollback()
            flash(f"E-Way Bill generation failed: {exc}", "danger")
    return render_template("sales/eway_bill.html", title=f"E-Way Bill {sale.invoice_no}", sale=sale)


@bp.route("/<int:id>/packing-slip")
@login_required
def packing_slip(id):
    sale = Sale.query.get_or_404(id)
    return render_template("sales/packing_slip.html", title=f"Packing Slip {sale.invoice_no}", sale=sale)


@bp.route("/<int:id>/shipping-label")
@login_required
def shipping_label(id):
    sale = Sale.query.get_or_404(id)
    return render_template("sales/shipping_label.html", title=f"Shipping Label {sale.invoice_no}", sale=sale)


@bp.route("/returns")
@login_required
def returns():
    return render_template("sales/returns.html", title="Sales Returns", items=SalesReturn.query.order_by(SalesReturn.id.desc()).all())


@bp.route("/returns/create", methods=["GET", "POST"])
@login_required
def return_create():
    if request.method == "POST":
        try:
            items = parse_return_items()
            totals = calculate_document(items)
            ret = SalesReturn(return_no=request.form.get("return_no") or next_number("sales_return"), return_date=date.fromisoformat(request.form["return_date"]), sale_id=request.form.get("sale_id") or None, customer_id=request.form["customer_id"], warehouse_id=request.form["warehouse_id"], reason=request.form.get("reason"), restock=bool(request.form.get("restock")), status="Approved" if request.form.get("sale_id") else "Pending Approval", refund_mode=request.form.get("refund_mode") or "Credit Note", notes=request.form.get("notes"), created_by=current_user.id, subtotal=totals["subtotal"], tax_total=totals["tax_total"], grand_total=totals["grand_total"])
            db.session.add(ret); db.session.flush()
            balance = ret.sales_return_customer.outstanding - float(ret.grand_total or 0)
            db.session.add(CustomerLedger(date=ret.return_date, customer_id=ret.customer_id, reference_type="SalesReturn", reference_id=ret.id, reference_no=ret.return_no, debit=0, credit=ret.grand_total, balance=balance, narration="Sales return credit note"))
            credit_note = CreditNote(cn_no=next_number("credit_note"), cn_date=ret.return_date, customer_id=ret.customer_id, sale_id=ret.sale_id, reason=ret.reason, adjustment_type="Return", status="Issued", created_by=current_user.id, subtotal=ret.subtotal, tax_total=ret.tax_total, grand_total=ret.grand_total)
            db.session.add(credit_note); db.session.flush()
            for item in items:
                db.session.add(SalesReturnItem(sales_return_id=ret.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
                db.session.add(CreditNoteItem(cn_id=credit_note.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
                if ret.restock and ret.status == "Approved":
                    apply_sales_return_item(item["product_id"], ret.warehouse_id, item["quantity"], item["rate"], ret.id, ret.return_no)
            record_audit("Create", "SalesReturn", ret.id, new_data={"return_no": ret.return_no, "restock": ret.restock})
            db.session.commit(); flash("Sales return saved and credit note generated.", "success")
            return redirect(url_for("sales.returns"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("sales/return_form.html", title="Create Sales Return", customers=Customer.query.all(), warehouses=Warehouse.query.all(), sales=Sale.query.order_by(Sale.id.desc()).all(), today=date.today(), return_no=next_number("sales_return"))


@bp.route("/refunds", methods=["GET", "POST"])
@login_required
def refunds():
    if request.method == "POST":
        try:
            amount = float(request.form.get("amount") or 0)
            limit = float(os.environ.get("REFUND_APPROVAL_LIMIT", "10000"))
            refund = Refund(
                refund_no=request.form.get("refund_no") or next_number("refund"),
                refund_date=date.fromisoformat(request.form["refund_date"]),
                customer_id=request.form["customer_id"],
                credit_note_id=request.form.get("credit_note_id") or None,
                sale_return_id=request.form.get("sale_return_id") or None,
                amount=amount,
                refund_mode=request.form.get("refund_mode") or "Cash",
                reference_no=request.form.get("reference_no"),
                approval_status="Pending Approval" if amount > limit else "Approved",
                notes=request.form.get("notes"),
                created_by=current_user.id,
            )
            db.session.add(refund)
            if refund.credit_note_id:
                note = CreditNote.query.get(refund.credit_note_id)
                note.refunded_amount = float(note.refunded_amount or 0) + amount
            customer = Customer.query.get(refund.customer_id)
            customer.current_balance = float(customer.current_balance or 0) + amount
            db.session.add(CustomerLedger(date=refund.refund_date, customer_id=refund.customer_id, reference_type="Refund", reference_id=refund.id, reference_no=refund.refund_no, debit=amount, credit=0, balance=customer.outstanding + amount, narration="Customer refund"))
            record_audit("Payment Update", "Refund", refund.id, new_data={"refund_no": refund.refund_no, "amount": str(refund.amount)})
            db.session.commit()
            flash("Refund saved.", "success")
            return redirect(url_for("sales.refunds"))
        except Exception as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("sales/refunds.html", title="Refunds", refunds=Refund.query.order_by(Refund.id.desc()).all(), customers=Customer.query.order_by(Customer.name).all(), credit_notes=CreditNote.query.order_by(CreditNote.id.desc()).all(), returns=SalesReturn.query.order_by(SalesReturn.id.desc()).all(), refund_no=next_number("refund"), today=date.today())


@bp.route("/delivery-bills")
@login_required
def delivery_bills():
    return render_template("sales/delivery_bills.html", title="Delivery Bills", bills=DeliveryBill.query.order_by(DeliveryBill.id.desc()).all())


@bp.route("/delivery-bills/<int:id>/status", methods=["POST"])
@login_required
def delivery_bill_status(id):
    bill = DeliveryBill.query.get_or_404(id)
    bill.delivery_status = request.form.get("delivery_status") or bill.delivery_status
    bill.delivery_person = request.form.get("delivery_person") or bill.delivery_person
    bill.delivery_date = date.fromisoformat(request.form["delivery_date"]) if request.form.get("delivery_date") else bill.delivery_date
    bill.remarks = request.form.get("remarks") or bill.remarks
    record_audit("Update", "DeliveryBill", bill.id, new_data={"status": bill.delivery_status})
    db.session.commit()
    flash("Delivery status updated.", "success")
    return redirect(url_for("sales.delivery_bills"))


@bp.route("/<int:id>/delivery-bill", methods=["POST"])
@login_required
def sale_delivery_bill(id):
    sale = Sale.query.get_or_404(id)
    bill = create_delivery_bill(sale.customer_id, sale_id=sale.id, address=request.form.get("delivery_address") or getattr(sale.customer, "shipping_address", None))
    record_audit("Create", "DeliveryBill", bill.id, new_data={"invoice_no": sale.invoice_no})
    db.session.commit()
    flash(f"Delivery bill {bill.delivery_no} created.", "success")
    return redirect(url_for("sales.delivery_bills"))


@bp.route("/picklists")
@login_required
def picklists():
    return render_template("sales/picklists.html", title="Picklists", picklists=Picklist.query.order_by(Picklist.id.desc()).all(), sales=Sale.query.order_by(Sale.id.desc()).limit(100).all(), orders=SalesOrder.query.order_by(SalesOrder.id.desc()).limit(100).all())


@bp.route("/picklists/create", methods=["POST"])
@login_required
def picklist_create():
    try:
        if request.form.get("sale_id"):
            source = Sale.query.get_or_404(request.form["sale_id"])
            picklist = build_picklist(source, "sale")
        else:
            source = SalesOrder.query.get_or_404(request.form["sales_order_id"])
            picklist = build_picklist(source, "order")
        db.session.commit()
        flash(f"Picklist {picklist.picklist_no} created.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("sales.picklists"))


@bp.route("/picklists/<int:id>/mark-picked", methods=["POST"])
@login_required
def picklist_mark_picked(id):
    picklist = Picklist.query.get_or_404(id)
    for item in picklist.items:
        picked = request.form.get(f"picked_{item.id}")
        item.picked_qty = picked if picked not in [None, ""] else item.quantity
        item.is_picked = float(item.picked_qty or 0) >= float(item.quantity or 0)
    picklist.status = "Picked" if all(item.is_picked for item in picklist.items) else "Partially Picked"
    record_audit("Update", "Picklist", picklist.id, new_data={"status": picklist.status})
    db.session.commit()
    flash("Picklist updated.", "success")
    return redirect(url_for("sales.picklists"))


@bp.route("/packages")
@login_required
def packages():
    return render_template("sales/packages.html", title="Packages", packages=Package.query.order_by(Package.id.desc()).all(), picklists=Picklist.query.order_by(Picklist.id.desc()).all())


@bp.route("/packages/create-from-picklist/<int:id>", methods=["POST"])
@login_required
def package_create_from_picklist(id):
    picklist = Picklist.query.get_or_404(id)
    customer_id = picklist.sale.customer_id if picklist.sale else picklist.sales_order.customer_id
    package = Package(package_no=next_number("package"), picklist_id=picklist.id, sale_id=picklist.sale_id, customer_id=customer_id, weight=request.form.get("weight") or 0, remarks=request.form.get("remarks"), created_by=current_user.id)
    db.session.add(package)
    db.session.flush()
    for item in picklist.items:
        qty = item.picked_qty or item.quantity
        if float(qty or 0) > 0:
            db.session.add(PackageItem(package_id=package.id, product_id=item.product_id, quantity=qty))
    picklist.status = "Packed"
    db.session.commit()
    flash(f"Package {package.package_no} created.", "success")
    return redirect(url_for("sales.packages"))


@bp.route("/packages/<int:id>/packing-slip")
@login_required
def package_packing_slip(id):
    return render_template("sales/package_slip.html", title="Packing Slip", package=Package.query.get_or_404(id))


@bp.route("/quotations")
@login_required
def quotations():
    return render_template("sales/simple_docs.html", title="Quotations", items=Quotation.query.order_by(Quotation.id.desc()).all(), no_field="quotation_no", create_endpoint="sales.quotation_create")


@bp.route("/quotations/create", methods=["GET", "POST"])
@login_required
def quotation_create():
    if request.method == "POST":
        try:
            save_sales_doc(Quotation, QuotationItem, "quotation_no", "quotation_date", "quotation")
            db.session.commit(); flash("Quotation saved.", "success")
            return redirect(url_for("sales.quotations"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("sales/doc_form.html", title="Create Quotation", no_name="quotation_no", date_name="quotation_date", doc_no=next_number("quotations"), customers=Customer.query.all(), today=date.today(), show_valid_until=True)


@bp.route("/quotations/<int:id>/convert", methods=["POST"])
@login_required
def quotation_convert(id):
    quotation = Quotation.query.get_or_404(id)
    sale = convert_document_to_sale(quotation, quotation.items, quotation.quotation_no)
    quotation.status = "Converted"
    db.session.commit()
    flash(f"Quotation converted to Invoice {sale.invoice_no}", "success")
    return redirect(url_for("invoices.detail", id=sale.id))


@bp.route("/proforma")
@login_required
def proforma():
    return render_template("sales/simple_docs.html", title="Proforma Invoices", items=ProformaInvoice.query.order_by(ProformaInvoice.id.desc()).all(), no_field="proforma_no", create_endpoint="sales.proforma_create")


@bp.route("/proforma/create", methods=["GET", "POST"])
@login_required
def proforma_create():
    if request.method == "POST":
        try:
            save_sales_doc(ProformaInvoice, ProformaInvoiceItem, "proforma_no", "proforma_date", "proforma")
            db.session.commit(); flash("Proforma invoice saved.", "success")
            return redirect(url_for("sales.proforma"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("sales/doc_form.html", title="Create Proforma Invoice", no_name="proforma_no", date_name="proforma_date", doc_no=next_number("proforma"), customers=Customer.query.all(), today=date.today(), show_valid_until=False)


@bp.route("/proforma/<int:id>/convert", methods=["POST"])
@login_required
def proforma_convert(id):
    proforma = ProformaInvoice.query.get_or_404(id)
    sale = convert_document_to_sale(proforma, proforma.items, proforma.proforma_no)
    proforma.status = "Converted"
    db.session.commit()
    flash(f"Proforma converted to Invoice {sale.invoice_no}", "success")
    return redirect(url_for("invoices.detail", id=sale.id))


@bp.route("/challans")
@login_required
def challans():
    return render_template("sales/simple_docs.html", title="Delivery Challans", items=DeliveryChallan.query.order_by(DeliveryChallan.id.desc()).all(), no_field="challan_no", create_endpoint="sales.challan_create")


@bp.route("/challans/create", methods=["GET", "POST"])
@login_required
def challan_create():
    if request.method == "POST":
        try:
            challan = DeliveryChallan(challan_no=request.form.get("challan_no") or next_number("challan"), challan_date=date.fromisoformat(request.form["challan_date"]), customer_id=request.form["customer_id"], delivery_address=request.form.get("delivery_address"), vehicle_no=request.form.get("vehicle_no"), driver_name=request.form.get("driver_name"), notes=request.form.get("notes"), created_by=current_user.id)
            db.session.add(challan); db.session.flush()
            for product_id, quantity, note in zip(request.form.getlist("product_id[]"), request.form.getlist("quantity[]"), request.form.getlist("notes[]")):
                if product_id:
                    db.session.add(DeliveryChallanItem(challan_id=challan.id, product_id=product_id, quantity=quantity or 0, notes=note))
            db.session.commit(); flash("Delivery challan saved.", "success")
            return redirect(url_for("sales.challans"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("sales/challan_form.html", title="Create Delivery Challan", customers=Customer.query.all(), products=Product.query.order_by(Product.name).all(), today=date.today(), challan_no=next_number("challan"))


def qr_data_uri(data):
    if not data:
        return None
    image = qrcode.make(data)
    output = BytesIO()
    image.save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def convert_document_to_sale(document, items, source_no):
    warehouse = Warehouse.query.first()
    if not warehouse:
        raise ValueError("Create a warehouse before converting to invoice.")
    sale = Sale(
        invoice_no=next_number("sales"),
        invoice_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        customer_id=document.customer_id,
        warehouse_id=warehouse.id,
        sale_type="Credit",
        status="Draft",
        subtotal=document.subtotal,
        discount_total=getattr(document, "discount_total", 0) or 0,
        tax_total=document.tax_total,
        grand_total=document.grand_total,
        paid_amount=0,
        balance_amount=document.grand_total,
        payment_status="Unpaid",
        notes=f"Converted from {source_no}",
        terms=document.terms,
        created_by=current_user.id,
    )
    db.session.add(sale); db.session.flush()
    for item in items:
        db.session.add(SaleItem(sale_id=sale.id, product_id=item.product_id, quantity=item.quantity, rate=item.rate, discount=getattr(item, "discount", 0) or 0, discount_amount=0, tax_rate=item.tax_rate, tax_amount=item.tax_amount, line_total=item.line_total, cost_price=0))
    return sale


def request_eway_bill(sale):
    base_url = os.environ.get("EWB_URL", "").rstrip("/")
    client_id = os.environ.get("EWB_CLIENT_ID")
    if not base_url or not client_id:
        return "EWB" + datetime.utcnow().strftime("%Y%m%d%H%M%S")
    payload = {
        "supplyType": request.form.get("supply_type") or "Outward",
        "subSupplyType": request.form.get("sub_type") or "Supply",
        "docNo": sale.invoice_no,
        "docDate": sale.invoice_date.strftime("%d/%m/%Y"),
        "fromGstin": "",
        "toGstin": sale.customer.gst_number or "URP",
        "totalValue": float(sale.grand_total or 0),
        "vehicleNo": request.form.get("vehicle_no"),
        "transporterName": request.form.get("transporter_name"),
        "transporterId": request.form.get("transporter_id"),
        "transDistance": request.form.get("distance_km") or "0",
    }
    response = requests.post(f"{base_url}/ewaybillapi/v1.03/ewayapi/genewaybill", json=payload, headers={"client_id": client_id}, timeout=20)
    response.raise_for_status()
    data = response.json().get("data") or response.json()
    return str(data.get("ewayBillNo") or data.get("ewb_no") or data.get("EwbNo"))


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
