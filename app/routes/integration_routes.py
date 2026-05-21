import json
import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from app.extensions import csrf, db
from app.models import (
    ApiToken, CommunicationLog, Coupon, CustomField, CustomModule, CustomModuleField,
    CustomModuleRecord, CustomView, EcommerceOrder, EmailTemplate,
    IncomingWebhookLog, IntegrationSetting, PaymentGateway, PaymentLink, Product, Sale,
    LoyaltySetting, ScheduledJob, ScheduledJobLog, ShippingProvider, Shipment, User, WebhookLog,
    WebhookSubscription, WorkflowAction, WorkflowCondition, WorkflowRule,
)
from app.services.scheduler_service import run_scheduled_jobs
from app.services.communication_service import send_message
from app.services.webhook_service import emit_webhook, record_incoming_webhook

bp = Blueprint("integrations", __name__)


def _bool(name):
    return bool(request.form.get(name))


def _json_text(name):
    value = request.form.get(name) or ""
    if not value.strip():
        return None
    try:
        json.loads(value)
    except ValueError:
        flash(f"{name.replace('_', ' ').title()} must be valid JSON.", "danger")
        return False
    return value


def _key(value):
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value[:80]


def _record_data(fields):
    data = {}
    errors = []
    for field in fields:
        if field.field_key == "title":
            continue
        raw = request.form.get(f"field_{field.id}")
        if field.is_required and not (raw or "").strip():
            errors.append(f"{field.label} is required.")
        if field.field_type == "Checkbox":
            data[field.field_key] = bool(request.form.get(f"field_{field.id}"))
        else:
            data[field.field_key] = raw
    return data, errors


@bp.route("/settings/email-templates", methods=["GET", "POST"])
@login_required
def email_templates():
    if request.method == "POST":
        if not request.form.get("name") or not request.form.get("subject"):
            flash("Template name and subject are required.", "danger")
            return redirect(url_for("integrations.email_templates"))
        row = EmailTemplate(
            name=request.form["name"].strip(),
            template_type=request.form.get("template_type") or "invoice_email",
            subject=request.form["subject"].strip(),
            body=request.form.get("body") or "",
            placeholders=request.form.get("placeholders"),
            is_active=_bool("is_active"),
        )
        db.session.add(row)
        db.session.commit()
        flash("Email template saved.", "success")
        return redirect(url_for("integrations.email_templates"))
    return render_template("settings/foundation_list.html", title="Email Templates", rows=EmailTemplate.query.order_by(EmailTemplate.id.desc()).all(), kind="email_templates")


@bp.route("/settings/communication-settings", methods=["GET", "POST"])
@login_required
def communication_settings():
    if request.method == "POST":
        config = _json_text("config_json")
        if config is False:
            return redirect(url_for("integrations.communication_settings"))
        row = IntegrationSetting(
            provider_type=request.form.get("provider_type") or "email",
            provider_name=request.form.get("provider_name") or "Provider",
            config_json=config,
            is_active=_bool("is_active"),
            test_mode=_bool("test_mode"),
        )
        db.session.add(row)
        db.session.commit()
        flash("Communication provider saved.", "success")
        return redirect(url_for("integrations.communication_settings"))
    return render_template("settings/foundation_list.html", title="Communication Settings", rows=IntegrationSetting.query.order_by(IntegrationSetting.id.desc()).all(), kind="communication_settings")


@bp.route("/settings/communication-settings/test-email", methods=["POST"])
@login_required
def test_email():
    recipient = request.form.get("recipient") or current_user.email
    log = send_message("email", recipient, "Vyapara ERP test email", "<p>This is a test email from Vyapara ERP.</p>", "settings", current_user.id)
    flash("Test email sent." if log.status in {"Sent", "Mock Sent"} else log.status, "success" if log.status in {"Sent", "Mock Sent"} else "warning")
    return redirect(url_for("integrations.communication_settings"))


