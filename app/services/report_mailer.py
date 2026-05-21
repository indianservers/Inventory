from datetime import datetime

from app.extensions import db
from app.models import Product, Purchase, Sale, ScheduledReport
from app.services.email_service import send_email
from app.utils.excel_export import export_to_excel


def send_due_reports():
    now = datetime.now()
    sent = []
    for schedule in ScheduledReport.query.filter_by(is_active=True).all():
        if not _is_due(schedule, now):
            continue
        attachment, filename = _build_report(schedule)
        ok = send_email(
            schedule.recipient_emails or "",
            f"Scheduled report: {schedule.name}",
            f"<p>{schedule.name} is attached.</p>",
            attachment,
            filename,
        )
        if ok:
            schedule.last_sent_at = now
            sent.append(schedule)
    db.session.commit()
    return sent


def send_report_now(schedule):
    attachment, filename = _build_report(schedule)
    ok = send_email(schedule.recipient_emails or "", f"Scheduled report: {schedule.name}", f"<p>{schedule.name} is attached.</p>", attachment, filename)
    if ok:
        schedule.last_sent_at = datetime.now()
        db.session.commit()
    return ok


def _is_due(schedule, now):
    if schedule.last_sent_at and schedule.last_sent_at.date() == now.date():
        return False
    target_time = schedule.time_of_day or "09:00"
    if now.strftime("%H:%M") < target_time:
        return False
    if schedule.frequency == "Weekly":
        return schedule.day_of_week is None or schedule.day_of_week == now.weekday()
    if schedule.frequency == "Monthly":
        return schedule.day_of_month is None or schedule.day_of_month == now.day
    return True


def _build_report(schedule):
    report_type = schedule.report_type
    if report_type == "purchases":
        rows = [[p.purchase_no, p.purchase_date, p.supplier.name, p.grand_total, p.payment_status] for p in Purchase.query.order_by(Purchase.purchase_date.desc()).limit(1000)]
        return export_to_excel(["Purchase No", "Date", "Supplier", "Total", "Status"], rows, "Purchases"), "purchases.xlsx"
    if report_type == "stock":
        rows = [[p.sku, p.name, p.current_stock, p.average_cost, p.stock_value] for p in Product.query.order_by(Product.name)]
        return export_to_excel(["SKU", "Name", "Stock", "Avg Cost", "Value"], rows, "Stock"), "stock.xlsx"
    rows = [[s.invoice_no, s.invoice_date, s.customer.name, s.grand_total, s.payment_status] for s in Sale.query.order_by(Sale.invoice_date.desc()).limit(1000)]
    return export_to_excel(["Invoice No", "Date", "Customer", "Total", "Status"], rows, "Sales"), "sales.xlsx"
