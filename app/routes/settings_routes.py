import secrets
from datetime import datetime
from pathlib import Path

import requests
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, render_template_string, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import ApiToken, AppSetting, AuditLog, CompanySetting, Currency, ExchangeRateLog, Permission, PrintTemplate, Role, RolePermission, ScheduledReport, Tax, User
from app.services.audit_service import record_audit
from app.services.backup_service import backup_uploads
from app.services.report_mailer import send_due_reports, send_report_now

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/company", methods=["GET", "POST"])
@login_required
def company():
    setting = CompanySetting.query.first() or CompanySetting()
    if request.method == "POST":
        for field in ["company_name","business_type","address","city","state","country","postal_code","phone","email","website","tax_number","pan_number","currency","invoice_prefix","purchase_prefix","quotation_prefix","receipt_prefix","payment_prefix","tax_mode","default_invoice_terms"]:
            setattr(setting, field, request.form.get(field))
        setting.enable_negative_stock = bool(request.form.get("enable_negative_stock"))
        setting.enable_batch_tracking = bool(request.form.get("enable_batch_tracking"))
        setting.enable_expiry_tracking = bool(request.form.get("enable_expiry_tracking"))
        setting.enable_barcode = bool(request.form.get("enable_barcode"))
        logo = request.files.get("logo")
        if logo and logo.filename:
            extension = logo.filename.rsplit(".", 1)[-1].lower() if "." in logo.filename else ""
            if extension in {"png", "jpg", "jpeg", "webp"}:
                upload_dir = Path(current_app.config["UPLOAD_FOLDER"]) / "company"
                upload_dir.mkdir(parents=True, exist_ok=True)
                filename = secure_filename(f"logo.{extension}")
                logo.save(upload_dir / filename)
                setting.logo = f"uploads/company/{filename}"
        db.session.add(setting); db.session.commit(); flash("Company settings saved.", "success")
        return redirect(url_for("settings.company"))
    return render_template("settings/company.html", title="Company Settings", setting=setting)


@bp.route("/users")
@login_required
def users():
    return render_template("settings/users.html", title="Users & Roles", users=User.query.all(), roles=Role.query.all())


@bp.route("/roles")
@login_required
def roles():
    return render_template("settings/roles.html", title="Role Management", roles=Role.query.all(), permissions=Permission.query.all())


@bp.route("/roles/<int:id>/permissions", methods=["GET", "POST"])
@login_required
def role_permissions(id):
    role = Role.query.get_or_404(id)
    permissions = Permission.query.order_by(Permission.module, Permission.action).all()
    if request.method == "POST":
        selected = {int(value) for value in request.form.getlist("permission_id[]")}
        RolePermission.query.filter_by(role_id=role.id).delete()
        for permission in permissions:
            if permission.id in selected:
                db.session.add(RolePermission(role_id=role.id, permission_id=permission.id, granted=True))
        record_audit("Update", "RolePermission", role.id, new_data={"permissions": sorted(selected)})
        db.session.commit()
        flash("Role permissions updated.", "success")
        return redirect(url_for("settings.roles"))
    granted = {rp.permission_id for rp in role.permissions.filter_by(granted=True).all()}
    return render_template("settings/role_permissions.html", title=f"Permissions - {role.name}", role=role, permissions=permissions, granted=granted)


@bp.route("/audit")
@login_required
def audit():
    logs = AuditLog.query.order_by(AuditLog.id.desc()).limit(500).all()
    return render_template("settings/audit.html", title="Audit Trail", logs=logs)


@bp.route("/api-tokens", methods=["GET", "POST"])
@login_required
def api_tokens():
    plain_token = None
    if request.method == "POST":
        token = secrets.token_urlsafe(32)
        api_token = ApiToken(
            name=request.form["name"].strip(),
            token_hash=generate_password_hash(token),
            prefix=token[:12],
            user_id=request.form.get("user_id") or None,
        )
        db.session.add(api_token)
        record_audit("Create", "ApiToken", new_data={"name": api_token.name, "prefix": api_token.prefix})
        db.session.commit()
        plain_token = token
        flash("API token created. Copy it now; it will not be shown again.", "success")
    return render_template("settings/api_tokens.html", title="API Tokens", tokens=ApiToken.query.order_by(ApiToken.id.desc()).all(), users=User.query.order_by(User.name).all(), plain_token=plain_token)


