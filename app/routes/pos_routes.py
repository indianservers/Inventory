import json
from datetime import date, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import BadRequest

from app.extensions import db
from app.models import Batch, CashMovement, Category, CouponRedemption, Customer, HeldBill, PaymentReceived, POSSession, Product, ProductVariant, Register, Sale, SaleItem, SerialNumber, User, Warehouse
from app.services.audit_service import record_audit
from app.services.accounting_service import post_customer_receipt, post_sale
from app.services.coupon_service import validate_coupon
from app.services.invoice_service import calculate_document, line_totals
from app.services.loyalty_service import earn_points_for_sale
from app.services.numbering_service import next_number
from app.services.stock_service import apply_sale_item
from app.utils.helpers import money

bp = Blueprint("pos", __name__, url_prefix="/pos")


@bp.route("/")
@login_required
def index():
    active = current_session()
    if active:
        return redirect(url_for("pos.terminal"))
    return render_template("pos/open_session.html", title="Open POS Session", registers=Register.query.filter_by(status=True).order_by(Register.name).all())


@bp.route("/open-session", methods=["POST"])
@login_required
def open_session():
    register_id = request.form.get("register_id") or None
    register = Register.query.filter_by(id=register_id, status=True).first() if register_id else None
    pos_session = POSSession(session_no=next_number("pos_session"), opened_by=current_user.id, register_id=register.id if register else None, opening_cash=request.form.get("opening_cash") or 0, status="Open")
    db.session.add(pos_session)
    db.session.flush()
    record_audit("Open Session", "POS", pos_session.id, new_data={"opening_cash": str(pos_session.opening_cash), "register_id": register.id if register else None})
    db.session.commit()
    session["pos_session_id"] = pos_session.id
    flash("POS session opened.", "success")
    return redirect(url_for("pos.terminal"))


@bp.route("/terminal")
@login_required
def terminal():
    active = current_session()
    if not active:
        return redirect(url_for("pos.index"))
    walkin = Customer.query.order_by(Customer.id).first()
    warehouse = active.register.warehouse if active.register else Warehouse.query.order_by(Warehouse.id).first()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template("pos/terminal.html", title="POS Terminal", pos_session=active, products=products, categories=Category.query.order_by(Category.name).all(), customers=Customer.query.order_by(Customer.name).all(), warehouses=Warehouse.query.order_by(Warehouse.name).all(), walkin=walkin, warehouse=warehouse)


@bp.route("/products/search")
@login_required
def product_search():
    q = (request.args.get("q") or "").strip()
    warehouse_id = request.args.get("warehouse_id")
    query = Product.query.filter(Product.is_active.is_(True))
    if q:
        like = f"%{q}%"
        batch_ids = db.session.query(Batch.product_id).filter(Batch.batch_no.ilike(like))
        serial_ids = db.session.query(SerialNumber.product_id).filter(SerialNumber.serial_no.ilike(like))
        variant_ids = db.session.query(ProductVariant.product_id).filter(db.or_(ProductVariant.sku.ilike(like), ProductVariant.barcode.ilike(like)))
        query = query.filter(
            db.or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.barcode.ilike(like),
                Product.id.in_(batch_ids),
                Product.id.in_(serial_ids),
                Product.id.in_(variant_ids),
            )
        )
    products = query.order_by(Product.name).limit(30).all()
    return jsonify({"data": [product_payload(product, warehouse_id) for product in products]})


