import os

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test")

from app import create_app
from app.extensions import db
from app.models import AccountGroup, ChartOfAccounts, Customer, Product, Role, Supplier, Tax, Unit, User, Warehouse
from app.services.accounting_service import create_journal


def app_with_db():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
        role = Role(name="Super Admin")
        db.session.add(role); db.session.flush()
        user = User(name="Admin", email="admin@example.com", role_id=role.id, is_active=True)
        user.set_password("admin123")
        db.session.add(user)
        group = AccountGroup(name="Assets", type="Asset")
        db.session.add(group); db.session.flush()
        for idx, name in enumerate(["Cash", "Accounts Receivable", "Accounts Payable", "Sales", "Inventory", "Tax Payable"], start=1):
            db.session.add(ChartOfAccounts(account_code=str(idx), account_name=name, account_group_id=group.id, is_active=True))
        tax = Tax(name="GST 18", rate=18)
        unit = Unit(name="Piece", short_name="pcs")
        wh = Warehouse(name="Main", code="MAIN")
        cust = Customer(customer_code="C1", name="Customer")
        sup = Supplier(supplier_code="S1", name="Supplier")
        db.session.add_all([tax, unit, wh, cust, sup]); db.session.flush()
        db.session.add(Product(sku="P1", name="Product", tax_id=tax.id, unit_id=unit.id, warehouse_id=wh.id, purchase_price=100, sales_price=150, current_stock=10, average_cost=100, is_active=True))
        db.session.commit()
    return app


def login(client):
    return client.post("/login", data={"email": "admin@example.com", "password": "admin123"}, follow_redirects=True)


def test_login():
    app = app_with_db()
    with app.test_client() as client:
        rv = login(client)
        assert b"Dashboard" in rv.data


def test_product_api():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        rv = client.get("/api/products")
        assert rv.json[0]["sku"] == "P1"


def test_journal_must_balance():
    app = app_with_db()
    with app.app_context():
        cash = ChartOfAccounts.query.filter_by(account_name="Cash").first()
        sales = ChartOfAccounts.query.filter_by(account_name="Sales").first()
        journal = create_journal(None, "Test", None, "Balanced", [{"account": cash, "debit": 100}, {"account": sales, "credit": 100}])
        assert journal.total_debit == journal.total_credit