@bp.route("/api-tokens/<int:id>/revoke")
@login_required
def revoke_api_token(id):
    token = ApiToken.query.get_or_404(id)
    token.is_active = False
    record_audit("Revoke", "ApiToken", token.id, new_data={"name": token.name, "prefix": token.prefix})
    db.session.commit()
    flash("API token revoked.", "success")
    return redirect(url_for("settings.api_tokens"))


@bp.route("/backup", methods=["GET", "POST"])
@login_required
def backup():
    if request.method == "POST":
        for key in ["backup_schedule_enabled", "backup_frequency", "backup_time", "backup_retention_days"]:
            setting = AppSetting.query.filter_by(key=key).first() or AppSetting(key=key)
            setting.value = request.form.get(key, "0") if key != "backup_schedule_enabled" else ("1" if request.form.get(key) else "0")
            db.session.add(setting)
        db.session.commit()
        flash("Backup schedule saved.", "success")
        return redirect(url_for("settings.backup"))
    settings = {row.key: row.value for row in AppSetting.query.filter(AppSetting.key.like("backup_%")).all()}
    return render_template("settings/backup.html", title="Backup & Restore", settings=settings)


@bp.route("/backup/uploads")
@login_required
def backup_upload_files():
    path = backup_uploads()
    return send_file(path, as_attachment=True)


@bp.route("/currencies", methods=["GET", "POST"])
@login_required
def currencies():
    if request.method == "POST":
        currency = Currency.query.filter_by(code=request.form["code"].upper()).first() or Currency(code=request.form["code"].upper())
        currency.name = request.form["name"]
        currency.symbol = request.form.get("symbol")
        currency.exchange_rate = request.form.get("exchange_rate") or 1
        currency.is_base = bool(request.form.get("is_base"))
        currency.auto_update = bool(request.form.get("auto_update"))
        if currency.is_base:
            Currency.query.update({Currency.is_base: False})
            currency.exchange_rate = 1
        db.session.add(currency)
        db.session.commit()
        flash("Currency saved.", "success")
        return redirect(url_for("settings.currencies"))
    return render_template("settings/currencies.html", title="Currencies", currencies=Currency.query.order_by(Currency.code).all())


@bp.route("/currencies/update-rates", methods=["POST"])
@login_required
def update_currency_rates():
    response = requests.get("https://api.exchangerate-api.com/v4/latest/INR", timeout=15)
    response.raise_for_status()
    rates = response.json().get("rates", {})
    for currency in Currency.query.filter(Currency.code != "INR").all():
        rate = rates.get(currency.code)
        if not rate:
            continue
        currency.exchange_rate = 1 / float(rate)
        currency.last_updated = datetime.utcnow()
        db.session.add(ExchangeRateLog(currency_id=currency.id, rate=currency.exchange_rate))
    db.session.commit()
    flash("Exchange rates updated.", "success")
    return redirect(url_for("settings.currencies"))


@bp.route("/templates/")
@login_required
def templates():
    rows = PrintTemplate.query.order_by(PrintTemplate.template_type, PrintTemplate.name).all()
    return render_template("settings/templates.html", title="Print Templates", templates=rows)


@bp.route("/templates/create", methods=["GET", "POST"])
@login_required
def template_create():
    template = PrintTemplate(template_type=request.args.get("type") or "sales_invoice", html=DEFAULT_TEMPLATE_HTML)
    return _template_form(template, "Create Print Template")


@bp.route("/templates/<int:id>/edit", methods=["GET", "POST"])
@login_required
def template_edit(id):
    return _template_form(PrintTemplate.query.get_or_404(id), "Edit Print Template")


@bp.route("/templates/<int:id>/default", methods=["POST"])
@login_required
def template_default(id):
    template = PrintTemplate.query.get_or_404(id)
    PrintTemplate.query.filter_by(template_type=template.template_type).update({PrintTemplate.is_default: False})
    template.is_default = True
    db.session.commit()
    flash(f"{template.name} is now default for {template.template_type}.", "success")
    return redirect(url_for("settings.templates"))


