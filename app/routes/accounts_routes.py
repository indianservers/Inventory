import csv
from datetime import date, datetime, timedelta
from io import StringIO

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import BankAccount, BankStatementLine, ChartOfAccounts, Customer, Expense, ExpenseCategory, ITCEntry, JournalEntry, PaymentAllocation, PaymentMade, PaymentReceived, Purchase, Sale, Supplier, SupplierLedger, TCSEntry, TDSEntry, TDSSection, VendorPaymentAllocation
from app.services.accounting_service import create_journal, post_customer_receipt, post_supplier_payment
from app.services.audit_service import record_audit
from app.services.numbering_service import next_number
from app.utils.helpers import money
from app.utils.excel_export import export_to_excel

bp = Blueprint("accounts", __name__, url_prefix="/accounts")
XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@bp.route("/chart")
@login_required
def chart():
    return render_template("accounts/chart.html", title="Chart of Accounts", accounts=ChartOfAccounts.query.order_by(ChartOfAccounts.account_code).all())


@bp.route("/journals")
@login_required
def journals():
    return render_template("accounts/journals.html", title="Journal Entries", journals=JournalEntry.query.order_by(JournalEntry.id.desc()).all())


@bp.route("/itc")
@login_required
def itc_register():
    query = ITCEntry.query
    if request.args.get("supplier_id"):
        query = query.filter(ITCEntry.supplier_id == request.args["supplier_id"])
    if request.args.get("status"):
        query = query.filter(ITCEntry.itc_status == request.args["status"])
    if request.args.get("period"):
        query = query.filter(ITCEntry.claim_period == request.args["period"])
    rows = query.order_by(ITCEntry.invoice_date.desc(), ITCEntry.id.desc()).all()
    if request.args.get("export") == "xlsx":
        output = export_to_excel(["Invoice", "Date", "Supplier", "Taxable", "CGST", "SGST", "IGST", "VAT", "Eligible", "Blocked", "Status", "Period"], [[r.invoice_no, r.invoice_date, r.supplier.name if r.supplier else "", r.taxable_value, r.input_tax_cgst, r.input_tax_sgst, r.input_tax_igst, r.input_tax_vat, r.eligible_itc_amount, r.blocked_itc_amount, r.itc_status, r.claim_period] for r in rows], "ITC Register")
        return send_file(output, mimetype=XLSX_MIMETYPE, as_attachment=True, download_name="itc-register.xlsx")
    return render_template("accounts/itc.html", title="ITC Register", rows=rows, suppliers=Supplier.query.order_by(Supplier.name).all())


@bp.route("/itc/<int:id>/update", methods=["POST"])
@login_required
def itc_update(id):
    entry = ITCEntry.query.get_or_404(id)
    entry.itc_status = request.form.get("itc_status") or entry.itc_status
    entry.blocked_itc_amount = request.form.get("blocked_itc_amount") or entry.blocked_itc_amount
    entry.eligible_itc_amount = max(float(entry.input_tax_cgst or 0) + float(entry.input_tax_sgst or 0) + float(entry.input_tax_igst or 0) + float(entry.input_tax_vat or 0) - float(entry.blocked_itc_amount or 0), 0)
    entry.ineligible_reason = request.form.get("ineligible_reason")
    entry.reversal_reason = request.form.get("reversal_reason")
    entry.remarks = request.form.get("remarks")
    record_audit("Update", "ITCEntry", entry.id, new_data={"status": entry.itc_status})
    db.session.commit()
    flash("ITC entry updated.", "success")
    return redirect(url_for("accounts.itc_register"))


