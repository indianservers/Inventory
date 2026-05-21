import secrets
from datetime import datetime
from pathlib import Path

import requests
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, render_template_string, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import ApiToken, AppSetting, AuditLog, Branch, Company, CompanySetting, Currency, ExchangeRateLog, Permission, PrintTemplate, Register, Role, RolePermission, ScheduledReport, Tax, User, Warehouse
from app.services.audit_service import record_audit
from app.services.backup_service import backup_uploads
from app.services.report_mailer import send_due_reports, send_report_now
from app.utils.tax_validation import is_valid_gstin, is_valid_trn

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/company", methods=["GET", "POST"])
@login_required
def company():
    company_row = Company.query.first()
    setting = CompanySetting.query.first()
    if not company_row:
        company_row = Company()
        if setting:
            company_row.legal_name = setting.company_name
            company_row.trade_name = setting.company_name
            company_row.logo = setting.logo
            company_row.address = setting.address
            company_row.city = setting.city
            company_row.state = setting.state
            company_row.country = setting.country
            company_row.postal_code = setting.postal_code
            company_row.phone = setting.phone
            company_row.email = setting.email
            company_row.website = setting.website
            company_row.tax_number = setting.tax_number
            company_row.currency = setting.currency
            company_row.financial_year_start_month = setting.financial_year_start.month if setting.financial_year_start else 4
            company_row.invoice_prefix = setting.invoice_prefix
            company_row.purchase_prefix = setting.purchase_prefix
            company_row.quotation_prefix = setting.quotation_prefix
            company_row.receipt_prefix = setting.receipt_prefix
            company_row.payment_prefix = setting.payment_prefix
    if request.method == "POST":
        if not request.form.get("legal_name", "").strip():
            flash("Company legal name is required.", "danger")
            return redirect(url_for("settings.company"))
        tax_number = request.form.get("tax_number")
        if tax_number and not (is_valid_gstin(tax_number) or is_valid_trn(tax_number)):
            flash("Invalid tax registration number. Enter a valid GSTIN or UAE TRN.", "danger")
            return redirect(url_for("settings.company"))
        for field in ["legal_name", "trade_name", "address", "city", "state", "country", "postal_code", "phone", "email", "website", "tax_number", "currency", "invoice_prefix", "purchase_prefix", "quotation_prefix", "receipt_prefix", "payment_prefix"]:
            setattr(company_row, field, request.form.get(field))
        company_row.financial_year_start_month = int(request.form.get("financial_year_start_month") or 4)
        logo = request.files.get("logo")
        if logo and logo.filename:
            extension = logo.filename.rsplit(".", 1)[-1].lower() if "." in logo.filename else ""
            if extension in {"png", "jpg", "jpeg", "webp"}:
                upload_dir = Path(current_app.config["UPLOAD_FOLDER"]) / "company"
                upload_dir.mkdir(parents=True, exist_ok=True)
                filename = secure_filename(f"logo.{extension}")
                logo.save(upload_dir / filename)
                company_row.logo = f"uploads/company/{filename}"
        db.session.add(company_row)
        setting = _sync_company_setting(company_row, setting)
        db.session.add(setting)
        db.session.flush()
        record_audit("Update", "Company", company_row.id, new_data={"legal_name": company_row.legal_name, "trade_name": company_row.trade_name})
        db.session.commit(); flash("Company profile saved.", "success")
        return redirect(url_for("settings.company"))
    return render_template("settings/company.html", title="Company Profile", setting=company_row)


@bp.route("/business-profile", methods=["GET", "POST"])
@login_required
def business_profile():
    setting = CompanySetting.query.first()
    if not setting:
        setting = CompanySetting(company_name="Vyapara ERP")
        db.session.add(setting)
        db.session.flush()
    profile_map = _business_profile_map()
    if request.method == "POST":
        business_type = request.form.get("business_type") or "Trading"
        setting.business_type = business_type
        selected = profile_map.get(business_type, profile_map["Custom"])
        setting.enable_barcode = "Barcode" in selected["modules"]
        setting.enable_batch_tracking = "Batch / Expiry" in selected["modules"]
        setting.enable_expiry_tracking = "Batch / Expiry" in selected["modules"]
        setting.enable_negative_stock = bool(request.form.get("enable_negative_stock"))
        record_audit("Update", "Business Profile", setting.id, new_data={"business_type": business_type, "modules": selected["modules"]})
        db.session.commit()
        flash("Business profile saved. Module recommendations are now active for new workflows.", "success")
        return redirect(url_for("settings.business_profile"))
    return render_template("settings/business_profile.html", title="Business Profile", setting=setting, profiles=profile_map)