@bp.route("/templates/<int:id>/preview", methods=["GET", "POST"])
@login_required
def template_preview(id):
    template = PrintTemplate.query.get_or_404(id)
    html = request.form.get("html") if request.method == "POST" else template.html
    rendered = render_template_string(html or "", **_sample_template_context())
    if request.method == "POST":
        return jsonify({"html": rendered})
    return rendered


@bp.route("/templates/preview-live", methods=["POST"])
@login_required
def template_preview_live():
    rendered = render_template_string(request.form.get("html") or "", **_sample_template_context())
    return jsonify({"html": rendered})


@bp.route("/scheduled-reports/", methods=["GET", "POST"])
@login_required
def scheduled_reports():
    if request.method == "POST":
        report = ScheduledReport(
            name=request.form["name"],
            report_type=request.form["report_type"],
            frequency=request.form.get("frequency") or "Daily",
            day_of_week=request.form.get("day_of_week") or None,
            day_of_month=request.form.get("day_of_month") or None,
            time_of_day=request.form.get("time_of_day") or "09:00",
            recipient_emails=request.form.get("recipient_emails"),
            format=request.form.get("format") or "Excel",
            is_active=bool(request.form.get("is_active")),
            created_by=current_user.id,
        )
        db.session.add(report)
        db.session.commit()
        flash("Scheduled report saved.", "success")
        return redirect(url_for("settings.scheduled_reports"))
    return render_template("settings/scheduled_reports.html", title="Scheduled Reports", reports=ScheduledReport.query.order_by(ScheduledReport.id.desc()).all())


@bp.route("/scheduled-reports/<int:id>/run-now", methods=["POST"])
@login_required
def scheduled_report_run_now(id):
    report = ScheduledReport.query.get_or_404(id)
    ok = send_report_now(report)
    flash("Report sent." if ok else "Email not configured; report was not sent.", "success" if ok else "warning")
    return redirect(url_for("settings.scheduled_reports"))


@bp.route("/scheduled-reports/run-due", methods=["POST"])
@login_required
def scheduled_report_run_due():
    sent = send_due_reports()
    flash(f"Sent {len(sent)} due report(s).", "success")
    return redirect(url_for("settings.scheduled_reports"))


def _template_form(template, title):
    if request.method == "POST":
        template.name = request.form["name"]
        template.template_type = request.form["template_type"]
        template.html = request.form.get("html")
        template.is_default = bool(request.form.get("is_default"))
        if template.is_default:
            PrintTemplate.query.filter_by(template_type=template.template_type).update({PrintTemplate.is_default: False})
        db.session.add(template)
        db.session.commit()
        flash("Print template saved.", "success")
        return redirect(url_for("settings.templates"))
    return render_template("settings/template_editor.html", title=title, template=template, template_types=TEMPLATE_TYPES, variables=TEMPLATE_VARIABLES)


def _sample_template_context():
    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    company = CompanySetting.query.first() or Obj(company_name="Vyapara ERP", address="Company Address", tax_number="GSTIN")
    customer = Obj(name="Sample Customer", billing_address="Customer Address")
    invoice = Obj(invoice_no="INV-SAMPLE", invoice_date="2026-05-21", grand_total=1180, customer=customer)
    items = [Obj(product=Obj(name="Sample Item", hsn_code="9983"), quantity=2, rate=500, tax_amount=180, line_total=1180)]
    return {"company": company, "invoice": invoice, "sale": invoice, "items": items}


TEMPLATE_TYPES = ["sales_invoice", "purchase_order", "delivery_challan", "quotation", "receipt", "credit_note"]
TEMPLATE_VARIABLES = ["company.company_name", "company.address", "invoice.invoice_no", "invoice.customer.name", "invoice.invoice_date", "invoice.grand_total", "items"]
DEFAULT_TEMPLATE_HTML = """<div style="font-family:Arial,sans-serif"><h1>{{ company.company_name }}</h1><h2>Invoice {{ invoice.invoice_no }}</h2><p>{{ invoice.customer.name }}</p><table width="100%" border="1" cellspacing="0" cellpadding="6">{% for item in items %}<tr><td>{{ item.product.name }}</td><td>{{ item.quantity }}</td><td>{{ item.line_total }}</td></tr>{% endfor %}</table><h3>Total {{ invoice.grand_total }}</h3></div>"""
