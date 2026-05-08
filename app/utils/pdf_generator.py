from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def render_pdf(template=None, **context):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    y = height - 50
    title = context.get("title", "Vyapara ERP Document")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, title)
    y -= 30
    c.setFont("Helvetica", 10)
    document = context.get("sale") or context.get("purchase")
    if document:
        rows = [
            ("Number", getattr(document, "invoice_no", None) or getattr(document, "purchase_no", "")),
            ("Date", str(getattr(document, "invoice_date", None) or getattr(document, "purchase_date", ""))),
            ("Party", getattr(getattr(document, "customer", None) or getattr(document, "supplier", None), "name", "")),
            ("Grand Total", str(document.grand_total)),
        ]
        for label, value in rows:
            c.drawString(40, y, f"{label}: {value}")
            y -= 18
        y -= 12
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, "Item")
        c.drawString(280, y, "Qty")
        c.drawString(350, y, "Rate")
        c.drawString(430, y, "Total")
        c.setFont("Helvetica", 10)
        y -= 18
        for item in document.items:
            if y < 70:
                c.showPage()
                y = height - 50
            c.drawString(40, y, item.product.name[:35])
            c.drawRightString(320, y, str(item.quantity))
            c.drawRightString(390, y, str(item.rate))
            c.drawRightString(500, y, str(item.line_total))
            y -= 18
    c.showPage()
    c.save()
    output.seek(0)
    return output
