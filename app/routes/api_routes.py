from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from werkzeug.security import check_password_hash

from app.extensions import csrf, db
from app.models import ApiToken, AuditLog, Customer, Product, Purchase, Sale, Supplier

bp = Blueprint("api", __name__, url_prefix="/api")
RATE_LIMIT = {}
MAX_REQUESTS_PER_MINUTE = 120


@bp.app_errorhandler(404)
def api_not_found(error):
    if request.path.startswith("/api/"):
        return api_error("Resource not found", 404, "not_found")
    return render_template("errors/error.html", code=404, title="Not Found"), 404


@bp.app_errorhandler(405)
def api_method_not_allowed(error):
    if request.path.startswith("/api/"):
        return api_error("Method not allowed", 405, "method_not_allowed")
    return render_template("errors/error.html", code=405, title="Method Not Allowed"), 405


def product_json(p):
    return {
        "id": p.id,
        "sku": p.sku,
        "barcode": p.barcode,
        "name": p.name,
        "sales_price": float(p.sales_price or 0),
        "purchase_price": float(p.purchase_price or 0),
        "current_stock": float(p.current_stock or 0),
        "average_cost": float(p.average_cost or 0),
        "tax_rate": float(p.tax.rate if p.tax else 0),
    }


def api_error(message, status=400, code="bad_request", details=None):
    payload = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return jsonify(payload), status


def token_from_request():
    auth = request.headers.get("Authorization", "")
    return auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else request.headers.get("X-API-Token")


def check_rate_limit(token_row):
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=1)
    key = token_row.prefix
    RATE_LIMIT[key] = [stamp for stamp in RATE_LIMIT.get(key, []) if stamp > window_start]
    if len(RATE_LIMIT[key]) >= MAX_REQUESTS_PER_MINUTE:
        return False
    RATE_LIMIT[key].append(now)
    return True


def audit_api_request(token_row):
    db.session.add(AuditLog(user_id=token_row.user_id, action="API", module=request.endpoint or "api", record_id=token_row.id, new_data={"method": request.method, "path": request.path, "token": token_row.name}, ip_address=request.remote_addr, user_agent=request.user_agent.string[:255]))


def api_auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = token_from_request()
        if not token:
            return api_error("Missing API token", 401, "missing_token")
        token_row = ApiToken.query.filter_by(prefix=token[:12], is_active=True).first()
        if not token_row or not check_password_hash(token_row.token_hash, token):
            return api_error("Invalid API token", 401, "invalid_token")
        if not check_rate_limit(token_row):
            return api_error("API rate limit exceeded", 429, "rate_limited")
        token_row.last_used_at = datetime.utcnow()
        audit_api_request(token_row)
        db.session.commit()
        return fn(*args, **kwargs)

    return wrapper


