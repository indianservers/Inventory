from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import BankAccount, ChartOfAccounts, Customer, Expense, ExpenseCategory, JournalEntry, PaymentMade, PaymentReceived, Supplier
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

