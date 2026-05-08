import secrets
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import ApiToken, AppSetting, AuditLog, CompanySetting, Permission, Role, RolePermission, Tax, User
from app.services.audit_service import record_audit
from app.services.backup_service import backup_uploads

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
