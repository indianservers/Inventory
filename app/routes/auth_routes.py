from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import AuditLog, User

bp = Blueprint("auth", __name__)


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