@bp.route("/journals/create", methods=["GET", "POST"])
@login_required
def journal_create():
    accounts = ChartOfAccounts.query.filter_by(is_active=True).all()
    if request.method == "POST":
        lines = []
        for acc_id, debit, credit in zip(request.form.getlist("account_id[]"), request.form.getlist("debit[]"), request.form.getlist("credit[]")):
            if acc_id:
                lines.append({"account": ChartOfAccounts.query.get(acc_id), "debit": debit or 0, "credit": credit or 0})
        create_journal(date.fromisoformat(request.form["entry_date"]), "Manual", None, request.form.get("narration"), lines, current_user.id)
        db.session.commit(); flash("Journal saved.", "success")
        return redirect(url_for("accounts.journals"))
    return render_template("accounts/journal_form.html", title="Create Journal", accounts=accounts, today=date.today())


@bp.route("/receipts", methods=["GET", "POST"])
@login_required
def receipts():
    if request.method == "POST":
        amount = money(request.form["amount"])
        receipt = PaymentReceived(receipt_no=request.form.get("receipt_no") or next_number("receipt"), receipt_date=date.fromisoformat(request.form["receipt_date"]), customer_id=request.form["customer_id"], amount=amount, unallocated_amount=amount, payment_mode=request.form.get("payment_mode"), reference_no=request.form.get("reference_no"), notes=request.form.get("notes"), created_by=current_user.id)
        db.session.add(receipt); db.session.flush(); post_customer_receipt(receipt, current_user.id)
        if request.form.get("sale_id"):
            allocate_receipt_to_sale(receipt, Sale.query.get(request.form["sale_id"]), min(amount, receipt.unallocated_amount))
        record_audit("Payment Update", "PaymentReceived", receipt.id, new_data={"receipt_no": receipt.receipt_no, "amount": str(receipt.amount)}); db.session.commit(); flash("Receipt saved.", "success")
        return redirect(url_for("accounts.receipts"))
    return render_template("accounts/receipts.html", title="Receipts", items=PaymentReceived.query.order_by(PaymentReceived.id.desc()).all(), customers=Customer.query.all(), invoices=Sale.query.filter(Sale.balance_amount > 0, Sale.status != "Cancelled").order_by(Sale.invoice_date.desc()).all(), receipt_no=next_number("receipt"), today=date.today())


def allocate_receipt_to_sale(receipt, sale, amount):
    if not sale or amount <= 0:
        return
    amount = min(money(amount), money(receipt.unallocated_amount), money(sale.balance_amount))
    if amount <= 0:
        return
    db.session.add(PaymentAllocation(payment_id=receipt.id, sale_id=sale.id, amount=amount))
    receipt.sale_id = receipt.sale_id or sale.id
    receipt.unallocated_amount = money(receipt.unallocated_amount) - amount
    sale.paid_amount = money(sale.paid_amount) + amount
    sale.update_payment_status()


@bp.route("/receipts/<int:id>/allocate", methods=["POST"])
@login_required
def receipt_allocate(id):
    receipt = PaymentReceived.query.get_or_404(id)
    try:
        allocate_receipt_to_sale(receipt, Sale.query.get_or_404(request.form["sale_id"]), request.form.get("amount") or receipt.unallocated_amount)
        record_audit("Payment Update", "PaymentReceived", receipt.id, new_data={"allocation": str(request.form.get("amount"))})
        db.session.commit()
        flash("Receipt allocated.", "success")
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
    return redirect(url_for("accounts.receipts"))


@bp.route("/receipts/<int:id>/reverse", methods=["POST"])
@login_required
def receipt_reverse(id):
    receipt = PaymentReceived.query.get_or_404(id)
    if receipt.status == "Reversed":
        flash("Receipt is already reversed.", "warning")
        return redirect(url_for("accounts.receipts"))
    try:
        for allocation in receipt.allocations:
            sale = allocation.sale
            sale.paid_amount = max(0, money(sale.paid_amount) - money(allocation.amount))
            sale.update_payment_status()
        customer = Customer.query.get(receipt.customer_id)
        customer.current_balance = money(customer.current_balance) + money(receipt.amount)
        receipt.status = "Reversed"
        receipt.reversed_at = datetime.utcnow()
        receipt.reversal_reason = request.form.get("reason")
        record_audit("Payment Update", "PaymentReceived", receipt.id, new_data={"status": "Reversed", "reason": receipt.reversal_reason})
        db.session.commit()
        flash("Receipt reversed. Review accounting journal reversal if required.", "success")
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
    return redirect(url_for("accounts.receipts"))