@bp.route("/settings/payment-gateways", methods=["GET", "POST"])
@login_required
def payment_gateways():
    if request.method == "POST":
        config = _json_text("config_json")
        if config is False:
            return redirect(url_for("integrations.payment_gateways"))
        row = PaymentGateway(
            provider=request.form.get("provider") or "manual",
            display_name=request.form.get("display_name") or "Manual Gateway",
            api_key_label=request.form.get("api_key_label"),
            config_json=config,
            is_active=_bool("is_active"),
            test_mode=_bool("test_mode"),
        )
        db.session.add(row)
        db.session.commit()
        flash("Payment gateway saved.", "success")
        return redirect(url_for("integrations.payment_gateways"))
    return render_template("settings/foundation_list.html", title="Payment Gateways", rows=PaymentGateway.query.order_by(PaymentGateway.id.desc()).all(), kind="payment_gateways")


@bp.route("/settings/loyalty", methods=["GET", "POST"])
@login_required
def loyalty_settings():
    row = LoyaltySetting.query.first() or LoyaltySetting()
    if request.method == "POST":
        row.is_enabled = _bool("is_enabled")
        row.earn_points_per_amount = request.form.get("earn_points_per_amount") or 100
        row.points_earned = request.form.get("points_earned") or 1
        row.redemption_value_per_point = request.form.get("redemption_value_per_point") or 1
        row.points_expiry_days = request.form.get("points_expiry_days") or 365
        db.session.add(row)
        db.session.commit()
        flash("Loyalty settings saved.", "success")
        return redirect(url_for("integrations.loyalty_settings"))
    return render_template("settings/foundation_list.html", title="Loyalty Settings", rows=[row] if row.id else [], setting=row, kind="loyalty")


@bp.route("/settings/coupons", methods=["GET", "POST"])
@login_required
def coupons():
    if request.method == "POST":
        coupon = Coupon(code=request.form["code"].strip().upper(), description=request.form.get("description"), discount_type=request.form.get("discount_type") or "Percentage", discount_value=request.form.get("discount_value") or 0, valid_from=datetime.fromisoformat(request.form["valid_from"]).date() if request.form.get("valid_from") else None, valid_to=datetime.fromisoformat(request.form["valid_to"]).date() if request.form.get("valid_to") else None, minimum_invoice_amount=request.form.get("minimum_invoice_amount") or 0, max_usage=request.form.get("max_usage") or None, per_customer_usage_limit=request.form.get("per_customer_usage_limit") or None, is_active=_bool("is_active"))
        db.session.add(coupon)
        db.session.commit()
        flash("Coupon saved.", "success")
        return redirect(url_for("integrations.coupons"))
    return render_template("settings/foundation_list.html", title="Coupons", rows=Coupon.query.order_by(Coupon.id.desc()).all(), kind="coupons")