def _business_profile_map():
    return {
        "Retail shop": {"modules": ["POS", "Barcode", "Inventory", "Loyalty"], "focus": "Fast billing, customer lookup and inventory accuracy."},
        "Restaurant": {"modules": ["Tables", "KOT", "Modifiers", "Kitchen Screen", "Tips"], "focus": "Dine-in, takeaway, delivery and kitchen coordination."},
        "Supermarket": {"modules": ["POS", "Barcode", "Weighing Scale", "Fast Checkout", "Batch / Expiry"], "focus": "High-volume scanning, price checks and quick checkout."},
        "Pharmacy": {"modules": ["Batch / Expiry", "Prescription", "Controlled Medicine", "GST"], "focus": "Expiry, batch traceability and prescription capture."},
        "Hardware": {"modules": ["Inventory", "Wholesale Pricing", "Credit Limit", "Stock Transfers"], "focus": "Bulk billing, heavy inventory and supplier replenishment."},
        "Garments": {"modules": ["Variants", "Size / Color Matrix", "Barcode", "Promotions"], "focus": "Variant-rich catalog and seasonal pricing."},
        "Electronics": {"modules": ["Serial Numbers", "Warranty", "Barcode", "Returns"], "focus": "Serial traceability, warranty and exchange flows."},
        "Services": {"modules": ["Service Items", "Staff Assignment", "Appointments", "Receivables"], "focus": "Service billing and staff performance."},
        "Trading": {"modules": ["Sales", "Purchases", "Inventory", "Accounting"], "focus": "End-to-end trading operations."},
        "Wholesale": {"modules": ["Customer Price Lists", "Bulk Discount", "Credit Limit", "E-way Bill"], "focus": "Customer-specific pricing and credit control."},
        "Manufacturing": {"modules": ["BOM", "Production Orders", "Raw Material Consumption", "Inventory"], "focus": "Assembly, material planning and production posting."},
        "Custom": {"modules": ["POS", "Inventory", "Sales", "Purchases", "Accounting"], "focus": "Flexible configuration for mixed operations."},
    }


