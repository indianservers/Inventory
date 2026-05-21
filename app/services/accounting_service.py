from datetime import date
from decimal import Decimal

from flask import abort

from app.extensions import db
from app.models import ChartOfAccounts, Customer, CustomerLedger, JournalEntry, JournalEntryLine, Supplier, SupplierLedger
from app.services.numbering_service import next_number
from app.utils.helpers import money


def account(name):
    acc = ChartOfAccounts.query.filter_by(account_name=name).first()
    if not acc:
        abort(400, f"Missing account: {name}. Run seed.py.")
    return acc


def create_journal(entry_date, reference_type, reference_id, narration, lines, user_id=None):
    total_debit = sum(money(line.get("debit", 0)) for line in lines)
    total_credit = sum(money(line.get("credit", 0)) for line in lines)
    if total_debit != total_credit:
        abort(400, "Journal entry must balance")
    journal = JournalEntry(
        entry_no=next_number("journal"),
        entry_date=entry_date or date.today(),
        reference_type=reference_type,
        reference_id=reference_id,
        narration=narration,
        total_debit=total_debit,
        total_credit=total_credit,
        created_by=user_id,
    )
    db.session.add(journal)
    db.session.flush()
    for line in lines:
        acc = line["account"]
        debit, credit = money(line.get("debit", 0)), money(line.get("credit", 0))
        db.session.add(JournalEntryLine(journal_entry_id=journal.id, account_id=acc.id, debit=debit, credit=credit, narration=line.get("narration")))
        acc.current_balance = Decimal(str(acc.current_balance or 0)) + debit - credit
    return journal


def post_sale(sale, user_id=None):
    customer = Customer.query.get(sale.customer_id)
    customer.current_balance = money(customer.current_balance) + money(sale.balance_amount)
    balance = customer.outstanding + float(sale.grand_total)
    db.session.add(CustomerLedger(date=sale.invoice_date, customer_id=sale.customer_id, reference_type="Sale", reference_id=sale.id, reference_no=sale.invoice_no, debit=sale.grand_total, credit=0, balance=balance, narration="Sales invoice"))
    lines = [
        {"account": account("Accounts Receivable"), "debit": sale.grand_total},
        {"account": account("Sales"), "credit": money(sale.grand_total) - money(sale.tax_total)},
    ]
    if money(sale.tax_total) > 0:
        lines.append({"account": account("Tax Payable"), "credit": sale.tax_total})
    create_journal(sale.invoice_date, "Sale", sale.id, f"Sale {sale.invoice_no}", lines, user_id)


def reverse_sale(sale, user_id=None, reason=None):
    customer = Customer.query.get(sale.customer_id)
    customer.current_balance = money(customer.current_balance) - money(sale.balance_amount)
    db.session.add(CustomerLedger(date=date.today(), customer_id=sale.customer_id, reference_type="SaleCancellation", reference_id=sale.id, reference_no=sale.invoice_no, debit=0, credit=sale.balance_amount, balance=customer.outstanding - float(sale.balance_amount or 0), narration=reason or "Sales invoice cancelled"))
    lines = [
        {"account": account("Sales"), "debit": money(sale.grand_total) - money(sale.tax_total)},
        {"account": account("Accounts Receivable"), "credit": sale.grand_total},
    ]
    if money(sale.tax_total) > 0:
        lines.append({"account": account("Tax Payable"), "debit": sale.tax_total})
    create_journal(date.today(), "SaleCancellation", sale.id, f"Cancel sale {sale.invoice_no}", lines, user_id)


def post_purchase(purchase, user_id=None):
    supplier = Supplier.query.get(purchase.supplier_id)
    supplier.current_balance = money(supplier.current_balance) + money(purchase.balance_amount)
    balance = supplier.outstanding + float(purchase.grand_total)
    db.session.add(SupplierLedger(date=purchase.purchase_date, supplier_id=purchase.supplier_id, reference_type="Purchase", reference_id=purchase.id, reference_no=purchase.purchase_no, debit=0, credit=purchase.grand_total, balance=balance, narration="Purchase invoice"))
    lines = [
        {"account": account("Inventory"), "debit": money(purchase.grand_total) - money(purchase.tax_total)},
        {"account": account("Accounts Payable"), "credit": purchase.grand_total},
    ]
    if money(purchase.tax_total) > 0:
        lines.append({"account": account("Tax Payable"), "debit": purchase.tax_total})
    create_journal(purchase.purchase_date, "Purchase", purchase.id, f"Purchase {purchase.purchase_no}", lines, user_id)


def post_customer_receipt(receipt, user_id=None):
    customer = Customer.query.get(receipt.customer_id)
    customer.current_balance = money(customer.current_balance) - money(receipt.amount)
    db.session.add(CustomerLedger(date=receipt.receipt_date, customer_id=receipt.customer_id, reference_type="Receipt", reference_id=receipt.id, reference_no=receipt.receipt_no, debit=0, credit=receipt.amount, balance=customer.outstanding - float(receipt.amount), narration="Customer receipt"))
    create_journal(receipt.receipt_date, "Receipt", receipt.id, f"Receipt {receipt.receipt_no}", [{"account": account("Cash"), "debit": receipt.amount}, {"account": account("Accounts Receivable"), "credit": receipt.amount}], user_id)


def post_supplier_payment(payment, user_id=None):
    supplier = Supplier.query.get(payment.supplier_id)
    if supplier:
        supplier.current_balance = money(supplier.current_balance) - money(payment.amount)
        db.session.add(SupplierLedger(date=payment.voucher_date, supplier_id=supplier.id, reference_type="Payment", reference_id=payment.id, reference_no=payment.voucher_no, debit=payment.amount, credit=0, balance=supplier.outstanding - float(payment.amount), narration="Supplier payment"))
    create_journal(payment.voucher_date, "Payment", payment.id, f"Payment {payment.voucher_no}", [{"account": account("Accounts Payable"), "debit": payment.amount}, {"account": account("Cash"), "credit": payment.amount}], user_id)
