from flask import Blueprint, render_template, request, url_for
from flask_login import login_required

from app.models import Customer, Product, Purchase, Sale, Supplier

bp = Blueprint("search", __name__, url_prefix="/search")


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        like = f"%{q}%"
        for product in Product.query.filter((Product.sku.ilike(like)) | (Product.name.ilike(like)) | (Product.barcode.ilike(like))).limit(20):
            results.append({"type": "Product", "label": f"{product.sku} - {product.name}", "detail": product.barcode or "", "url": url_for("products.edit", id=product.id)})
        for customer in Customer.query.filter((Customer.customer_code.ilike(like)) | (Customer.name.ilike(like)) | (Customer.phone.ilike(like))).limit(20):
            results.append({"type": "Customer", "label": f"{customer.customer_code} - {customer.name}", "detail": customer.phone or "", "url": url_for("parties.customer_edit", id=customer.id)})
        for supplier in Supplier.query.filter((Supplier.supplier_code.ilike(like)) | (Supplier.name.ilike(like)) | (Supplier.phone.ilike(like))).limit(20):
            results.append({"type": "Supplier", "label": f"{supplier.supplier_code} - {supplier.name}", "detail": supplier.phone or "", "url": url_for("parties.supplier_edit", id=supplier.id)})
        for sale in Sale.query.filter(Sale.invoice_no.ilike(like)).limit(20):
            results.append({"type": "Sale", "label": sale.invoice_no, "detail": sale.customer.name, "url": url_for("sales.print_sale", id=sale.id)})
        for purchase in Purchase.query.filter(Purchase.purchase_no.ilike(like)).limit(20):
            results.append({"type": "Purchase", "label": purchase.purchase_no, "detail": purchase.supplier.name, "url": url_for("purchases.print_purchase", id=purchase.id)})
    return render_template("search/index.html", title="Global Search", q=q, results=results)
