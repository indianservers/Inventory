import os
from datetime import date, datetime, timedelta

from app.extensions import db
from app.models import RecurringInvoice, Sale, SaleItem
from app.services.accounting_service import post_sale
from app.services.invoice_service import calculate_document, line_totals
from app.services.numbering_service import next_number
from app.services.stock_service import apply_sale_item


def calculate_next(run_date, frequency, interval_value=1):
    interval_value = max(int(interval_value or 1), 1)
    if frequency == "Daily":
        return run_date + timedelta(days=interval_value)
    if frequency == "Weekly":
        return run_date + timedelta(weeks=interval_value)
    if frequency == "Quarterly":
        return _add_months(run_date, 3 * interval_value)
    if frequency == "Yearly":
        return _add_months(run_date, 12 * interval_value)
    return _add_months(run_date, interval_value)


def generate_sale_from_recurring(recurring, user_id=None):
    items = []
    for item in recurring.items:
        totals = line_totals(item.quantity, item.rate, item.discount, item.tax_rate)
        items.append({
            "product_id": item.product_id,
            "quantity": item.quantity,
            "rate": item.rate,
            "discount": item.discount,
            "tax_rate": item.tax_rate,
            **totals,
        })
    totals = calculate_document(items)
    sale = Sale(
        invoice_no=next_number("sales"),
        invoice_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        customer_id=recurring.customer_id,
        warehouse_id=recurring.warehouse_id,
        sale_type="Credit",
        notes=f"{recurring.notes or ''}\nRecurring template #{recurring.id}".strip(),
        terms=recurring.terms,
        created_by=user_id or recurring.created_by,
        issued_at=datetime.utcnow(),
        **totals,
    )
    sale.update_payment_status()
    db.session.add(sale)
    db.session.flush()
    for item in items:
        cost = apply_sale_item(item["product_id"], sale.warehouse_id, item["quantity"], sale.id, sale.invoice_no)
        db.session.add(SaleItem(
            sale_id=sale.id,
            product_id=item["product_id"],
            quantity=item["quantity"],
            rate=item["rate"],
            discount=item["discount"],
            discount_amount=item["discount_amount"],
            tax_rate=item["tax_rate"],
            tax_amount=item["tax_amount"],
            line_total=item["line_total"],
            cost_price=cost,
        ))
    post_sale(sale, user_id or recurring.created_by)
    recurring.last_run_date = date.today()
    recurring.next_run_date = calculate_next(recurring.next_run_date or date.today(), recurring.frequency, recurring.interval_value)
    if recurring.end_date and recurring.next_run_date > recurring.end_date:
        recurring.status = "Ended"
    return sale


def generate_due_recurring():
    due = RecurringInvoice.query.filter(
        RecurringInvoice.status == "Active",
        RecurringInvoice.next_run_date <= date.today(),
    ).all()
    generated = []
    for recurring in due:
        sale = generate_sale_from_recurring(recurring)
        generated.append(sale)
        if recurring.auto_send and os.environ.get("WHATSAPP_TOKEN"):
            # The existing WhatsApp route is interactive; scheduled delivery is
            # kept as a marker for operators until a background queue is added.
            sale.notes = f"{sale.notes or ''}\nAuto-send requested".strip()
    db.session.commit()
    return generated


def _add_months(value, months):
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, _last_day(year, month))
    return date(year, month, day)


def _last_day(year, month):
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day