@bp.route("/payments", methods=["GET", "POST"])
@login_required
def payments():
    if request.method == "POST":
        amount = money(request.form["amount"])
        payment = PaymentMade(voucher_no=request.form.get("voucher_no") or next_number("payment"), voucher_date=date.fromisoformat(request.form["voucher_date"]), payee_type=request.form.get("payee_type") or "Supplier", supplier_id=request.form.get("supplier_id") or None, amount=amount, unallocated_amount=amount, payment_mode=request.form.get("payment_mode"), reference_no=request.form.get("reference_no"), notes=request.form.get("notes"), created_by=current_user.id)
        db.session.add(payment); db.session.flush(); post_supplier_payment(payment, current_user.id)
        if request.form.get("purchase_id"):
            allocate_payment_to_purchase(payment, Purchase.query.get(request.form["purchase_id"]), min(amount, payment.unallocated_amount))
        record_audit("Payment Update", "PaymentMade", payment.id, new_data={"voucher_no": payment.voucher_no, "amount": str(payment.amount)}); db.session.commit(); flash("Payment saved.", "success")
        return redirect(url_for("accounts.payments"))
    return render_template("accounts/payments.html", title="Payments", items=PaymentMade.query.order_by(PaymentMade.id.desc()).all(), suppliers=Supplier.query.all(), purchases=Purchase.query.filter(Purchase.balance_amount > 0).order_by(Purchase.purchase_date.desc()).all(), voucher_no=next_number("payment"), today=date.today())


def allocate_payment_to_purchase(payment, purchase, amount):
    if not purchase or amount <= 0:
        return
    amount = min(money(amount), money(payment.unallocated_amount), money(purchase.balance_amount))
    if amount <= 0:
        return
    db.session.add(VendorPaymentAllocation(payment_id=payment.id, purchase_id=purchase.id, amount=amount))
    payment.purchase_id = payment.purchase_id or purchase.id
    payment.unallocated_amount = money(payment.unallocated_amount) - amount
    purchase.paid_amount = money(purchase.paid_amount) + amount
    purchase.update_payment_status()


@bp.route("/payments/<int:id>/allocate", methods=["POST"])
@login_required
def payment_allocate(id):
    payment = PaymentMade.query.get_or_404(id)
    try:
        allocate_payment_to_purchase(payment, Purchase.query.get_or_404(request.form["purchase_id"]), request.form.get("amount") or payment.unallocated_amount)
        record_audit("Payment Update", "PaymentMade", payment.id, new_data={"allocation": str(request.form.get("amount"))})
        db.session.commit()
        flash("Payment allocated.", "success")
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
    return redirect(url_for("accounts.payments"))


@bp.route("/payments/<int:id>/reverse", methods=["POST"])
@login_required
def payment_reverse(id):
    payment = PaymentMade.query.get_or_404(id)
    if payment.status == "Reversed":
        flash("Payment is already reversed.", "warning")
        return redirect(url_for("accounts.payments"))
    try:
        for allocation in payment.allocations:
            purchase = allocation.purchase
            purchase.paid_amount = max(0, money(purchase.paid_amount) - money(allocation.amount))
            purchase.update_payment_status()
        supplier = Supplier.query.get(payment.supplier_id)
        if supplier:
            supplier.current_balance = money(supplier.current_balance) + money(payment.amount)
            db.session.add(SupplierLedger(date=date.today(), supplier_id=supplier.id, reference_type="PaymentReversal", reference_id=payment.id, reference_no=payment.voucher_no, debit=0, credit=payment.amount, balance=supplier.outstanding + float(payment.amount), narration=request.form.get("reason") or "Vendor payment reversed"))
        payment.status = "Reversed"
        payment.reversed_at = datetime.utcnow()
        payment.reversal_reason = request.form.get("reason")
        record_audit("Payment Update", "PaymentMade", payment.id, new_data={"status": "Reversed", "reason": payment.reversal_reason})
        db.session.commit()
        flash("Payment reversed.", "success")
    except Exception as exc:
        db.session.rollback(); flash(str(exc), "danger")
    return redirect(url_for("accounts.payments"))


