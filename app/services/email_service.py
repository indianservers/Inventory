import logging
import os
import smtplib
from email.message import EmailMessage


def send_email(to, subject, body_html, attachment_bytes=None, attachment_name=None):
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT") or 587)
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    sender = os.environ.get("SMTP_FROM") or user
    if not host or not sender:
        logging.info("Email not configured")
        return False

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content("This email contains an HTML report. Please use an HTML-capable client.")
    message.add_alternative(body_html, subtype="html")
    if attachment_bytes and attachment_name:
        payload = attachment_bytes.getvalue() if hasattr(attachment_bytes, "getvalue") else attachment_bytes
        maintype, subtype = ("application", "pdf") if attachment_name.lower().endswith(".pdf") else ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=attachment_name)

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(message)
    return True