@bp.route("/users")
@login_required
def users():
    status = request.args.get("status", "all")
    query = User.query.join(Role)
    if status == "active":
        query = query.filter(User.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(User.is_active.is_(False))
    return render_template("settings/users.html", title="Users", users=query.order_by(User.name).all(), roles=Role.query.order_by(Role.name).all(), status=status)


@bp.route("/users/create", methods=["GET", "POST"])
@login_required
def user_create():
    user = User(is_active=True)
    return _user_form(user, "Create User")


@bp.route("/users/<int:id>/edit", methods=["GET", "POST"])
@login_required
def user_edit(id):
    return _user_form(User.query.get_or_404(id), "Edit User")


@bp.route("/users/<int:id>/toggle", methods=["POST"])
@login_required
def user_toggle(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "warning")
        return redirect(url_for("settings.users"))
    user.is_active = not user.is_active
    record_audit("Update", "User", user.id, new_data={"is_active": user.is_active})
    db.session.commit()
    flash(f"{user.name} is now {'active' if user.is_active else 'inactive'}.", "success")
    return redirect(url_for("settings.users"))


@bp.route("/roles", methods=["GET", "POST"])
@login_required
def roles():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Role name is required.", "danger")
            return redirect(url_for("settings.roles"))
        if Role.query.filter(Role.name == name).first():
            flash("Role name already exists.", "danger")
            return redirect(url_for("settings.roles"))
        role = Role(name=name, description=request.form.get("description"), is_system=False)
        db.session.add(role)
        db.session.flush()
        for permission in Permission.query.all():
            db.session.add(RolePermission(role_id=role.id, permission_id=permission.id, granted=False))
        record_audit("Create", "Role", role.id, new_data={"name": role.name})
        db.session.commit()
        flash("Role created. Configure permissions next.", "success")
        return redirect(url_for("settings.role_permissions", id=role.id))
    return render_template("settings/roles.html", title="Roles & Permissions", roles=Role.query.order_by(Role.name).all(), permissions=Permission.query.order_by(Permission.module, Permission.action).all())


@bp.route("/roles/<int:id>/edit", methods=["POST"])
@login_required
def role_edit(id):
    role = Role.query.get_or_404(id)
    role.description = request.form.get("description")
    if not role.is_system:
        name = request.form.get("name", "").strip()
        if not name:
            flash("Role name is required.", "danger")
            return redirect(url_for("settings.roles"))
        duplicate = Role.query.filter(Role.name == name, Role.id != role.id).first()
        if duplicate:
            flash("Role name already exists.", "danger")
            return redirect(url_for("settings.roles"))
        role.name = name
    record_audit("Update", "Role", role.id, new_data={"name": role.name, "description": role.description})
    db.session.commit()
    flash("Role updated.", "success")
    return redirect(url_for("settings.roles"))


@bp.route("/branches", methods=["GET", "POST"])
@login_required
def branches():
    if request.method == "POST":
        branch = Branch()
        ok = _save_branch(branch)
        if ok:
            db.session.add(branch)
            db.session.flush()
            record_audit("Create", "Branch", branch.id, new_data={"code": branch.code, "name": branch.name})
            db.session.commit()
            flash("Branch created.", "success")
            return redirect(url_for("settings.branches"))
    status = request.args.get("status", "all")
    query = Branch.query
    if status == "active":
        query = query.filter(Branch.status.is_(True))
    elif status == "inactive":
        query = query.filter(Branch.status.is_(False))
    return render_template("settings/branches.html", title="Branches", branches=query.order_by(Branch.name).all(), status=status)


@bp.route("/branches/<int:id>/edit", methods=["GET", "POST"])
@login_required
def branch_edit(id):
    branch = Branch.query.get_or_404(id)
    if request.method == "POST" and _save_branch(branch):
        record_audit("Update", "Branch", branch.id, new_data={"code": branch.code, "name": branch.name})
        db.session.commit()
        flash("Branch updated.", "success")
        return redirect(url_for("settings.branches"))
    return render_template("settings/branch_form.html", title="Edit Branch", branch=branch)


@bp.route("/branches/<int:id>/toggle", methods=["POST"])
@login_required
def branch_toggle(id):
    branch = Branch.query.get_or_404(id)
    branch.status = not branch.status
    record_audit("Update", "Branch", branch.id, new_data={"status": branch.status})
    db.session.commit()
    flash(f"Branch {'reactivated' if branch.status else 'deactivated'}.", "success")
    return redirect(url_for("settings.branches"))


@bp.route("/warehouses", methods=["GET", "POST"])
@login_required
def warehouses():
    if request.method == "POST":
        warehouse = Warehouse()
        ok = _save_warehouse(warehouse)
        if ok:
            db.session.add(warehouse)
            db.session.flush()
            record_audit("Create", "Warehouse", warehouse.id, new_data={"code": warehouse.code, "name": warehouse.name})
            db.session.commit()
            flash("Warehouse created.", "success")
            return redirect(url_for("settings.warehouses"))
    status = request.args.get("status", "all")
    query = Warehouse.query
    if status == "active":
        query = query.filter(Warehouse.status.is_(True))
    elif status == "inactive":
        query = query.filter(Warehouse.status.is_(False))
    return render_template("settings/warehouses.html", title="Warehouses", warehouses=query.order_by(Warehouse.name).all(), branches=Branch.query.order_by(Branch.name).all(), status=status)


@bp.route("/warehouses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def warehouse_edit(id):
    warehouse = Warehouse.query.get_or_404(id)
    if request.method == "POST" and _save_warehouse(warehouse):
        record_audit("Update", "Warehouse", warehouse.id, new_data={"code": warehouse.code, "name": warehouse.name})
        db.session.commit()
        flash("Warehouse updated.", "success")
        return redirect(url_for("settings.warehouses"))
    return render_template("settings/warehouse_form.html", title="Edit Warehouse", warehouse=warehouse, branches=Branch.query.order_by(Branch.name).all())


@bp.route("/warehouses/<int:id>/toggle", methods=["POST"])
@login_required
def warehouse_toggle(id):
    warehouse = Warehouse.query.get_or_404(id)
    warehouse.status = not warehouse.status
    record_audit("Update", "Warehouse", warehouse.id, new_data={"status": warehouse.status})
    db.session.commit()
    flash(f"Warehouse {'reactivated' if warehouse.status else 'deactivated'}.", "success")
    return redirect(url_for("settings.warehouses"))


@bp.route("/registers", methods=["GET", "POST"])
@login_required
def registers():
    if request.method == "POST":
        register = Register()
        ok = _save_register(register)
        if ok:
            db.session.add(register)
            db.session.flush()
            record_audit("Create", "Register", register.id, new_data={"code": register.code, "name": register.name})
            db.session.commit()
            flash("POS register created.", "success")
            return redirect(url_for("settings.registers"))
    status = request.args.get("status", "all")
    query = Register.query
    if status == "active":
        query = query.filter(Register.status.is_(True))
    elif status == "inactive":
        query = query.filter(Register.status.is_(False))
    return render_template("settings/registers.html", title="POS Registers", registers=query.order_by(Register.name).all(), branches=Branch.query.order_by(Branch.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all(), status=status)


@bp.route("/registers/<int:id>/edit", methods=["GET", "POST"])
@login_required
def register_edit(id):
    register = Register.query.get_or_404(id)
    if request.method == "POST" and _save_register(register):
        record_audit("Update", "Register", register.id, new_data={"code": register.code, "name": register.name})
        db.session.commit()
        flash("POS register updated.", "success")
        return redirect(url_for("settings.registers"))
    return render_template("settings/register_form.html", title="Edit POS Register", register=register, branches=Branch.query.order_by(Branch.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all())


@bp.route("/registers/<int:id>/toggle", methods=["POST"])
@login_required
def register_toggle(id):
    register = Register.query.get_or_404(id)
    register.status = not register.status
    record_audit("Update", "Register", register.id, new_data={"status": register.status})
    db.session.commit()
    flash(f"POS register {'reactivated' if register.status else 'deactivated'}.", "success")
    return redirect(url_for("settings.registers"))


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
        template.module = request.form.get("module") or template.template_type
        template.paper_size = request.form.get("paper_size") or "A4"
        template.show_header = bool(request.form.get("show_header"))
        template.show_footer = bool(request.form.get("show_footer"))
        template.show_logo = bool(request.form.get("show_logo"))
        template.column_config = request.form.get("column_config")
        template.terms_conditions = request.form.get("terms_conditions")
        template.html = request.form.get("html")
        template.is_default = bool(request.form.get("is_default"))
        if template.is_default:
            PrintTemplate.query.filter_by(template_type=template.template_type).update({PrintTemplate.is_default: False})
        db.session.add(template)
        db.session.commit()
        flash("Print template saved.", "success")
        return redirect(url_for("settings.templates"))
    return render_template("settings/template_editor.html", title=title, template=template, template_types=TEMPLATE_TYPES, variables=TEMPLATE_VARIABLES)


def _sync_company_setting(company_row, setting=None):
    setting = setting or CompanySetting()
    setting.company_name = company_row.company_name
    setting.logo = company_row.logo
    setting.address = company_row.address
    setting.city = company_row.city
    setting.state = company_row.state
    setting.country = company_row.country
    setting.postal_code = company_row.postal_code
    setting.phone = company_row.phone
    setting.email = company_row.email
    setting.website = company_row.website
    setting.tax_number = company_row.tax_number
    setting.currency = company_row.currency
    if company_row.financial_year_start_month:
        from datetime import date

        setting.financial_year_start = date(date.today().year, company_row.financial_year_start_month, 1)
    setting.invoice_prefix = company_row.invoice_prefix
    setting.purchase_prefix = company_row.purchase_prefix
    setting.quotation_prefix = company_row.quotation_prefix
    setting.receipt_prefix = company_row.receipt_prefix
    setting.payment_prefix = company_row.payment_prefix
    return setting


def _save_branch(branch):
    branch.name = request.form.get("name", "").strip()
    branch.code = request.form.get("code", "").strip().upper()
    if not branch.name or not branch.code:
        flash("Branch name and code are required.", "danger")
        return False
    duplicate = Branch.query.filter(Branch.code == branch.code, Branch.id != (branch.id or 0)).first()
    if duplicate:
        flash("Branch code already exists.", "danger")
        return False
    tax_number = request.form.get("tax_number")
    if tax_number and not (is_valid_gstin(tax_number) or is_valid_trn(tax_number)):
        flash("Invalid branch tax registration number. Enter a valid GSTIN or UAE TRN.", "danger")
        return False
    for field in ["address", "contact_person", "phone", "email", "tax_number"]:
        setattr(branch, field, request.form.get(field))
    branch.status = bool(request.form.get("status"))
    return True


def _save_warehouse(warehouse):
    warehouse.name = request.form.get("name", "").strip()
    warehouse.code = request.form.get("code", "").strip().upper()
    if not warehouse.name or not warehouse.code:
        flash("Warehouse name and code are required.", "danger")
        return False
    duplicate = Warehouse.query.filter(Warehouse.code == warehouse.code, Warehouse.id != (warehouse.id or 0)).first()
    if duplicate:
        flash("Warehouse code already exists.", "danger")
        return False
    warehouse.branch_id = request.form.get("branch_id") or None
    for field in ["address", "contact_person", "phone", "email"]:
        setattr(warehouse, field, request.form.get(field))
    warehouse.status = bool(request.form.get("status"))
    return True


def _save_register(register):
    register.name = request.form.get("name", "").strip()
    register.code = request.form.get("code", "").strip().upper()
    if not register.name or not register.code:
        flash("Register name and code are required.", "danger")
        return False
    duplicate = Register.query.filter(Register.code == register.code, Register.id != (register.id or 0)).first()
    if duplicate:
        flash("Register code already exists.", "danger")
        return False
    register.branch_id = request.form.get("branch_id")
    register.warehouse_id = request.form.get("warehouse_id")
    if not register.branch_id or not register.warehouse_id:
        flash("Register must be linked to a branch and warehouse.", "danger")
        return False
    register.receipt_printer = request.form.get("receipt_printer")
    register.status = bool(request.form.get("status"))
    return True


def _user_form(user, title):
    roles = Role.query.order_by(Role.name).all()
    if request.method == "POST":
        is_new = user.id is None
        user.name = request.form.get("name", "").strip()
        user.email = request.form.get("email", "").strip().lower()
        user.phone = request.form.get("phone")
        user.role_id = request.form.get("role_id")
        user.is_active = bool(request.form.get("is_active"))
        password = request.form.get("password", "")
        if not user.name or not user.email or not user.role_id:
            flash("Name, email and role are required.", "danger")
            return render_template("settings/user_form.html", title=title, user=user, roles=roles)
        duplicate = User.query.filter(User.email == user.email, User.id != (user.id or 0)).first()
        if duplicate:
            flash("A user with this email already exists.", "danger")
            return render_template("settings/user_form.html", title=title, user=user, roles=roles)
        if not user.id and not password:
            flash("Password is required for new users.", "danger")
            return render_template("settings/user_form.html", title=title, user=user, roles=roles)
        if password:
            user.set_password(password)
        db.session.add(user)
        db.session.flush()
        record_audit("Create" if is_new else "Update", "User", user.id, new_data={"email": user.email, "role_id": user.role_id, "is_active": user.is_active})
        db.session.commit()
        flash("User saved.", "success")
        return redirect(url_for("settings.users"))
    return render_template("settings/user_form.html", title=title, user=user, roles=roles)


def _sample_template_context():
    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    company = CompanySetting.query.first() or Obj(company_name="Vyapara ERP", address="Company Address", tax_number="GSTIN")
    customer = Obj(name="Sample Customer", billing_address="Customer Address")
    invoice = Obj(invoice_no="INV-SAMPLE", invoice_date="2026-05-21", grand_total=1180, customer=customer)
    items = [Obj(product=Obj(name="Sample Item", hsn_code="9983"), quantity=2, rate=500, tax_amount=180, line_total=1180)]
    return {"company": company, "invoice": invoice, "sale": invoice, "items": items}


TEMPLATE_TYPES = ["pos_receipt", "tax_invoice", "sales_invoice", "sales_order", "delivery_note", "delivery_challan", "credit_note", "refund_receipt", "purchase_order", "purchase_bill", "payment_receipt", "barcode_label", "packing_slip", "quotation", "receipt"]
TEMPLATE_VARIABLES = ["company.company_name", "company.address", "invoice.invoice_no", "invoice.customer.name", "invoice.invoice_date", "invoice.grand_total", "items"]
DEFAULT_TEMPLATE_HTML = """<div style="font-family:Arial,sans-serif"><h1>{{ company.company_name }}</h1><h2>Invoice {{ invoice.invoice_no }}</h2><p>{{ invoice.customer.name }}</p><table width="100%" border="1" cellspacing="0" cellpadding="6">{% for item in items %}<tr><td>{{ item.product.name }}</td><td>{{ item.quantity }}</td><td>{{ item.line_total }}</td></tr>{% endfor %}</table><h3>Total {{ invoice.grand_total }}</h3></div>"""