def paginated_response(query, serializer, allowed_sort=None):
    allowed_sort = allowed_sort or {}
    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = min(max(int(request.args.get("per_page", 25) or 25), 1), 100)
    sort_by = request.args.get("sort_by")
    sort_dir = request.args.get("sort_dir", "asc")
    if sort_by in allowed_sort:
        col = allowed_sort[sort_by]
        query = query.order_by(col.desc() if sort_dir == "desc" else col.asc())
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"data": [serializer(row) for row in rows], "meta": {"page": page, "per_page": per_page, "total": total, "pages": (total + per_page - 1) // per_page}}


def apply_date_filters(query, model, field_name):
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    column = getattr(model, field_name)
    if date_from:
        query = query.filter(column >= date.fromisoformat(date_from))
    if date_to:
        query = query.filter(column <= date.fromisoformat(date_to))
    return query


@bp.route("/products")
@login_required
def products():
    return jsonify(product_payload()["data"])


def product_payload():
    q = request.args.get("q", "")
    query = Product.query.filter_by(is_active=True)
    if q:
        query = query.filter((Product.name.like(f"%{q}%")) | (Product.sku.like(f"%{q}%")) | (Product.barcode.like(f"%{q}%")))
    warehouse_id = request.args.get("warehouse_id")
    if warehouse_id:
        query = query.filter(Product.warehouse_id == warehouse_id)
    return paginated_response(query, product_json, {"sku": Product.sku, "name": Product.name, "stock": Product.current_stock})


@bp.route("/products/<int:id>")
@login_required
def product_detail(id):
    return jsonify(product_json(Product.query.get_or_404(id)))


@bp.route("/customers")
@login_required
def customers():
    return jsonify(customer_payload()["data"])


def customer_payload():
    q = request.args.get("q", "")
    query = Customer.query
    if q:
        query = query.filter((Customer.name.like(f"%{q}%")) | (Customer.customer_code.like(f"%{q}%")) | (Customer.phone.like(f"%{q}%")))
    return paginated_response(query, lambda c: {"id": c.id, "code": c.customer_code, "name": c.name, "outstanding": c.outstanding}, {"code": Customer.customer_code, "name": Customer.name})


@bp.route("/suppliers")
@login_required
def suppliers():
    return jsonify(supplier_payload()["data"])


def supplier_payload():
    q = request.args.get("q", "")
    query = Supplier.query
    if q:
        query = query.filter((Supplier.name.like(f"%{q}%")) | (Supplier.supplier_code.like(f"%{q}%")) | (Supplier.phone.like(f"%{q}%")))
    return paginated_response(query, lambda s: {"id": s.id, "code": s.supplier_code, "name": s.name, "outstanding": s.outstanding}, {"code": Supplier.supplier_code, "name": Supplier.name})


@bp.route("/sales")
@login_required
def sales():
    query = apply_date_filters(Sale.query, Sale, "invoice_date")
    if request.args.get("customer_id"):
        query = query.filter(Sale.customer_id == request.args["customer_id"])
    if request.args.get("warehouse_id"):
        query = query.filter(Sale.warehouse_id == request.args["warehouse_id"])
    if request.args.get("status"):
        query = query.filter(Sale.payment_status == request.args["status"])
    return jsonify(paginated_response(query, lambda s: {"id": s.id, "invoice_no": s.invoice_no, "date": s.invoice_date.isoformat(), "customer": s.customer.name, "status": s.display_status, "total": float(s.grand_total)}, {"date": Sale.invoice_date, "total": Sale.grand_total, "invoice_no": Sale.invoice_no}))


@bp.route("/sales/<int:id>")
@login_required
def sale_detail(id):
    s = Sale.query.get_or_404(id)
    return jsonify({"id": s.id, "invoice_no": s.invoice_no, "customer": s.customer.name, "total": float(s.grand_total), "items": [{"product": i.product.name, "qty": float(i.quantity), "total": float(i.line_total)} for i in s.items]})


@bp.route("/invoices")
@login_required
def invoices():
    query = apply_date_filters(Sale.query, Sale, "invoice_date")
    if request.args.get("customer_id"):
        query = query.filter(Sale.customer_id == request.args["customer_id"])
    if request.args.get("status"):
        query = query.filter(Sale.status == request.args["status"])
    return jsonify(paginated_response(query, lambda s: {"id": s.id, "invoice_no": s.invoice_no, "date": s.invoice_date.isoformat(), "due_date": s.due_date.isoformat() if s.due_date else None, "customer": s.customer.name, "status": s.display_status, "total": float(s.grand_total or 0), "paid": float(s.paid_amount or 0), "balance": float(s.balance_amount or 0)}, {"date": Sale.invoice_date, "total": Sale.grand_total, "invoice_no": Sale.invoice_no}))


@bp.route("/invoices/<int:id>")
@login_required
def invoice_detail(id):
    s = Sale.query.get_or_404(id)
    return jsonify({"id": s.id, "invoice_no": s.invoice_no, "status": s.display_status, "customer": s.customer.name, "subtotal": float(s.subtotal or 0), "discount_total": float(s.discount_total or 0), "tax_total": float(s.tax_total or 0), "total": float(s.grand_total or 0), "paid": float(s.paid_amount or 0), "balance": float(s.balance_amount or 0), "items": [{"product": i.product.name, "qty": float(i.quantity), "rate": float(i.rate), "tax_rate": float(i.tax_rate or 0), "total": float(i.line_total)} for i in s.items]})


@bp.route("/purchases")
@login_required
def purchases():
    query = apply_date_filters(Purchase.query, Purchase, "purchase_date")
    if request.args.get("supplier_id"):
        query = query.filter(Purchase.supplier_id == request.args["supplier_id"])
    if request.args.get("warehouse_id"):
        query = query.filter(Purchase.warehouse_id == request.args["warehouse_id"])
    if request.args.get("status"):
        query = query.filter(Purchase.payment_status == request.args["status"])
    return jsonify(paginated_response(query, lambda p: {"id": p.id, "purchase_no": p.purchase_no, "date": p.purchase_date.isoformat(), "supplier": p.supplier.name, "status": p.payment_status, "total": float(p.grand_total)}, {"date": Purchase.purchase_date, "total": Purchase.grand_total, "purchase_no": Purchase.purchase_no}))


@bp.route("/reports/sales")
@login_required
def report_sales():
    return sales()


@bp.route("/reports/stock")
@login_required
def report_stock():
    return products()


@bp.route("/reports/profit-loss")
@login_required
def report_profit_loss():
    return jsonify(profit_loss_payload())


def profit_loss_payload():
    sales_total = sum(float(s.grand_total or 0) for s in Sale.query.all())
    purchases_total = sum(float(p.grand_total or 0) for p in Purchase.query.all())
    return {"sales": sales_total, "purchases": purchases_total, "profit": sales_total - purchases_total}


@bp.route("/v1/products")
@csrf.exempt
@api_auth_required
def v1_products():
    return jsonify(product_payload())


@bp.route("/v1/products", methods=["POST"])
@csrf.exempt
@api_auth_required
def v1_product_create():
    data = request.get_json(silent=True) or {}
    if not data.get("sku") or not data.get("name"):
        return api_error("sku and name are required", 422, "validation_error")
    if Product.query.filter_by(sku=data["sku"]).first():
        return api_error("SKU already exists", 409, "duplicate_sku")
    product = Product(sku=data["sku"], name=data["name"], barcode=data.get("barcode"), sales_price=data.get("sales_price") or 0, purchase_price=data.get("purchase_price") or 0, current_stock=data.get("current_stock") or 0, min_stock=data.get("min_stock") or 0, reorder_level=data.get("reorder_level") or 0, is_active=True)
    db.session.add(product); db.session.commit()
    return jsonify({"data": product_json(product)}), 201


@bp.route("/v1/products/<int:id>", methods=["PUT"])
@csrf.exempt
@api_auth_required
def v1_product_update(id):
    product = Product.query.get_or_404(id)
    data = request.get_json(silent=True) or {}
    for field in ["barcode", "name", "sales_price", "purchase_price", "min_stock", "reorder_level", "rack_bin"]:
        if field in data:
            setattr(product, field, data[field])
    db.session.commit()
    return jsonify({"data": product_json(product)})


@bp.route("/v1/customers")
@csrf.exempt
@api_auth_required
def v1_customers():
    return jsonify(customer_payload())


@bp.route("/v1/suppliers")
@csrf.exempt
@api_auth_required
def v1_suppliers():
    return jsonify(supplier_payload())


@bp.route("/v1/reports/profit-loss")
@csrf.exempt
@api_auth_required
def v1_profit_loss():
    return jsonify(profit_loss_payload())


@bp.route("/openapi")
@login_required
def openapi_docs():
    return render_template("api/openapi.html", title="API Documentation", spec=openapi_spec())


@bp.route("/openapi.json")
@login_required
def openapi_json():
    return jsonify(openapi_spec())


def openapi_spec():
    return {
        "openapi": "3.0.0",
        "info": {"title": "Vyapara ERP API", "version": "1.0.0"},
        "security": [{"bearerAuth": []}],
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        "paths": {
            "/api/v1/products": {"get": {"summary": "List products"}, "post": {"summary": "Create product"}},
            "/api/v1/products/{id}": {"put": {"summary": "Update product"}},
            "/api/v1/customers": {"get": {"summary": "List customers"}},
            "/api/v1/suppliers": {"get": {"summary": "List suppliers"}},
            "/api/v1/reports/profit-loss": {"get": {"summary": "Profit and loss summary"}},
        },
    }