@bp.route("/sale", methods=["POST"])
@login_required
def sale():
    active = current_session()
    if not active:
        return jsonify({"error": "No open POS session"}), 400
    data = request.get_json(force=True)
    request_id = data.get("request_id")
    if request_id:
        seen = set(session.get("pos_sale_request_ids", []))
        if request_id in seen:
            return jsonify({"error": "Duplicate sale submission ignored"}), 409
    items = []
    for item in data.get("items", []):
        product = Product.query.get_or_404(int(item["product_id"]))
        if money(item.get("discount") or 0) > 50 and not current_user.has_permission("pos", "edit"):
            return jsonify({"error": f"Discount override not allowed for {product.name}"}), 403
        if money(item.get("rate") or 0) != money(product.sales_price) and not current_user.has_permission("pos", "edit"):
            return jsonify({"error": f"Price override not allowed for {product.name}"}), 403
        totals = line_totals(item["qty"], item["rate"], item.get("discount", 0), item.get("tax_rate", 0))
        items.append({"product_id": product.id, "quantity": item["qty"], "rate": item["rate"], "discount": item.get("discount", 0), "tax_rate": item.get("tax_rate", 0), "track_inventory": product.track_inventory, **totals})
    if not items:
        return jsonify({"error": "Cart is empty"}), 400
    totals = calculate_document(items, paid=0)
    discount_total = money(data.get("discount_total") or 0)
    coupon, coupon_discount, coupon_error = validate_coupon(data.get("coupon_code"), data.get("customer_id"), totals["subtotal"])
    if coupon_error:
        return jsonify({"error": coupon_error}), 400
    discount_total += money(coupon_discount)
    totals["discount_total"] = money(totals["discount_total"]) + discount_total
    totals["grand_total"] = money(totals["grand_total"]) - discount_total
    mode = data.get("payment_mode") or "Cash"
    is_credit = mode == "Credit"
    if is_credit and not data.get("customer_id"):
        return jsonify({"error": "Customer is required for credit sale"}), 400
    paid_total = 0 if is_credit else totals["grand_total"]
    totals["balance_amount"] = totals["grand_total"] if is_credit else 0
    totals["paid_amount"] = paid_total
    totals["payment_status"] = "Unpaid" if is_credit else "Paid"
    default_warehouse_id = active.register.warehouse_id if active.register else Warehouse.query.first().id
    sale = Sale(invoice_no=next_number("sales"), invoice_date=date.today(), customer_id=data.get("customer_id") or Customer.query.first().id, warehouse_id=data.get("warehouse_id") or default_warehouse_id, sale_type="Credit" if is_credit else "Cash", invoice_type="Retail Invoice", status="Issued" if is_credit else "Paid", notes="Delivery bill" if data.get("delivery_bill") else None, created_by=current_user.id, issued_at=datetime.utcnow(), **totals)
    try:
        db.session.add(sale); db.session.flush()
        for item in items:
            cost = apply_sale_item(item["product_id"], sale.warehouse_id, item["quantity"], sale.id, sale.invoice_no) if item.get("track_inventory") else 0
            db.session.add(SaleItem(sale_id=sale.id, product_id=item["product_id"], quantity=item["quantity"], rate=item["rate"], discount=item["discount"], discount_amount=item["discount_amount"], tax_rate=item["tax_rate"], tax_amount=item["tax_amount"], line_total=item["line_total"], cost_price=cost))
        if coupon and coupon_discount:
            db.session.add(CouponRedemption(coupon_id=coupon.id, sale_id=sale.id, customer_id=sale.customer_id, discount_amount=coupon_discount))
        post_sale(sale, current_user.id)
        if not is_credit:
            receipt = PaymentReceived(receipt_no=next_number("receipt"), receipt_date=date.today(), customer_id=sale.customer_id, amount=sale.grand_total, payment_mode=mode, reference_no=data.get("reference_no"), sale_id=sale.id, created_by=current_user.id)
            db.session.add(receipt); db.session.flush(); post_customer_receipt(receipt, current_user.id)
        cash = money(data.get("cash_tendered") or (sale.grand_total if mode == "Cash" else 0))
        card = money(data.get("card_amount") or (sale.grand_total if mode == "Card" else 0))
        upi = money(data.get("upi_amount") or (sale.grand_total if mode == "UPI" else 0))
        wallet = money(data.get("wallet_amount") or (sale.grand_total if mode == "Wallet" else 0))
        active.total_sales = money(active.total_sales) + money(sale.grand_total)
        active.total_cash = money(active.total_cash) + (money(sale.grand_total) if mode == "Cash" else cash)
        active.total_card = money(active.total_card) + card
        active.total_upi = money(active.total_upi) + upi
        active.total_wallet = money(active.total_wallet) + wallet
        active.total_credit = money(active.total_credit) + (money(sale.grand_total) if is_credit else 0)
        earn_points_for_sale(sale)
        record_audit("Sale Completed", "POS", sale.id, new_data={"invoice_no": sale.invoice_no, "total": str(sale.grand_total), "payment_mode": mode})
        if request_id:
            seen = list(set(session.get("pos_sale_request_ids", [])) | {request_id})[-20:]
            session["pos_sale_request_ids"] = seen
        db.session.commit()
    except BadRequest as exc:
        db.session.rollback()
        return jsonify({"error": exc.description}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    change_due = max(float(cash - money(sale.grand_total)), 0) if mode in ["Cash", "Split"] else 0
    return jsonify({"invoice_no": sale.invoice_no, "grand_total": float(sale.grand_total), "change_due": change_due, "sale_id": sale.id})


@bp.route("/hold", methods=["POST"])
@login_required
def hold_bill():
    active = current_session()
    if not active:
        return jsonify({"error": "No open POS session"}), 400
    data = request.get_json(force=True)
    held = HeldBill(
        hold_no=next_number("held_bill"),
        session_id=active.id,
        customer_id=data.get("customer_id") or None,
        warehouse_id=data.get("warehouse_id") or None,
        cart_json=json.dumps(data.get("items", [])),
        notes=data.get("notes"),
        created_by=current_user.id,
    )
    db.session.add(held)
    db.session.flush()
    record_audit("Hold Bill", "POS", held.id, new_data={"hold_no": held.hold_no, "items": len(data.get("items", []))})
    db.session.commit()
    return jsonify({"hold_no": held.hold_no, "id": held.id})


@bp.route("/held")
@login_required
def held_bills():
    return render_template("pos/held_bills.html", title="Held Bills", held_bills=HeldBill.query.filter_by(status="Held").order_by(HeldBill.id.desc()).all())


@bp.route("/held.json")
@login_required
def held_bills_json():
    active = current_session()
    query = HeldBill.query.filter_by(status="Held")
    if active:
        query = query.filter(HeldBill.session_id == active.id)
    rows = query.order_by(HeldBill.id.desc()).limit(25).all()
    payload = []
    for bill in rows:
        cart = json.loads(bill.cart_json or "[]")
        amount = sum(float(item.get("qty", item.get("quantity", 0)) or 0) * float(item.get("rate", 0) or 0) for item in cart)
        actor = User.query.get(bill.created_by) if bill.created_by else None
        payload.append({"id": bill.id, "hold_no": bill.hold_no, "notes": bill.notes, "customer": bill.customer.name if bill.customer else "Walk-in Customer", "item_count": len(cart), "amount": amount, "held_by": actor.name if actor else "", "created_at": bill.created_at.isoformat()})
    return jsonify({"data": payload})


@bp.route("/held/<int:id>/json")
@login_required
def held_bill_json(id):
    bill = HeldBill.query.get_or_404(id)
    bill.status = "Recalled"
    db.session.commit()
    return jsonify({"id": bill.id, "customer_id": bill.customer_id, "warehouse_id": bill.warehouse_id, "items": json.loads(bill.cart_json or "[]")})


@bp.route("/held/<int:id>/delete", methods=["POST"])
@login_required
def held_bill_delete(id):
    bill = HeldBill.query.get_or_404(id)
    active = current_session()
    if active and bill.session_id != active.id and not current_user.has_permission("pos", "delete"):
        return jsonify({"error": "This held bill belongs to another session"}), 403
    bill.status = "Cancelled"
    record_audit("Delete Held Bill", "POS", bill.id, old_data={"hold_no": bill.hold_no})
    db.session.commit()
    return jsonify({"status": "deleted"})


@bp.route("/cash-movement", methods=["POST"])
@login_required
def cash_movement():
    active = current_session()
    if not active:
        return redirect(url_for("pos.index"))
    amount = money(request.form.get("amount") or 0)
    movement_type = request.form.get("movement_type") or "Withdrawal"
    db.session.add(CashMovement(session_id=active.id, movement_type=movement_type, amount=amount, reason=request.form.get("reason"), created_by=current_user.id))
    if movement_type == "Withdrawal":
        active.cash_withdrawals = money(active.cash_withdrawals) + amount
    record_audit("Cash Movement", "POS", active.id, new_data={"type": movement_type, "amount": str(amount), "reason": request.form.get("reason")})
    db.session.commit()
    flash("Cash movement recorded.", "success")
    return redirect(url_for("pos.sessions"))


@bp.route("/close-session", methods=["POST"])
@login_required
def close_session():
    active = current_session()
    if not active:
        return redirect(url_for("pos.index"))
    if request.form.get("closing_cash") in {None, ""}:
        flash("Closing cash is required.", "danger")
        return redirect(url_for("pos.terminal"))
    active.closing_cash = request.form.get("closing_cash") or 0
    active.expected_closing_cash = money(active.opening_cash) + money(active.total_cash) - money(active.cash_withdrawals) - money(active.total_refunds)
    active.cash_difference = money(active.closing_cash) - money(active.expected_closing_cash)
    active.closed_at = datetime.utcnow()
    active.status = "Closed"
    session.pop("pos_session_id", None)
    record_audit("Close Session", "POS", active.id, new_data={"expected_cash": str(active.expected_closing_cash), "closing_cash": str(active.closing_cash), "difference": str(active.cash_difference)})
    db.session.commit()
    return render_template("pos/z_report.html", title=f"Z Report {active.session_no}", pos_session=active)


@bp.route("/sessions")
@login_required
def sessions():
    return render_template("pos/sessions.html", title="POS Sessions", sessions=POSSession.query.order_by(POSSession.id.desc()).all())


@bp.route("/receipt/<int:id>")
@login_required
def receipt(id):
    sale = Sale.query.get_or_404(id)
    return render_template("pos/receipt.html", title=f"Receipt {sale.invoice_no}", sale=sale)


def current_session():
    pos_id = session.get("pos_session_id")
    if pos_id:
        active = POSSession.query.filter_by(id=pos_id, status="Open").first()
        if active:
            return active
    active = POSSession.query.filter_by(opened_by=current_user.id, status="Open").order_by(POSSession.id.desc()).first()
    if active:
        session["pos_session_id"] = active.id
    return active


def product_payload(product, warehouse_id=None):
    batches = [batch for batch in product.batch_lots if (not warehouse_id or str(batch.warehouse_id) == str(warehouse_id)) and float(batch.quantity or 0) > 0]
    serials = [serial for serial in product.serial_numbers if (not warehouse_id or str(serial.warehouse_id) == str(warehouse_id)) and serial.status == "Available"]
    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "barcode": product.barcode,
        "category": product.category.name if product.category else "",
        "rate": float(product.sales_price or 0),
        "tax_rate": float(product.tax.rate if product.tax else 0),
        "stock": float(product.current_stock or 0),
        "track_inventory": bool(product.track_inventory),
        "batch_tracking": bool(product.batch_tracking),
        "serial_tracking": bool(product.serial_tracking),
        "expiry_tracking": bool(product.expiry_tracking),
        "decimal_allowed": bool(product.unit.decimal_allowed if product.unit else False),
        "low_stock": product.is_low_stock,
        "batches": [{"id": batch.id, "batch_no": batch.batch_no, "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else "", "quantity": float(batch.quantity or 0)} for batch in batches],
        "serials": [{"id": serial.id, "serial_no": serial.serial_no} for serial in serials[:50]],
    }
