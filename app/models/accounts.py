from datetime import datetime
from app.extensions import db


class FinancialYear(db.Model):
    __tablename__ = 'financial_years'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<FinancialYear {self.name}>'


class AccountGroup(db.Model):
    __tablename__ = 'account_groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # Asset, Liability, Income, Expense, Equity
    parent_id = db.Column(db.Integer, db.ForeignKey('account_groups.id'), nullable=True)
    description = db.Column(db.Text)
    is_system = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    children = db.relationship('AccountGroup', backref=db.backref('parent', remote_side=[id]))
    accounts = db.relationship('ChartOfAccounts', backref='group', lazy='dynamic')

    def __repr__(self):
        return f'<AccountGroup {self.name}>'


class ChartOfAccounts(db.Model):
    __tablename__ = 'chart_of_accounts'
    id = db.Column(db.Integer, primary_key=True)
    account_code = db.Column(db.String(20), unique=True, nullable=False)
    account_name = db.Column(db.String(150), nullable=False)
    account_group_id = db.Column(db.Integer, db.ForeignKey('account_groups.id'), nullable=False)
    description = db.Column(db.Text)
    opening_balance = db.Column(db.Numeric(12, 2), default=0)
    current_balance = db.Column(db.Numeric(12, 2), default=0)
    is_system = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    journal_lines = db.relationship('JournalEntryLine', backref='account', lazy='dynamic')

    def __repr__(self):
        return f'<Account {self.account_code} {self.account_name}>'


class JournalEntry(db.Model):
    __tablename__ = 'journal_entries'
    id = db.Column(db.Integer, primary_key=True)
    entry_no = db.Column(db.String(30), unique=True, nullable=False)
    entry_date = db.Column(db.Date, nullable=False)
    reference_type = db.Column(db.String(30))
    reference_id = db.Column(db.Integer)
    narration = db.Column(db.Text)
    total_debit = db.Column(db.Numeric(12, 2), default=0)
    total_credit = db.Column(db.Numeric(12, 2), default=0)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    lines = db.relationship('JournalEntryLine', backref='journal_entry', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<JournalEntry {self.entry_no}>'


class JournalEntryLine(db.Model):
    __tablename__ = 'journal_entry_lines'
    id = db.Column(db.Integer, primary_key=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id', ondelete='CASCADE'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('chart_of_accounts.id'), nullable=False)
    debit = db.Column(db.Numeric(12, 2), default=0)
    credit = db.Column(db.Numeric(12, 2), default=0)
    narration = db.Column(db.String(255))

    def __repr__(self):
        return f'<JournalEntryLine {self.account_id} Dr:{self.debit} Cr:{self.credit}>'


class CustomerLedger(db.Model):
    __tablename__ = 'customer_ledger'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    reference_type = db.Column(db.String(30))
    reference_id = db.Column(db.Integer)
    reference_no = db.Column(db.String(30))
    debit = db.Column(db.Numeric(12, 2), default=0)
    credit = db.Column(db.Numeric(12, 2), default=0)
    balance = db.Column(db.Numeric(12, 2), default=0)
    narration = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CustomerLedger {self.customer_id} {self.reference_no}>'


class SupplierLedger(db.Model):
    __tablename__ = 'supplier_ledger'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    reference_type = db.Column(db.String(30))
    reference_id = db.Column(db.Integer)
    reference_no = db.Column(db.String(30))
    debit = db.Column(db.Numeric(12, 2), default=0)
    credit = db.Column(db.Numeric(12, 2), default=0)
    balance = db.Column(db.Numeric(12, 2), default=0)
    narration = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SupplierLedger {self.supplier_id} {self.reference_no}>'


class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'
    id = db.Column(db.Integer, primary_key=True)
    account_name = db.Column(db.String(100), nullable=False)
    account_type = db.Column(db.String(20), default='Bank')  # Bank, Cash
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(30))
    ifsc_code = db.Column(db.String(20))
    opening_balance = db.Column(db.Numeric(12, 2), default=0)
    current_balance = db.Column(db.Numeric(12, 2), default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    payments_received = db.relationship('PaymentReceived', backref='bank_account', lazy='dynamic')
    payments_made = db.relationship('PaymentMade', backref='bank_account', lazy='dynamic')

    def __repr__(self):
        return f'<BankAccount {self.account_name}>'


class CashAccount(db.Model):
    __tablename__ = 'cash_accounts'
    id = db.Column(db.Integer, primary_key=True)
    account_name = db.Column(db.String(100), nullable=False)
    opening_balance = db.Column(db.Numeric(12, 2), default=0)
    current_balance = db.Column(db.Numeric(12, 2), default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CashAccount {self.account_name}>'


class PaymentReceived(db.Model):
    __tablename__ = 'payments_received'
    id = db.Column(db.Integer, primary_key=True)
    receipt_no = db.Column(db.String(30), unique=True, nullable=False)
    receipt_date = db.Column(db.Date, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_mode = db.Column(db.String(30), default='Cash')  # Cash, Bank Transfer, UPI, Card, Cheque
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=True)
    reference_no = db.Column(db.String(50))
    notes = db.Column(db.Text)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sale = db.relationship('Sale', backref='payments')

    def __repr__(self):
        return f'<PaymentReceived {self.receipt_no}>'


class PaymentMade(db.Model):
    __tablename__ = 'payments_made'
    id = db.Column(db.Integer, primary_key=True)
    voucher_no = db.Column(db.String(30), unique=True, nullable=False)
    voucher_date = db.Column(db.Date, nullable=False)
    payee_type = db.Column(db.String(20), default='Supplier')  # Supplier, Expense, Other
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_mode = db.Column(db.String(30), default='Cash')
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=True)
    reference_no = db.Column(db.String(50))
    notes = db.Column(db.Text)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    purchase = db.relationship('Purchase', backref='payments')

    def __repr__(self):
        return f'<PaymentMade {self.voucher_no}>'


class ExpenseCategory(db.Model):
    __tablename__ = 'expense_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expenses = db.relationship('Expense', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    expense_no = db.Column(db.String(30), unique=True, nullable=False)
    expense_date = db.Column(db.Date, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    tax_amount = db.Column(db.Numeric(12, 2), default=0)
    vendor_name = db.Column(db.String(150))
    notes = db.Column(db.Text)
    attachment = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bank_account = db.relationship('BankAccount', backref='expenses')
    payments_made = db.relationship('PaymentMade', backref='expense', lazy='dynamic')

    def __repr__(self):
        return f'<Expense {self.expense_no}>'
