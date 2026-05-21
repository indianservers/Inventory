import logging
import json
import os
import smtplib
from email.message import EmailMessage

from app.models import IntegrationSetting


def send_email(to, subject, body_html, attachment_bytes=None, attachment_name=None):
    config = smtp_config()
    host = config.get("host")
    port = int(config.get("port") or 587)
    user = config.get("user")
    password = config.get("password")
    sender = config.get("sender") or user
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


def smtp_config():
    config = {
        "host": os.environ.get("SMTP_HOST"),
        "port": os.environ.get("SMTP_PORT") or 587,
        "user": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASS"),
        "sender": os.environ.get("SMTP_FROM"),
    }
    try:
        setting = IntegrationSetting.query.filter_by(provider_type="email", is_active=True).order_by(IntegrationSetting.id.desc()).first()
        if setting and setting.config_json:
            data = json.loads(setting.config_json)
            config.update({
                "host": data.get("host") or data.get("SMTP_HOST") or config["host"],
                "port": data.get("port") or data.get("SMTP_PORT") or config["port"],
                "user": data.get("user") or data.get("SMTP_USER") or config["user"],
                "password": data.get("password") or data.get("SMTP_PASS") or config["password"],
                "sender": data.get("sender") or data.get("from") or data.get("SMTP_FROM") or config["sender"],
            })
    except Exception:
        logging.exception("Unable to read SMTP integration settings")
    return config
