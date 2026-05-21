from datetime import date, datetime

from flask import abort

from app.extensions import db
from app.models import Currency, Customer, PaymentReceived, Product, Sale, SaleItem
from app.services.accounting_service import post_customer_receipt, post_sale, reverse_sale
from app.services.numbering_service import next_number
from app.services.stock_service import apply_sale_item, reverse_sale_item
from app.utils.helpers import money, payment_status, qty


def line_totals(quantity, rate, discount_percent=0, tax_rate=0):
    quantity, rate = qty(quantity), money(rate)
    gross = money(quantity * rate)
    discount_amount = money(gross * money(discount_percent) / 100)
    taxable = gross - discount_amount
    tax_amount = money(taxable * money(tax_rate) / 100)
    return {
        "gross": gross,
        "discount_amount": discount_amount,
        "tax_amount": tax_amount,
        "line_total": money(taxable + tax_amount),
    }


def calculate_document(items, shipping=0, other=0, round_off=0, paid=0):
    subtotal = sum(money(item["gross"]) for item in items)
    discount_total = sum(money(item["discount_amount"]) for item in items)
    tax_total = sum(money(item["tax_amount"]) for item in items)
    grand_total = money(subtotal - discount_total + tax_total + money(shipping) + money(other) + money(round_off))
    return {
        "subtotal": subtotal,
        "discount_total": discount_total,
        "tax_total": tax_total,
        "grand_total": grand_total,
        "paid_amount": money(paid),
        "balance_amount": money(grand_total - money(paid)),
        "payment_status": payment_status(grand_total, paid),
    }


def validate_invoice_items(items):
    if not items:
        abort(400, "At least one invoice item is required.")
    product_ids = [int(item["product_id"]) for item in items]
    products = {product.id: product for product in Product.query.filter(Product.id.in_(product_ids)).all()}
    if len(products) != len(set(product_ids)):
        abort(400, "One or more invoice products do not exist.")
    for item in items:
        product = products[int(item["product_id"])]
        if qty(item["quantity"]) <= 0:
            abort(400, f"Quantity must be greater than zero for {product.name}.")
        if money(item["rate"]) < 0:
            abort(400, f"Rate cannot be negative for {product.name}.")
        if money(item.get("discount", 0)) < 0:
            abort(400, f"Discount cannot be negative for {product.name}.")
    return products


def create_or_update_invoice(sale, form, items, user_id):
    if sale.id and sale.status != "Draft":
        abort(400, "Only draft invoices can be edited.")
    validate_invoice_items(items)
    invoice_date = date.fromisoformat(form["invoice_date"])
    due_date = date.fromisoformat(form["due_date"]) if form.get("due_date") else None
    if due_date and due_date < invoice_date:
        abort(400, "Due date cannot be before invoice date.")
    customer = Customer.query.get(form["customer_id"])
    if not customer:
        abort(400, "Customer does not exist.")
    totals = calculate_document(items, shipping=form.get("shipping_charges"), other=form.get("other_charges"), round_off=form.get("round_off"), paid=0)
    currency = Currency.query.get(form.get("currency_id")) if form.get("currency_id") else Currency.query.filter_by(is_base=True).first()
    exchange_rate = money(form.get("exchange_rate_snapshot") or (currency.exchange_rate if currency else 1) or 1)
    original_total = totals["grand_total"]
    if exchange_rate != 1:
        totals = {key: money(value * exchange_rate) if key not in ["payment_status"] else value for key, value in totals.items()}
        for item in items:
            for key in ["rate", "gross", "discount_amount", "tax_amount", "line_total"]:
                item[key] = money(item[key] * exchange_rate)
    sale.invoice_no = form.get("invoice_no") or sale.invoice_no or next_number("sales")
    sale.invoice_date = invoice_date
    sale.due_date = due_date
    sale.customer_id = form["customer_id"]
    sale.warehouse_id = form["warehouse_id"]
    sale.sale_type = form.get("sale_type") or "Credit"
    sale.currency_id = currency.id if currency else None
    sale.exchange_rate_snapshot = exchange_rate
    sale.original_currency_total = original_total
    sale.notes = form.get("notes")
    sale.terms = form.get("terms")
    sale.status = "Draft"
    sale.payment_status = "Unpaid"
    sale.updated_by = user_id
    if not sale.created_by:
        sale.created_by = user_id
    for key, value in totals.items():
        if key in ["paid_amount", "balance_amount", "payment_status"]:
            continue
        setattr(sale, key, value)
    sale.paid_amount = money(0)
    sale.balance_amount = totals["grand_total"]
    db.session.add(sale)
    db.session.flush()
    if sale.id:
        SaleItem.query.filter_by(sale_id=sale.id).delete()
    for item in items:
        db.session.add(SaleItem(sale_id=sale.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], discount=item["discount"], discount_amount=item["discount_amount"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"], cost_price=0))
    return sale


def issue_invoice(sale, user_id):
    if sale.status != "Draft":
        abort(400, "Only draft invoices can be issued.")
    if sale.items.count() == 0:
        abort(400, "Invoice must have at least one item before issuing.")
    for item in sale.items:
        cost = apply_sale_item(item.product_id, sale.warehouse_id, item.quantity, sale.id, sale.invoice_no)
        item.cost_price = cost
    sale.issued_at = datetime.utcnow()
    sale.updated_by = user_id
    sale.status = "Issued"
    sale.payment_status = "Unpaid"
    sale.paid_amount = money(0)
    sale.balance_amount = sale.grand_total
    post_sale(sale, user_id)
    return sale


def record_invoice_payment(sale, amount, payment_date, payment_mode, reference_no, notes, user_id):
    if sale.status in ["Draft", "Cancelled"]:
        abort(400, "Payments can only be recorded on issued invoices.")
    amount = money(amount)
    if amount <= 0:
        abort(400, "Payment amount must be greater than zero.")
    if amount > money(sale.balance_amount):
        abort(400, "Payment amount cannot exceed invoice balance.")
    receipt = PaymentReceived(receipt_no=next_number("receipt"), receipt_date=payment_date, customer_id=sale.customer_id, amount=amount, payment_mode=payment_mode or "Cash", reference_no=reference_no, notes=notes, sale_id=sale.id, created_by=user_id)
    db.session.add(receipt)
    db.session.flush()
    sale.paid_amount = money(sale.paid_amount) + amount
    sale.update_payment_status()
    sale.updated_by = user_id
    post_customer_receipt(receipt, user_id)
    return receipt


def cancel_invoice(sale, reason, user_id):
    if sale.status == "Cancelled":
        abort(400, "Invoice is already cancelled.")
    if sale.status == "Draft":
        sale.status = "Cancelled"
        sale.cancelled_at = datetime.utcnow()
        sale.cancellation_reason = reason
        sale.updated_by = user_id
        return sale
    if money(sale.paid_amount) > 0:
        abort(400, "Paid or partially paid invoices cannot be cancelled. Reverse the receipt first.")
    for item in sale.items:
        reverse_sale_item(item.product_id, sale.warehouse_id, item.quantity, item.cost_price, sale.id, sale.invoice_no, reason)
    reverse_sale(sale, user_id, reason)
    sale.status = "Cancelled"
    sale.cancelled_at = datetime.utcnow()
    sale.cancellation_reason = reason
    sale.balance_amount = money(0)
    sale.updated_by = user_id
    return sale
