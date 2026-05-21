import hashlib
import hmac
import json
from datetime import datetime

import requests
from flask import request

from app.extensions import db
from app.models import IncomingWebhookLog, WebhookLog, WebhookSubscription


def _event_enabled(subscription, event):
    configured = [item.strip() for item in (subscription.events or "").split(",") if item.strip()]
    return "*" in configured or event in configured


def _signature(secret, payload):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def emit_webhook(event, payload):
    payload_text = json.dumps({"event": event, "data": payload}, default=str)
    logs = []
    for subscription in WebhookSubscription.query.filter_by(is_active=True).all():
        if not _event_enabled(subscription, event):
            continue
        headers = {"Content-Type": "application/json"}
        if subscription.secret:
            headers["X-Vyapara-Signature"] = _signature(subscription.secret, payload_text)
        log = WebhookLog(subscription_id=subscription.id, event=event, payload=payload_text, status="Pending")
        db.session.add(log)
        db.session.flush()
        try:
            response = requests.post(subscription.target_url, data=payload_text, headers=headers, timeout=10)
            log.response_status = response.status_code
            log.response_body = response.text[:2000]
            log.status = "Delivered" if response.ok else "Failed"
            log.delivered_at = datetime.utcnow() if response.ok else None
        except Exception as exc:
            log.status = "Failed"
            log.error_message = str(exc)
        logs.append(log)
    db.session.commit()
    return logs


def record_incoming_webhook(provider, event_type=None, payload=None):
    row = IncomingWebhookLog(
        provider=provider,
        event_type=event_type,
        payload=json.dumps(payload if payload is not None else (request.get_json(silent=True) or {}), default=str),
        headers=json.dumps(dict(request.headers), default=str),
        status="Received",
    )
    db.session.add(row)
    db.session.commit()
    return row