@bp.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    if request.method == "POST":
        expense = Expense(expense_no=request.form.get("expense_no") or next_number("expense"), expense_date=date.fromisoformat(request.form["expense_date"]), category_id=request.form.get("category_id") or None, amount=request.form["amount"], tax_amount=request.form.get("tax_amount") or 0, vendor_name=request.form.get("vendor_name"), notes=request.form.get("notes"), created_by=current_user.id)
        db.session.add(expense); db.session.commit(); flash("Expense saved.", "success")
        return redirect(url_for("accounts.expenses"))
    return render_template("accounts/expenses.html", title="Expenses", items=Expense.query.order_by(Expense.id.desc()).all(), categories=ExpenseCategory.query.all(), expense_no=next_number("expense"), today=date.today())

@bp.route("/cash-book")
@login_required
def cash_book():
    return render_template("shared/placeholder.html", title="Cash Book", message="Cash book report is available through accounts reports.")

@bp.route("/bank-book")
@login_required
def bank_book():
    return render_template("shared/placeholder.html", title="Bank Book", message="Bank book report is available through accounts reports.")


@bp.route("/banks/<int:id>/reconcile")
@login_required
def reconcile(id):
    bank = BankAccount.query.get_or_404(id)
    lines = BankStatementLine.query.filter_by(bank_account_id=id).order_by(BankStatementLine.txn_date.desc()).all()
    payments = PaymentMade.query.filter_by(bank_account_id=id).all()
    receipts = PaymentReceived.query.filter_by(bank_account_id=id).all()
    return render_template("accounts/reconcile.html", title=f"Reconcile {bank.account_name}", bank=bank, lines=lines, payments=payments, receipts=receipts)


@bp.route("/banks/<int:id>/import", methods=["POST"])
@login_required
def import_bank_statement(id):
    bank = BankAccount.query.get_or_404(id)
    file = request.files.get("statement")
    if not file:
        flash("Upload a CSV file.", "warning"); return redirect(url_for("accounts.reconcile", id=id))
    rows = list(csv.DictReader(StringIO(file.read().decode("utf-8-sig"))))
    if request.form.get("preview"):
        return render_template("accounts/reconcile.html", title=f"Import Preview {bank.account_name}", bank=bank, lines=BankStatementLine.query.filter_by(bank_account_id=id).all(), preview=rows, payments=[], receipts=[])
    imported = 0
    for row in rows:
        norm = {k.lower().strip(): v for k, v in row.items()}
        txn_date = date.fromisoformat(norm.get("date") or norm.get("txn_date") or norm.get("transaction date"))
        description = norm.get("description") or norm.get("narration") or ""
        debit = norm.get("debit") or 0
        credit = norm.get("credit") or 0
        exists = BankStatementLine.query.filter_by(bank_account_id=id, txn_date=txn_date, description=description, debit=debit or 0, credit=credit or 0).first()
        if exists:
            continue
        db.session.add(BankStatementLine(bank_account_id=id, txn_date=txn_date, description=description, debit=debit or 0, credit=credit or 0, balance=norm.get("balance") or 0, reference_no=norm.get("reference_no") or norm.get("ref") or ""))
        imported += 1
    db.session.commit(); flash(f"Imported {imported} bank lines.", "success")
    return redirect(url_for("accounts.reconcile", id=id))


@bp.route("/banks/<int:id>/match/<int:line_id>", methods=["POST"])
@login_required
def match_bank_line(id, line_id):
    line = BankStatementLine.query.get_or_404(line_id)
    line.matched_to_type = request.form["matched_to_type"]
    line.matched_to_id = request.form["matched_to_id"]
    line.is_reconciled = True
    db.session.commit()
    return redirect(url_for("accounts.reconcile", id=id))


