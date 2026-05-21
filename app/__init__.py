import os
from pathlib import Path

import pymysql
from flask import Flask, render_template

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

    @app.context_processor
    def inject_globals():
        from app.models import CompanySetting

        try:
            company = CompanySetting.query.first()
        except Exception:
            company = None
        return {"company": company, "app_name": "Vyapara ERP"}

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

    return app
