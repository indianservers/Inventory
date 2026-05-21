import base64
import os
from datetime import datetime, timedelta
from io import BytesIO

import qrcode
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import AuditLog, User

bp = Blueprint("auth", __name__)

try:
    import pyotp
except ImportError:  # pragma: no cover - dependency is declared for deployments
    pyotp = None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if user and user.is_active and user.check_password(request.form.get("password", "")):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.add(AuditLog(user_id=user.id, action="Login", module="Auth", ip_address=request.remote_addr, user_agent=request.user_agent.string[:255]))
            db.session.commit()
            if user.totp_enabled:
                session["2fa_verified"] = False
                return redirect(url_for("auth.two_factor_check"))
            session["2fa_verified"] = True
            return redirect(url_for("dashboard.index"))
        flash("Invalid login or inactive account.", "danger")
    return render_template("auth/login.html", title="Login")


@bp.route("/logout")
@login_required
def logout():
    db.session.add(AuditLog(user_id=current_user.id, action="Logout", module="Auth", ip_address=request.remote_addr, user_agent=request.user_agent.string[:255]))
    db.session.commit()
    logout_user()
    flash("Logged out successfully.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form["name"]
        current_user.phone = request.form.get("phone")
        db.session.commit()
        flash("Profile updated.", "success")
    return render_template("auth/profile.html", title="My Profile")


@bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    if not current_user.check_password(request.form.get("current_password", "")):
        flash("Current password is incorrect.", "danger")
    else:
        current_user.set_password(request.form["new_password"])
        db.session.commit()
        flash("Password changed.", "success")
    return redirect(url_for("auth.profile"))


@bp.route("/forgot-password")
def forgot_password():
    return render_template("auth/forgot_password.html", title="Forgot Password")


@bp.route("/auth/2fa/setup")
@login_required
def two_factor_setup():
    if not pyotp:
        flash("Install pyotp to enable 2FA.", "warning"); return redirect(url_for("auth.profile"))
    if not current_user.totp_secret:
        current_user.totp_secret = pyotp.random_base32()
        db.session.commit()
    uri = pyotp.totp.TOTP(current_user.totp_secret).provisioning_uri(name=current_user.email, issuer_name="Vyapara ERP")
    img = qrcode.make(uri)
    out = BytesIO(); img.save(out, format="PNG")
    qr_image = "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    return render_template("auth/2fa_setup.html", title="Setup 2FA", qr_image=qr_image, secret=current_user.totp_secret)


@bp.route("/auth/2fa/verify", methods=["POST"])
@login_required
def two_factor_verify():
    if not pyotp:
        flash("Install pyotp to enable 2FA.", "warning"); return redirect(url_for("auth.profile"))
    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(request.form.get("code", "")):
        flash("Invalid 2FA code.", "danger"); return redirect(url_for("auth.two_factor_setup"))
    codes = [base64.b32encode(os.urandom(5)).decode("ascii").rstrip("=") for _ in range(10)]
    from werkzeug.security import generate_password_hash
    current_user.backup_codes = "\n".join(generate_password_hash(code) for code in codes)
    current_user.totp_enabled = True
    db.session.commit()
    return render_template("auth/2fa_codes.html", title="Backup Codes", codes=codes)


@bp.route("/auth/2fa/disable", methods=["POST"])
@login_required
def two_factor_disable():
    if not current_user.check_password(request.form.get("password", "")):
        flash("Password confirmation failed.", "danger"); return redirect(url_for("auth.profile"))
    current_user.totp_enabled = False; current_user.totp_secret = None; current_user.backup_codes = None
    db.session.commit(); flash("2FA disabled.", "success")
    return redirect(url_for("auth.profile"))


@bp.route("/auth/2fa/check", methods=["GET", "POST"])
@login_required
def two_factor_check():
    if not pyotp:
        session["2fa_verified"] = True
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        if session.get("2fa_locked_until") and datetime.utcnow().timestamp() < session["2fa_locked_until"]:
            flash("Too many attempts. Try again later.", "danger"); return redirect(url_for("auth.two_factor_check"))
        code = request.form.get("code", "")
        valid = pyotp.TOTP(current_user.totp_secret).verify(code)
        if not valid and current_user.backup_codes:
            from werkzeug.security import check_password_hash
            valid = any(check_password_hash(hashed, code) for hashed in current_user.backup_codes.splitlines())
        if valid:
            session["2fa_verified"] = True; session["2fa_attempts"] = 0
            return redirect(url_for("dashboard.index"))
        session["2fa_attempts"] = session.get("2fa_attempts", 0) + 1
        if session["2fa_attempts"] >= 3:
            session["2fa_locked_until"] = (datetime.utcnow() + timedelta(minutes=5)).timestamp()
        flash("Invalid 2FA code.", "danger")
    return render_template("auth/2fa_check.html", title="Two-Factor Authentication")