@bp.route("/banks/<int:id>/auto-match", methods=["POST"])
@login_required
def auto_match_bank(id):
    lines = BankStatementLine.query.filter_by(bank_account_id=id, is_reconciled=False).all()
    matched = 0
    for line in lines:
        amount = float(line.credit or 0) or float(line.debit or 0)
        start, end = line.txn_date - timedelta(days=2), line.txn_date + timedelta(days=2)
        receipt = PaymentReceived.query.filter(PaymentReceived.receipt_date.between(start, end), PaymentReceived.amount == amount).first()
        payment = PaymentMade.query.filter(PaymentMade.voucher_date.between(start, end), PaymentMade.amount == amount).first()
        obj = receipt or payment
        if obj:
            line.matched_to_type = "Receipt" if receipt else "Payment"
            line.matched_to_id = obj.id
            line.is_reconciled = True
            matched += 1
    db.session.commit(); flash(f"Auto-matched {matched} lines.", "success")
    return redirect(url_for("accounts.reconcile", id=id))


@bp.route("/banks/<int:id>/create-entry/<int:line_id>", methods=["POST"])
@login_required
def create_entry_from_bank(id, line_id):
    line = BankStatementLine.query.get_or_404(line_id)
    amount = float(line.debit or line.credit or 0)
    expense = Expense(expense_no=next_number("expense"), expense_date=line.txn_date, bank_account_id=id, amount=amount, vendor_name=line.description[:150], notes="Created from bank reconciliation", created_by=current_user.id)
    db.session.add(expense)
    line.matched_to_type = "Expense"
    line.matched_to_id = expense.id
    line.is_reconciled = True
    db.session.commit(); flash("Entry created from bank line.", "success")
    return redirect(url_for("accounts.reconcile", id=id))


@bp.route("/tds/")
@login_required
def tds_ledger():
    entries = TDSEntry.query.order_by(TDSEntry.entry_date.desc(), TDSEntry.id.desc()).all()
    return render_template("accounts/tds.html", title="TDS Ledger", entries=entries)


@bp.route("/tds/create", methods=["GET", "POST"])
@login_required
def tds_create():
    if request.method == "POST":
        section = TDSSection.query.get(request.form["section_id"])
        base = float(request.form.get("base_amount") or 0)
        rate = float(request.form.get("tds_rate") or section.default_rate or 0)
        entry = TDSEntry(
            entry_date=date.fromisoformat(request.form["entry_date"]),
            party_type=request.form["party_type"],
            party_id=request.form["party_id"],
            reference_type=request.form.get("reference_type"),
            reference_id=request.form.get("reference_id") or None,
            reference_no=request.form.get("reference_no"),
            section_id=section.id,
            base_amount=base,
            tds_rate=rate,
            tds_amount=round(base * rate / 100, 2),
            status=request.form.get("status") or "Pending",
            created_by=current_user.id,
        )
        db.session.add(entry)
        db.session.commit()
        flash("TDS entry saved.", "success")
        return redirect(url_for("accounts.tds_ledger"))
    return render_template("accounts/tds_form.html", title="Create TDS Entry", sections=TDSSection.query.filter_by(is_active=True).all(), suppliers=Supplier.query.order_by(Supplier.name).all(), customers=Customer.query.order_by(Customer.name).all(), today=date.today())


@bp.route("/tds/challan")
@login_required
def tds_challan():
    entries = TDSEntry.query.order_by(TDSEntry.entry_date.desc()).all()
    total = sum(float(e.tds_amount or 0) for e in entries)
    return render_template("accounts/tds_challan.html", title="Form 26Q / TDS Challan", entries=entries, total=total)


@bp.route("/tcs/")
@login_required
def tcs_ledger():
    entries = TCSEntry.query.order_by(TCSEntry.entry_date.desc(), TCSEntry.id.desc()).all()
    return render_template("accounts/tcs.html", title="TCS Ledger", entries=entries)
