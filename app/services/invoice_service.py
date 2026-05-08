from app.utils.helpers import money, payment_status, qty


def line_totals(quantity, rate, discount_percent=0, tax_rate=0):
    quantity, rate = qty(quantity), money(rate)
    gross = money(quantity * rate)
    discount_amount = money(gross * money(discount_percent) / 100)
    taxable = gross - discount_amount
    tax_amount = money(taxable * money(tax_rate) / 100)
    return {
        "gross": gross,
        "discount_amount": discount_amount,
        "tax_amount": tax_amount,
        "line_total": money(taxable + tax_amount),
    }


def calculate_document(items, shipping=0, other=0, round_off=0, paid=0):
    subtotal = sum(money(item["gross"]) for item in items)
    discount_total = sum(money(item["discount_amount"]) for item in items)
    tax_total = sum(money(item["tax_amount"]) for item in items)
    grand_total = money(subtotal - discount_total + tax_total + money(shipping) + money(other) + money(round_off))
    return {
        "subtotal": subtotal,
        "discount_total": discount_total,
        "tax_total": tax_total,
        "grand_total": grand_total,
        "paid_amount": money(paid),
        "balance_amount": money(grand_total - money(paid)),
        "payment_status": payment_status(grand_total, paid),
    }

