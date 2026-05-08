from datetime import date

from urllib.parse import quote_plus

from flask import Blueprint, flash, jsonify, redirect, render_template, send_file, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Customer, CustomerLedger, DeliveryChallan, DeliveryChallanItem, Product, ProformaInvoice, ProformaInvoiceItem, Quotation, QuotationItem, Sale, SaleItem, SalesReturn, SalesReturnItem, Warehouse
from app.services.accounting_service import post_sale
from app.services.document_service import e_invoice_payload, hsn_summary
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


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        try:
            items = parse_items()
            totals = calculate_document(items, shipping=request.form.get("shipping_charges"), round_off=request.form.get("round_off"), paid=request.form.get("paid_amount"))
            sale = Sale(invoice_no=request.form.get("invoice_no") or next_number("sales"), invoice_date=date.fromisoformat(request.form["invoice_date"]), customer_id=request.form["customer_id"], warehouse_id=request.form["warehouse_id"], sale_type=request.form.get("sale_type") or "Credit", notes=request.form.get("notes"), terms=request.form.get("terms"), created_by=current_user.id, **totals)
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
    return render_template("sales/form.html", title="Create Sales Invoice", customers=Customer.query.all(), warehouses=Warehouse.query.all(), today=date.today(), invoice_no=next_number("sales"))


@bp.route("/<int:id>/print")
@login_required
def print_sale(id):
    sale = Sale.query.get_or_404(id)
    return render_template("sales/print.html", title=f"Invoice {sale.invoice_no}", sale=sale, hsn_rows=hsn_summary(sale))


@bp.route("/<int:id>/pdf")
@login_required
def sale_pdf(id):
    sale = Sale.query.get_or_404(id)
    pdf = render_pdf("sales/print.html", sale=sale, title=f"Invoice {sale.invoice_no}")
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
    invoice_url = url_for("sales.print_sale", id=sale.id, _external=True)
    subject = quote_plus(f"Invoice {sale.invoice_no}")
    body = quote_plus(f"Dear {sale.customer.name},\n\nPlease find invoice {sale.invoice_no} for {sale.grand_total}.\n\nView/print: {invoice_url}")
    return redirect(f"mailto:{sale.customer.email or ''}?subject={subject}&body={body}")


@bp.route("/<int:id>/whatsapp")
@login_required
def whatsapp_invoice(id):
    sale = Sale.query.get_or_404(id)
    invoice_url = url_for("sales.print_sale", id=sale.id, _external=True)
    phone = "".join(ch for ch in (sale.customer.phone or "") if ch.isdigit())
    text = quote_plus(f"Invoice {sale.invoice_no} amount {sale.grand_total}. View: {invoice_url}")
    return redirect(f"https://wa.me/{phone}?text={text}" if phone else f"https://wa.me/?text={text}")


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
            ret = SalesReturn(return_no=request.form.get("return_no") or next_number("sales_return"), return_date=date.fromisoformat(request.form["return_date"]), sale_id=request.form.get("sale_id") or None, customer_id=request.form["customer_id"], warehouse_id=request.form["warehouse_id"], reason=request.form.get("reason"), refund_mode=request.form.get("refund_mode") or "Credit Note", notes=request.form.get("notes"), created_by=current_user.id, subtotal=totals["subtotal"], tax_total=totals["tax_total"], grand_total=totals["grand_total"])
            db.session.add(ret); db.session.flush()
            balance = ret.sales_return_customer.outstanding - float(ret.grand_total or 0)
            db.session.add(CustomerLedger(date=ret.return_date, customer_id=ret.customer_id, reference_type="SalesReturn", reference_id=ret.id, reference_no=ret.return_no, debit=0, credit=ret.grand_total, balance=balance, narration="Sales return credit note"))
            for item in items:
                db.session.add(SalesReturnItem(sales_return_id=ret.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"]))
                apply_sales_return_item(item["product_id"], ret.warehouse_id, item["quantity"], item["rate"], ret.id, ret.return_no)
            db.session.commit(); flash("Sales return saved and stock updated.", "success")
            return redirect(url_for("sales.returns"))
        except Exception as exc:
            db.session.rollback(); flash(str(exc), "danger")
    return render_template("sales/return_form.html", title="Create Sales Return", customers=Customer.query.all(), warehouses=Warehouse.query.all(), sales=Sale.query.order_by(Sale.id.desc()).all(), today=date.today(), return_no=next_number("sales_return"))


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
