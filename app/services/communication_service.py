from datetime import datetime

from flask import current_app, render_template_string

from app.extensions import db
from app.models import CommunicationLog, EmailTemplate, IntegrationSetting
from app.services.email_service import send_email


def _active_provider(channel):
    return IntegrationSetting.query.filter_by(provider_type=channel, is_active=True).order_by(IntegrationSetting.id.desc()).first()


def render_email_template(template_type, context):
    template = EmailTemplate.query.filter_by(template_type=template_type, is_active=True).order_by(EmailTemplate.id.desc()).first()
    if not template:
        return "", ""
    return render_template_string(template.subject or "", **context), render_template_string(template.body or "", **context)


def log_communication(channel, recipient, subject=None, body=None, status="Pending", provider=None, reference_type=None, reference_id=None, error_message=None):
    row = CommunicationLog(
        channel=channel,
        recipient=recipient,
        subject=subject,
        body=body,
        provider=provider,
        status=status,
        reference_type=reference_type,
        reference_id=reference_id,
        error_message=error_message,
        sent_at=datetime.utcnow() if status in {"Sent", "Mock Sent"} else None,
    )
    db.session.add(row)
    db.session.commit()
    return row


def send_message(channel, recipient, subject="", body="", reference_type=None, reference_id=None, attachment_bytes=None, attachment_name=None):
    provider = _active_provider(channel)
    if not provider:
        return log_communication(channel, recipient, subject, body, "Provider configuration required", None, reference_type, reference_id, "No active provider configured")

    if provider.test_mode:
        return log_communication(channel, recipient, subject, body, "Mock Sent", provider.provider_name, reference_type, reference_id)

    if channel == "email":
        ok = send_email(recipient, subject, body, attachment_bytes, attachment_name)
        return log_communication(channel, recipient, subject, body, "Sent" if ok else "Failed", provider.provider_name, reference_type, reference_id, None if ok else "SMTP send failed")

    current_app.logger.info("Provider %s for %s is configured but no live adapter is installed.", provider.provider_name, channel)
    return log_communication(channel, recipient, subject, body, "Provider configuration required", provider.provider_name, reference_type, reference_id, "Live adapter not installed")


def send_invoice_email(sale, recipient=None, attachment_bytes=None):
    recipient = recipient or (sale.customer.email if sale.customer else "")
    subject, body = render_email_template("invoice_email", {"invoice": sale, "sale": sale, "customer": sale.customer})
    subject = subject or f"Invoice {sale.invoice_no}"
    body = body or f"Please find invoice {sale.invoice_no} for amount {sale.grand_total}."
    return send_message("email", recipient, subject, body, "invoice", sale.id, attachment_bytes, f"{sale.invoice_no}.pdf")


def send_low_stock_alert(product):
    subject = f"Low stock alert: {product.name}"
    body = f"{product.name} is below reorder level. Current stock: {product.current_stock}."
    return send_message("email", "admin", subject, body, "product", product.id)
