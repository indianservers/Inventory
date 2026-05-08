from collections import defaultdict


def hsn_summary(document):
    rows = defaultdict(lambda: {"taxable": 0.0, "tax": 0.0, "total": 0.0, "rate": 0.0})
    for item in document.items:
        hsn = item.product.hsn_code or "NA"
        gross = float(item.quantity or 0) * float(item.rate or 0)
        discount = float(getattr(item, "discount_amount", 0) or 0)
        taxable = gross - discount
        rows[hsn]["taxable"] += taxable
        rows[hsn]["tax"] += float(item.tax_amount or 0)
        rows[hsn]["total"] += float(item.line_total or 0)
        rows[hsn]["rate"] = float(item.tax_rate or 0)
    return [{"hsn": hsn, **values} for hsn, values in sorted(rows.items())]


def e_invoice_payload(sale, company=None):
    return {
        "version": "1.1",
        "document": {
            "type": "INV",
            "number": sale.invoice_no,
            "date": sale.invoice_date.isoformat(),
        },
        "seller": {
            "name": company.company_name if company else "",
            "gstin": company.tax_number if company else "",
            "address": company.address if company else "",
            "state": company.state if company else "",
        },
        "buyer": {
            "name": sale.customer.name,
            "gstin": sale.customer.gst_number or "",
            "address": sale.customer.billing_address or "",
            "state": sale.customer.state or "",
        },
        "items": [
            {
                "name": item.product.name,
                "hsn": item.product.hsn_code or "",
                "quantity": float(item.quantity or 0),
                "unit": item.product.unit.short_name if item.product.unit else "",
                "rate": float(item.rate or 0),
                "tax_rate": float(item.tax_rate or 0),
                "tax_amount": float(item.tax_amount or 0),
                "line_total": float(item.line_total or 0),
            }
            for item in sale.items
        ],
        "totals": {
            "subtotal": float(sale.subtotal or 0),
            "discount": float(sale.discount_total or 0),
            "tax": float(sale.tax_total or 0),
            "round_off": float(sale.round_off or 0),
            "grand_total": float(sale.grand_total or 0),
        },
    }
