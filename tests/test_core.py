import os

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test")

from app import create_app
from app.extensions import db
from werkzeug.exceptions import BadRequest

from app.models import AccountGroup, ChartOfAccounts, Customer, Product, Role, Sale, Supplier, Tax, Unit, User, Warehouse
from app.services.accounting_service import create_journal
from app.services.invoice_service import cancel_invoice, create_or_update_invoice, issue_invoice, line_totals, record_invoice_payment


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


def invoice_form(customer, warehouse):
    return {
        "invoice_no": "INV-T1",
        "invoice_date": "2026-05-10",
        "due_date": "2026-06-09",
        "customer_id": str(customer.id),
        "warehouse_id": str(warehouse.id),
        "sale_type": "Credit",
        "shipping_charges": "0",
        "other_charges": "0",
        "round_off": "0",
        "notes": "",
        "terms": "",
    }


def test_invoice_issue_deducts_stock_and_posts_balance():
    app = app_with_db()
    with app.app_context():
        product = Product.query.filter_by(sku="P1").first()
        customer = Customer.query.first()
        warehouse = Warehouse.query.first()
        sale = Sale()
        item = {"product_id": product.id, "quantity": "2", "rate": "150", "discount": "0", "tax_rate": "18", **line_totals("2", "150", "0", "18")}

        create_or_update_invoice(sale, invoice_form(customer, warehouse), [item], 1)
        assert sale.status == "Draft"
        issue_invoice(sale, 1)
        db.session.commit()

        assert sale.status == "Issued"
        assert float(product.current_stock) == 8
        assert float(sale.grand_total) == 354
        assert round(customer.outstanding, 2) == 354


def test_invoice_payments_update_status_and_reject_overpayment():
    app = app_with_db()
    with app.app_context():
        product = Product.query.filter_by(sku="P1").first()
        customer = Customer.query.first()
        warehouse = Warehouse.query.first()
        sale = Sale()
        item = {"product_id": product.id, "quantity": "1", "rate": "100", "discount": "0", "tax_rate": "0", **line_totals("1", "100", "0", "0")}
        create_or_update_invoice(sale, invoice_form(customer, warehouse), [item], 1)
        issue_invoice(sale, 1)
        record_invoice_payment(sale, "40", sale.invoice_date, "Cash", "R1", "", 1)
        assert sale.status == "Partially Paid"
        assert float(sale.balance_amount) == 60

        try:
            record_invoice_payment(sale, "61", sale.invoice_date, "Cash", "R2", "", 1)
            assert False, "Expected overpayment to be rejected"
        except BadRequest:
            pass

        record_invoice_payment(sale, "60", sale.invoice_date, "Cash", "R3", "", 1)
        assert sale.status == "Paid"
        assert float(sale.balance_amount) == 0


def test_unpaid_invoice_cancellation_reverses_stock():
    app = app_with_db()
    with app.app_context():
        product = Product.query.filter_by(sku="P1").first()
        customer = Customer.query.first()
        warehouse = Warehouse.query.first()
        sale = Sale()
        item = {"product_id": product.id, "quantity": "3", "rate": "100", "discount": "0", "tax_rate": "0", **line_totals("3", "100", "0", "0")}
        create_or_update_invoice(sale, invoice_form(customer, warehouse), [item], 1)
        issue_invoice(sale, 1)
        assert float(product.current_stock) == 7

        cancel_invoice(sale, "Wrong invoice", 1)
        db.session.commit()

        assert sale.status == "Cancelled"
        assert float(product.current_stock) == 10


def test_invoice_pages_and_api_render():
    app = app_with_db()
    with app.app_context():
        product = Product.query.filter_by(sku="P1").first()
        customer = Customer.query.first()
        warehouse = Warehouse.query.first()
        sale = Sale()
        item = {"product_id": product.id, "quantity": "1", "rate": "150", "discount": "0", "tax_rate": "18", **line_totals("1", "150", "0", "18")}
        create_or_update_invoice(sale, invoice_form(customer, warehouse), [item], 1)
        issue_invoice(sale, 1)
        db.session.commit()
        sale_id = sale.id

    with app.test_client() as client:
        login(client)
        for path in ["/invoices/", "/invoices/create", f"/invoices/{sale_id}", f"/api/invoices/{sale_id}"]:
            rv = client.get(path)
            assert rv.status_code == 200
