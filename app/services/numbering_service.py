from datetime import date
from app.extensions import db
from app.models import CompanySetting


MODEL_FIELD = {
    "sales": ("Sale", "invoice_no", "invoice_prefix", "INV"),
    "purchases": ("Purchase", "purchase_no", "purchase_prefix", "PUR"),
    "quotations": ("Quotation", "quotation_no", "quotation_prefix", "QUO"),
    "proforma": ("ProformaInvoice", "proforma_no", None, "PRO"),
    "challan": ("DeliveryChallan", "challan_no", None, "DC"),
    "receipt": ("PaymentReceived", "receipt_no", "receipt_prefix", "REC"),
    "payment": ("PaymentMade", "voucher_no", "payment_prefix", "PAY"),
    "sales_return": ("SalesReturn", "return_no", "sales_return_prefix", "SR"),
    "purchase_return": ("PurchaseReturn", "return_no", "purchase_return_prefix", "PR"),
    "purchase_order": ("PurchaseOrder", "po_no", None, "PO"),
    "grn": ("GoodsReceiptNote", "grn_no", None, "GRN"),
    "pos_session": ("POSSession", "session_no", None, "POS"),
    "credit_note": ("CreditNote", "cn_no", None, "CN"),
    "debit_note": ("DebitNote", "dn_no", None, "DN"),
    "manufacturing_order": ("ManufacturingOrder", "mo_no", None, "MO"),
    "journal": ("JournalEntry", "entry_no", None, "JV"),
    "stock_adjustment": ("StockAdjustment", "adjustment_no", None, "SA"),
    "stock_transfer": ("StockTransfer", "transfer_no", None, "ST"),
    "expense": ("Expense", "expense_no", None, "EXP"),
}


def next_number(kind):
    import app.models as models

    model_name, field_name, setting_attr, default_prefix = MODEL_FIELD[kind]
    model = getattr(models, model_name)
    setting = CompanySetting.query.first()
    prefix = getattr(setting, setting_attr) if setting and setting_attr else default_prefix
    year = date.today().year
    stem = f"{prefix}-{year}-"
    last = (
        db.session.query(getattr(model, field_name))
        .filter(getattr(model, field_name).like(f"{stem}%"))
        .order_by(getattr(model, field_name).desc())
        .first()
    )
    sequence = 1
    if last:
        try:
            sequence = int(last[0].split("-")[-1]) + 1
        except (ValueError, IndexError):
            sequence = 1
    return f"{stem}{sequence:05d}"
