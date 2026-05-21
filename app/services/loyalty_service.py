from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import CustomerLoyaltyAccount, LoyaltySetting, LoyaltyTransaction


def active_loyalty_setting():
    return LoyaltySetting.query.first()


def get_account(customer_id):
    account = CustomerLoyaltyAccount.query.filter_by(customer_id=customer_id).first()
    if not account:
        account = CustomerLoyaltyAccount(customer_id=customer_id, points_balance=0, lifetime_points=0)
        db.session.add(account)
        db.session.flush()
    return account


def earn_points_for_sale(sale):
    setting = active_loyalty_setting()
    if not setting or not setting.is_enabled or not sale.customer_id:
        return None
    amount_unit = Decimal(str(setting.earn_points_per_amount or 100))
    points_unit = Decimal(str(setting.points_earned or 1))
    if amount_unit <= 0:
        return None
    points = (Decimal(str(sale.grand_total or 0)) / amount_unit) * points_unit
    points = points.quantize(Decimal("0.01"))
    if points <= 0:
        return None
    account = get_account(sale.customer_id)
    account.points_balance = Decimal(str(account.points_balance or 0)) + points
    account.lifetime_points = Decimal(str(account.lifetime_points or 0)) + points
    txn = LoyaltyTransaction(customer_id=sale.customer_id, sale_id=sale.id, transaction_type="Earn", points=points, expiry_date=date.today() + timedelta(days=setting.points_expiry_days or 365), notes=f"Earned on {sale.invoice_no}")
    db.session.add(txn)
    return txn
