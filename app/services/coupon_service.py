from datetime import date
from decimal import Decimal

from app.models import Coupon, CouponRedemption


def validate_coupon(code, customer_id, subtotal):
    code = (code or "").strip().upper()
    if not code:
        return None, Decimal("0"), None
    coupon = Coupon.query.filter_by(code=code, is_active=True).first()
    if not coupon:
        return None, Decimal("0"), "Coupon not found or inactive."
    today = date.today()
    if coupon.valid_from and coupon.valid_from > today:
        return None, Decimal("0"), "Coupon is not active yet."
    if coupon.valid_to and coupon.valid_to < today:
        return None, Decimal("0"), "Coupon has expired."
    subtotal = Decimal(str(subtotal or 0))
    if subtotal < Decimal(str(coupon.minimum_invoice_amount or 0)):
        return None, Decimal("0"), "Invoice amount is below coupon minimum."
    if coupon.max_usage and CouponRedemption.query.filter_by(coupon_id=coupon.id).count() >= coupon.max_usage:
        return None, Decimal("0"), "Coupon usage limit reached."
    if customer_id and coupon.per_customer_usage_limit and CouponRedemption.query.filter_by(coupon_id=coupon.id, customer_id=customer_id).count() >= coupon.per_customer_usage_limit:
        return None, Decimal("0"), "Customer coupon usage limit reached."
    if coupon.discount_type == "Fixed":
        discount = Decimal(str(coupon.discount_value or 0))
    else:
        discount = subtotal * Decimal(str(coupon.discount_value or 0)) / Decimal("100")
    return coupon, min(discount, subtotal), None
