import os
from pathlib import Path

import pymysql
from flask import Flask, abort, render_template, request
from flask_login import current_user

from config import get_config
from app.extensions import csrf, db, login_manager, migrate


def create_database_if_missing(config):
    if config.SQLALCHEMY_DATABASE_URI.startswith("mysql"):
        conn = pymysql.connect(
            host=config.DB_HOST,
            port=int(config.DB_PORT),
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            charset="utf8mb4",
            autocommit=True,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            conn.close()


def create_app():
    app = Flask(__name__)
    config = get_config()
    app.config.from_object(config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    create_database_if_missing(config)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.routes import register_blueprints

    register_blueprints(app)
    from app.services.schema_service import ensure_invoice_schema

    ensure_invoice_schema(app)

    @app.before_request
    def enforce_role_permissions():
        if request.endpoint in {None, "static"} or request.endpoint.startswith("static"):
            return None
        if request.endpoint.startswith("auth.") or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            return None
        if not current_user.is_active:
            abort(403)
        module = _permission_module(request.endpoint)
        if not module:
            return None
        action = _permission_action(request.endpoint, request.method)
        if not current_user.has_permission(module, action):
            try:
                from app.models import AuditLog

                db.session.add(AuditLog(user_id=current_user.id, action="Permission Denied", module=module, record_id=None, ip_address=request.remote_addr, user_agent=request.user_agent.string[:255]))
                db.session.commit()
            except Exception:
                db.session.rollback()
            abort(403)
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.datatables.net https://code.jquery.com https://checkout.razorpay.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.datatables.net; "
            "font-src 'self' https://cdn.jsdelivr.net data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.razorpay.com https://graph.facebook.com;",
        )
        return response

    @app.context_processor
    def inject_globals():
        from app.models import Branch, Company, CompanySetting, CustomModule

        try:
            company = Company.query.filter_by(is_active=True).first() or CompanySetting.query.first()
            branches = Branch.query.filter_by(status=True).order_by(Branch.name).all()
            custom_modules_nav = CustomModule.query.filter_by(is_active=True, show_in_sidebar=True).order_by(CustomModule.name).all()
        except Exception:
            company = None
            branches = []
            custom_modules_nav = []
        return {"company": company, "branches": branches, "custom_modules_nav": custom_modules_nav, "app_name": "Vyapara ERP"}

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/error.html", code=400, title="Bad Request"), 400

    @app.errorhandler(401)
    def unauthorized(error):
        return render_template("errors/error.html", code=401, title="Unauthorized"), 401

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/error.html", code=403, title="Forbidden"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/error.html", code=404, title="Not Found"), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template("errors/error.html", code=500, title="Server Error"), 500

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        print("Database tables created.")

    @app.cli.group("recurring")
    def recurring_cli():
        """Recurring invoice jobs."""

    @recurring_cli.command("run")
    def recurring_run():
        from app.services.recurring_service import generate_due_recurring

        generated = generate_due_recurring()
        print(f"Generated {len(generated)} recurring invoice(s).")

    @app.cli.group("reports")
    def reports_cli():
        """Scheduled report jobs."""

    @reports_cli.command("send-due")
    def reports_send_due():
        from app.services.report_mailer import send_due_reports

        sent = send_due_reports()
        print(f"Sent {len(sent)} scheduled report(s).")

    @app.cli.group("scheduler")
    def scheduler_cli():
        """Automation and scheduled job runner."""

    @scheduler_cli.command("run")
    def scheduler_run():
        from app.services.scheduler_service import run_scheduled_jobs

        logs = run_scheduled_jobs()
        print(f"Ran {len(logs)} scheduled job(s).")

    return app


PUBLIC_ENDPOINTS = {
    "invoices.pay",
    "invoices.create_order",
    "invoices.payment_callback",
}


def _permission_module(endpoint):
    blueprint = endpoint.split(".", 1)[0]
    mapping = {
        "dashboard": "dashboard",
        "products": "products",
        "masters": "settings",
        "price_lists": "products",
        "parties": "sales",
        "purchases": "purchases",
        "purchase_orders": "purchases",
        "invoices": "sales",
        "sales": "sales",
        "notes": "sales",
        "recurring": "sales",
        "manufacturing": "inventory",
        "stock": "inventory",
        "pos": "pos",
        "accounts": "accounts",
        "reports": "reports",
        "settings": "settings",
        "integrations": "settings",
        "api": "products",
        "search": "dashboard",
    }
    return mapping.get(blueprint)


def _permission_action(endpoint, method):
    name = endpoint.rsplit(".", 1)[-1]
    if any(word in name for word in ["delete", "toggle", "cancel", "revoke", "disable"]):
        return "delete"
    if method == "GET":
        if name.endswith(("print", "pdf", "receipt")):
            return "print"
        if "export" in name:
            return "export"
        return "view"
    if any(word in name for word in ["edit", "update", "permissions", "default", "approve"]):
        return "edit"
    if any(word in name for word in ["print", "pdf"]):
        return "print"
    return "create"
