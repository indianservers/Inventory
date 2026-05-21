def register_blueprints(app):
    from app.routes.auth_routes import bp as auth_bp
    from app.routes.dashboard_routes import bp as dashboard_bp
    from app.routes.master_routes import bp as master_bp
    from app.routes.party_routes import bp as party_bp
    from app.routes.product_routes import bp as product_bp
    from app.routes.purchase_routes import bp as purchase_bp
    from app.routes.purchase_order_routes import bp as purchase_order_bp
    from app.routes.pos_routes import bp as pos_bp
    from app.routes.price_routes import bp as price_bp
    from app.routes.note_routes import bp as note_bp
    from app.routes.recurring_routes import bp as recurring_bp
    from app.routes.manufacturing_routes import bp as manufacturing_bp
    from app.routes.sales_routes import bp as sales_bp
    from app.routes.invoice_routes import bp as invoice_bp
    from app.routes.stock_routes import bp as stock_bp
    from app.routes.accounts_routes import bp as accounts_bp
    from app.routes.reports_routes import bp as reports_bp
    from app.routes.settings_routes import bp as settings_bp
    from app.routes.integration_routes import bp as integration_bp
    from app.routes.api_routes import bp as api_bp
    from app.routes.search_routes import bp as search_bp

    for bp in [
        auth_bp,
        dashboard_bp,
        master_bp,
        party_bp,
        product_bp,
        purchase_bp,
        purchase_order_bp,
        pos_bp,
        price_bp,
        note_bp,
        recurring_bp,
        manufacturing_bp,
        sales_bp,
        invoice_bp,
        stock_bp,
        accounts_bp,
        reports_bp,
        settings_bp,
        integration_bp,
        api_bp,
        search_bp,
    ]:
        app.register_blueprint(bp)
