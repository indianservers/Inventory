import csv
from datetime import date, timedelta
from io import StringIO

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import BankAccount, BankStatementLine, ChartOfAccounts, Customer, Expense, ExpenseCategory, JournalEntry, PaymentMade, PaymentReceived, Supplier, TCSEntry, TDSEntry, TDSSection
from app.services.accounting_service import create_journal, post_customer_receipt, post_supplier_payment
from app.services.numbering_service import next_number

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("/chart")
@login_required
def chart():
    return render_template("accounts/chart.html", title="Chart of Accounts", accounts=ChartOfAccounts.query.order_by(ChartOfAccounts.account_code).all())


@bp.route("/journals")
@login_required
def journals():
    return render_template("accounts/journals.html", title="Journal Entries", journals=JournalEntry.query.order_by(JournalEntry.id.desc()).all())


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
        receipt = PaymentReceived(receipt_no=request.form.get("receipt_no") or next_number("receipt"), receipt_date=date.fromisoformat(request.form["receipt_date"]), customer_id=request.form["customer_id"], amount=request.form["amount"], payment_mode=request.form.get("payment_mode"), reference_no=request.form.get("reference_no"), notes=request.form.get("notes"), created_by=current_user.id)
        db.session.add(receipt); db.session.flush(); post_customer_receipt(receipt, current_user.id); db.session.commit(); flash("Receipt saved.", "success")
        return redirect(url_for("accounts.receipts"))
    return render_template("accounts/receipts.html", title="Receipts", items=PaymentReceived.query.order_by(PaymentReceived.id.desc()).all(), customers=Customer.query.all(), receipt_no=next_number("receipt"), today=date.today())


@bp.route("/payments", methods=["GET", "POST"])
@login_required
def payments():
    if request.method == "POST":
        payment = PaymentMade(voucher_no=request.form.get("voucher_no") or next_number("payment"), voucher_date=date.fromisoformat(request.form["voucher_date"]), payee_type=request.form.get("payee_type") or "Supplier", supplier_id=request.form.get("supplier_id") or None, amount=request.form["amount"], payment_mode=request.form.get("payment_mode"), reference_no=request.form.get("reference_no"), notes=request.form.get("notes"), created_by=current_user.id)
        db.session.add(payment); db.session.flush(); post_supplier_payment(payment, current_user.id); db.session.commit(); flash("Payment saved.", "success")
        return redirect(url_for("accounts.payments"))
    return render_template("accounts/payments.html", title="Payments", items=PaymentMade.query.order_by(PaymentMade.id.desc()).all(), suppliers=Supplier.query.all(), voucher_no=next_number("payment"), today=date.today())


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