@bp.route("/settings/payment-links/<int:sale_id>/create", methods=["POST"])
@login_required
def create_payment_link(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    gateway = PaymentGateway.query.filter_by(is_active=True).order_by(PaymentGateway.id.desc()).first()
    if not gateway:
        flash("Provider configuration required before creating payment links.", "warning")
        return redirect(request.referrer or url_for("invoices.detail", id=sale.id))
    reference = f"PL-{secrets.token_hex(6).upper()}"
    link = PaymentLink(
        sale_id=sale.id,
        gateway_id=gateway.id,
        provider_reference=reference,
        amount=sale.balance_amount or sale.grand_total,
        currency="INR",
        status="Created" if not gateway.test_mode else "Mock Created",
        expires_at=datetime.utcnow() + timedelta(days=7),
        link_url=url_for("invoices.pay", id=sale.id, _external=True),
    )
    db.session.add(link)
    db.session.commit()
    flash("Payment link created." if not gateway.test_mode else "Mock payment link created in test mode.", "success")
    return redirect(request.referrer or url_for("invoices.detail", id=sale.id))


@bp.route("/settings/ecommerce-integrations", methods=["GET", "POST"])
@login_required
def ecommerce_integrations():
    if request.method == "POST":
        config = _json_text("config_json")
        if config is False:
            return redirect(url_for("integrations.ecommerce_integrations"))
        db.session.add(IntegrationSetting(provider_type="ecommerce", provider_name=request.form.get("provider_name") or "Ecommerce", config_json=config, is_active=_bool("is_active"), test_mode=_bool("test_mode")))
        db.session.commit()
        flash("Ecommerce integration saved.", "success")
        return redirect(url_for("integrations.ecommerce_integrations"))
    return render_template("settings/foundation_list.html", title="Ecommerce Integrations", rows=IntegrationSetting.query.filter_by(provider_type="ecommerce").order_by(IntegrationSetting.id.desc()).all(), kind="ecommerce_integrations", orders=EcommerceOrder.query.order_by(EcommerceOrder.id.desc()).limit(100).all())


@bp.route("/settings/shipping-providers", methods=["GET", "POST"])
@login_required
def shipping_providers():
    if request.method == "POST":
        config = _json_text("config_json")
        if config is False:
            return redirect(url_for("integrations.shipping_providers"))
        db.session.add(ShippingProvider(name=request.form.get("name") or "Shipping Provider", provider_code=request.form.get("provider_code") or "MANUAL", config_json=config, is_active=_bool("is_active"), test_mode=_bool("test_mode")))
        db.session.commit()
        flash("Shipping provider saved.", "success")
        return redirect(url_for("integrations.shipping_providers"))
    return render_template("settings/foundation_list.html", title="Shipping Providers", rows=ShippingProvider.query.order_by(ShippingProvider.id.desc()).all(), kind="shipping_providers", shipments=Shipment.query.order_by(Shipment.id.desc()).limit(100).all())


@bp.route("/settings/api-keys", methods=["GET", "POST"])
@login_required
def api_keys():
    plain_token = None
    if request.method == "POST":
        token = secrets.token_urlsafe(32)
        api_token = ApiToken(name=request.form["name"].strip(), token_hash=generate_password_hash(token), prefix=token[:12], user_id=request.form.get("user_id") or None)
        db.session.add(api_token)
        db.session.commit()
        plain_token = token
        flash("API key created. Copy it now; it will not be shown again.", "success")
    return render_template("settings/api_tokens.html", title="API Keys", tokens=ApiToken.query.order_by(ApiToken.id.desc()).all(), users=User.query.order_by(User.name).all(), plain_token=plain_token)


@bp.route("/settings/webhooks", methods=["GET", "POST"])
@login_required
def webhooks():
    if request.method == "POST":
        db.session.add(WebhookSubscription(name=request.form["name"].strip(), target_url=request.form["target_url"].strip(), events=request.form.get("events") or "*", secret=request.form.get("secret"), is_active=_bool("is_active")))
        db.session.commit()
        flash("Webhook subscription saved.", "success")
        return redirect(url_for("integrations.webhooks"))
    return render_template("settings/foundation_list.html", title="Webhooks", rows=WebhookSubscription.query.order_by(WebhookSubscription.id.desc()).all(), kind="webhooks")


@bp.route("/settings/webhooks/test/<int:id>", methods=["POST"])
@login_required
def webhook_test(id):
    subscription = WebhookSubscription.query.get_or_404(id)
    emit_webhook("system.test", {"subscription_id": subscription.id, "sent_by": current_user.email})
    flash("Webhook test queued. Check webhook logs for delivery status.", "success")
    return redirect(url_for("integrations.webhooks"))


@bp.route("/webhooks/incoming/<provider>", methods=["POST"])
@csrf.exempt
def incoming_webhook(provider):
    payload = request.get_json(silent=True) or request.form.to_dict()
    record_incoming_webhook(provider, payload.get("event") or payload.get("type"), payload)
    return jsonify({"status": "received"})


@bp.route("/payments/webhook/<provider>", methods=["POST"])
@csrf.exempt
def payment_webhook(provider):
    payload = request.get_json(silent=True) or {}
    record_incoming_webhook(provider, payload.get("event") or "payment", payload)
    return jsonify({"status": "received"})


@bp.route("/settings/custom-fields", methods=["GET", "POST"])
@login_required
def custom_fields():
    if request.method == "POST":
        db.session.add(CustomField(entity_type=request.form.get("entity_type") or "products", field_key=request.form["field_key"].strip(), label=request.form["label"].strip(), field_type=request.form.get("field_type") or "Text", options=request.form.get("options"), is_required=_bool("is_required"), is_active=_bool("is_active")))
        db.session.commit()
        flash("Custom field saved.", "success")
        return redirect(url_for("integrations.custom_fields"))
    return render_template("settings/foundation_list.html", title="Custom Fields", rows=CustomField.query.order_by(CustomField.entity_type, CustomField.label).all(), kind="custom_fields")


@bp.route("/settings/custom-views", methods=["GET", "POST"])
@login_required
def custom_views():
    if request.method == "POST":
        filters = _json_text("filters_json")
        columns = _json_text("columns_json")
        if filters is False or columns is False:
            return redirect(url_for("integrations.custom_views"))
        db.session.add(CustomView(entity_type=request.form.get("entity_type") or "products", name=request.form["name"].strip(), filters_json=filters, columns_json=columns, sort_json=request.form.get("sort_json"), is_default=_bool("is_default"), created_by=current_user.id))
        db.session.commit()
        flash("Custom view saved.", "success")
        return redirect(url_for("integrations.custom_views"))
    return render_template("settings/foundation_list.html", title="Custom Views", rows=CustomView.query.order_by(CustomView.entity_type, CustomView.name).all(), kind="custom_views")


@bp.route("/settings/customization")
@login_required
def customization():
    modules = CustomModule.query.order_by(CustomModule.name).all()
    fields = CustomField.query.order_by(CustomField.entity_type, CustomField.label).all()
    views = CustomView.query.order_by(CustomView.entity_type, CustomView.name).all()
    return render_template("settings/customization.html", title="Customization Studio", modules=modules, fields=fields, views=views)


@bp.route("/settings/custom-modules", methods=["GET", "POST"])
@login_required
def custom_modules():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        module_key = _key(request.form.get("module_key") or name)
        if not name or not module_key:
            flash("Module name and key are required.", "danger")
            return redirect(url_for("integrations.custom_modules"))
        if CustomModule.query.filter_by(module_key=module_key).first():
            flash("A custom module with this key already exists.", "danger")
            return redirect(url_for("integrations.custom_modules"))
        module = CustomModule(
            module_key=module_key,
            name=name,
            plural_name=(request.form.get("plural_name") or f"{name}s").strip(),
            description=request.form.get("description"),
            icon=request.form.get("icon") or "bi-grid",
            show_in_sidebar=_bool("show_in_sidebar"),
            allow_import=_bool("allow_import"),
            allow_export=_bool("allow_export"),
            is_active=_bool("is_active"),
            created_by=current_user.id,
        )
        db.session.add(module)
        db.session.flush()
        db.session.add(CustomModuleField(module_id=module.id, field_key="title", label="Title", field_type="Text", is_required=True, show_in_list=True, sort_order=1))
        db.session.commit()
        flash("Custom module created.", "success")
        return redirect(url_for("integrations.custom_module_detail", id=module.id))
    modules = CustomModule.query.order_by(CustomModule.name).all()
    return render_template("settings/custom_modules.html", title="Custom Modules", modules=modules)


@bp.route("/settings/custom-modules/<int:id>", methods=["GET", "POST"])
@login_required
def custom_module_detail(id):
    module = CustomModule.query.get_or_404(id)
    fields = module.fields.filter_by(is_active=True).order_by(CustomModuleField.sort_order, CustomModuleField.id).all()
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        data, errors = _record_data(fields)
        if not title:
            errors.append("Record title is required.")
        if errors:
            for error in errors:
                flash(error, "danger")
            return redirect(url_for("integrations.custom_module_detail", id=module.id))
        record = CustomModuleRecord(
            module_id=module.id,
            title=title,
            data_json=json.dumps(data),
            status=request.form.get("status") or "Active",
            created_by=current_user.id,
        )
        db.session.add(record)
        db.session.commit()
        flash("Record saved.", "success")
        return redirect(url_for("integrations.custom_module_detail", id=module.id))
    records = module.records.order_by(CustomModuleRecord.id.desc()).all()
    record_rows = []
    for record in records:
        try:
            values = json.loads(record.data_json or "{}")
        except ValueError:
            values = {}
        record_rows.append((record, values))
    return render_template("settings/custom_module_detail.html", title=module.plural_name or module.name, module=module, fields=fields, record_rows=record_rows)


@bp.route("/settings/custom-modules/<int:id>/fields", methods=["POST"])
@login_required
def custom_module_fields(id):
    module = CustomModule.query.get_or_404(id)
    label = (request.form.get("label") or "").strip()
    field_key = _key(request.form.get("field_key") or label)
    if not label or not field_key:
        flash("Field label and key are required.", "danger")
        return redirect(url_for("integrations.custom_module_detail", id=module.id))
    if CustomModuleField.query.filter_by(module_id=module.id, field_key=field_key).first():
        flash("This field key already exists on the module.", "danger")
        return redirect(url_for("integrations.custom_module_detail", id=module.id))
    field = CustomModuleField(
        module_id=module.id,
        field_key=field_key,
        label=label,
        field_type=request.form.get("field_type") or "Text",
        options=request.form.get("options"),
        is_required=_bool("is_required"),
        show_in_list=_bool("show_in_list"),
        sort_order=int(request.form.get("sort_order") or 0),
        is_active=True,
    )
    db.session.add(field)
    db.session.commit()
    flash("Module field added.", "success")
    return redirect(url_for("integrations.custom_module_detail", id=module.id))


@bp.route("/settings/custom-modules/<int:id>/toggle", methods=["POST"])
@login_required
def custom_module_toggle(id):
    module = CustomModule.query.get_or_404(id)
    module.is_active = not module.is_active
    db.session.commit()
    flash("Custom module status updated.", "success")
    return redirect(url_for("integrations.custom_modules"))


@bp.route("/settings/workflows", methods=["GET", "POST"])
@login_required
def workflows():
    if request.method == "POST":
        rule = WorkflowRule(name=request.form["name"].strip(), trigger_event=request.form.get("trigger_event") or "stock.low", is_active=_bool("is_active"))
        db.session.add(rule)
        db.session.flush()
        if request.form.get("condition_field"):
            db.session.add(WorkflowCondition(workflow_id=rule.id, field_name=request.form["condition_field"], operator=request.form.get("condition_operator") or "equals", value=request.form.get("condition_value")))
        db.session.add(WorkflowAction(workflow_id=rule.id, action_type=request.form.get("action_type") or "send_notification", config_json=request.form.get("action_config") or "{}"))
        db.session.commit()
        flash("Workflow rule saved.", "success")
        return redirect(url_for("integrations.workflows"))
    return render_template("settings/workflows.html", title="Workflow Automation", rows=WorkflowRule.query.order_by(WorkflowRule.id.desc()).all())


@bp.route("/settings/scheduled-jobs", methods=["GET", "POST"])
@login_required
def scheduled_jobs():
    if request.method == "POST":
        config = _json_text("config_json")
        if config is False:
            return redirect(url_for("integrations.scheduled_jobs"))
        db.session.add(ScheduledJob(name=request.form["name"].strip(), job_type=request.form.get("job_type") or "low_stock_alert", frequency=request.form.get("frequency") or "Daily", time_of_day=request.form.get("time_of_day") or "09:00", config_json=config, is_active=_bool("is_active")))
        db.session.commit()
        flash("Scheduled job saved.", "success")
        return redirect(url_for("integrations.scheduled_jobs"))
    return render_template("settings/foundation_list.html", title="Scheduled Jobs", rows=ScheduledJob.query.order_by(ScheduledJob.id.desc()).all(), kind="scheduled_jobs")


@bp.route("/settings/scheduled-jobs/run-due", methods=["POST"])
@login_required
def run_due_jobs():
    logs = run_scheduled_jobs()
    flash(f"Ran {len(logs)} scheduled job(s).", "success")
    return redirect(url_for("integrations.scheduled_jobs"))


@bp.route("/reports/communication-logs")
@login_required
def communication_logs():
    return render_template("reports/foundation_logs.html", title="Communication Logs", rows=CommunicationLog.query.order_by(CommunicationLog.id.desc()).limit(500).all(), kind="communication")


@bp.route("/reports/webhook-logs")
@login_required
def webhook_logs():
    return render_template("reports/foundation_logs.html", title="Webhook Logs", rows=WebhookLog.query.order_by(WebhookLog.id.desc()).limit(500).all(), incoming=IncomingWebhookLog.query.order_by(IncomingWebhookLog.id.desc()).limit(200).all(), kind="webhook")


@bp.route("/reports/scheduler-logs")
@login_required
def scheduler_logs():
    return render_template("reports/foundation_logs.html", title="Scheduler Logs", rows=ScheduledJobLog.query.order_by(ScheduledJobLog.id.desc()).limit(500).all(), kind="scheduler")
