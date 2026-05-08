from decimal import Decimal, ROUND_HALF_UP


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def qty(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def payment_status(total, paid):
    total, paid = money(total), money(paid)
    if paid <= 0:
        return "Unpaid"
    if paid >= total:
        return "Paid"
    return "Partial"

