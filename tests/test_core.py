import os
import hmac
from hashlib import sha256

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test")

from app import create_app
from app.extensions import db
from werkzeug.exceptions import BadRequest

from app.models import AccountGroup, Branch, ChartOfAccounts, Customer, CustomField, CustomModule, CustomModuleField, CustomModuleRecord, CustomView, HeldBill, PaymentReceived, POSSession, Product, Register, Role, Sale, Supplier, Tax, Unit, User, Warehouse
from app.routes.reports_routes import build_tally_xml
from app.services.accounting_service import create_journal
from app.services.invoice_service import cancel_invoice, create_or_update_invoice, issue_invoice, line_totals, record_invoice_payment
from app.utils.tax_validation import is_valid_gstin, is_valid_hsn, is_valid_pan, is_valid_trn


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
        branch = Branch(name="Main Branch", code="MAIN")
        db.session.add(branch); db.session.flush()
        wh = Warehouse(name="Main", code="MAIN", branch_id=branch.id)
        cust = Customer(customer_code="C1", name="Customer")
        sup = Supplier(supplier_code="S1", name="Supplier")
        db.session.add_all([tax, unit, wh, cust, sup]); db.session.flush()
        db.session.add(Register(name="Main POS", code="POS-1", branch_id=branch.id, warehouse_id=wh.id, status=True))
        db.session.add(Product(sku="P1", barcode="89000000801", name="Product", tax_id=tax.id, unit_id=unit.id, warehouse_id=wh.id, purchase_price=100, sales_price=150, current_stock=10, average_cost=100, is_active=True))
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


def test_product_master_ui_filters_render():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        rv = client.get("/products/?q=P1&stock_status=active")
        assert rv.status_code == 200
        assert b"Inventory command center" in rv.data
        assert b"POS Preferences" in rv.data


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


def open_pos_session(client):
    return client.post("/pos/open-session", data={"register_id": "1", "opening_cash": "100"}, follow_redirects=True)


def test_pos_terminal_add_item_page():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        rv = open_pos_session(client)
        assert rv.status_code == 200
        assert b"Scan barcode or search product" in rv.data
        assert b"Product" in rv.data


def test_pos_redirects_without_active_session():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        rv = client.get("/pos/terminal", follow_redirects=False)
        assert rv.status_code == 302
        assert "/pos/" in rv.headers["Location"]


def test_pos_product_search_by_sku_and_barcode():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        open_pos_session(client)
        sku = client.get("/pos/products/search?q=P1")
        barcode = client.get("/pos/products/search?q=89000000801")
        assert sku.status_code == 200
        assert sku.json["data"][0]["sku"] == "P1"
        assert barcode.status_code == 200


def test_pos_hold_and_recall_bill():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        open_pos_session(client)
        rv = client.post("/pos/hold", json={"customer_id": 1, "warehouse_id": 1, "notes": "Counter wait", "items": [{"product_id": 1, "name": "Product", "qty": 1, "rate": 150, "discount": 0, "tax_rate": 18}]})
        assert rv.status_code == 200
        hold_id = rv.json["id"]
        listed = client.get("/pos/held.json")
        assert listed.status_code == 200
        assert listed.json["data"][0]["id"] == hold_id
        recalled = client.get(f"/pos/held/{hold_id}/json")
        assert recalled.status_code == 200
        assert recalled.json["items"][0]["product_id"] == 1
        with app.app_context():
            assert HeldBill.query.get(hold_id).status == "Recalled"


def test_pos_complete_sale_and_reduce_stock():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        open_pos_session(client)
        rv = client.post("/pos/sale", json={"customer_id": 1, "warehouse_id": 1, "items": [{"product_id": 1, "qty": 2, "rate": 150, "discount": 0, "tax_rate": 18}], "payment_mode": "Cash", "cash_tendered": 400})
        assert rv.status_code == 200
        assert rv.json["invoice_no"]
        assert round(rv.json["grand_total"], 2) == 354
        with app.app_context():
            assert float(Product.query.get(1).current_stock) == 8
            assert Sale.query.get(rv.json["sale_id"]).payment_status == "Paid"


def test_pos_complete_split_payment_sale():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        open_pos_session(client)
        rv = client.post("/pos/sale", json={"customer_id": 1, "warehouse_id": 1, "items": [{"product_id": 1, "qty": 1, "rate": 100, "discount": 0, "tax_rate": 0}], "payment_mode": "Split", "cash_tendered": 40, "card_amount": 60, "reference_no": "CARD-1"})
        assert rv.status_code == 200
        with app.app_context():
            pos_session = POSSession.query.first()
            assert float(pos_session.total_cash) == 40
            assert float(pos_session.total_card) == 60


def test_pos_complete_credit_sale_with_customer_and_reject_without_customer():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        open_pos_session(client)
        missing = client.post("/pos/sale", json={"warehouse_id": 1, "items": [{"product_id": 1, "qty": 1, "rate": 100, "discount": 0, "tax_rate": 0}], "payment_mode": "Credit"})
        assert missing.status_code == 400
        ok = client.post("/pos/sale", json={"customer_id": 1, "warehouse_id": 1, "items": [{"product_id": 1, "qty": 1, "rate": 100, "discount": 0, "tax_rate": 0}], "payment_mode": "Credit"})
        assert ok.status_code == 200
        with app.app_context():
            sale = Sale.query.get(ok.json["sale_id"])
            assert sale.payment_status == "Unpaid"
            assert sale.sale_type == "Credit"


def test_pos_line_discount_and_duplicate_submit():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        open_pos_session(client)
        payload = {"request_id": "dup-1", "customer_id": 1, "warehouse_id": 1, "items": [{"product_id": 1, "qty": 1, "rate": 100, "discount": 10, "tax_rate": 0}], "payment_mode": "Cash", "cash_tendered": 100}
        first = client.post("/pos/sale", json=payload)
        second = client.post("/pos/sale", json=payload)
        assert first.status_code == 200
        assert round(first.json["grand_total"], 2) == 90
        assert second.status_code == 409


def test_pos_add_service_item_without_stock_reduction():
    app = app_with_db()
    with app.app_context():
        unit = Unit.query.first()
        tax = Tax.query.first()
        service = Product(sku="SVC1", name="Consulting Service", tax_id=tax.id, unit_id=unit.id, sales_price=500, purchase_price=0, current_stock=0, track_inventory=False, is_active=True)
        db.session.add(service)
        db.session.commit()
        service_id = service.id
    with app.test_client() as client:
        login(client)
        open_pos_session(client)
        rv = client.post("/pos/sale", json={"customer_id": 1, "warehouse_id": 1, "items": [{"product_id": service_id, "qty": 1, "rate": 500, "discount": 0, "tax_rate": 0}], "payment_mode": "Cash", "cash_tendered": 500})
        assert rv.status_code == 200
        with app.app_context():
            assert float(Product.query.get(service_id).current_stock) == 0


def test_pos_insufficient_stock_returns_json_error():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        open_pos_session(client)
        rv = client.post("/pos/sale", json={"customer_id": 1, "warehouse_id": 1, "items": [{"product_id": 1, "qty": 99, "rate": 150, "discount": 0, "tax_rate": 18}], "payment_mode": "Cash", "cash_tendered": 20000})
        assert rv.status_code == 400
        assert "Insufficient stock" in rv.json["error"]


def test_pos_close_session_calculation():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        open_pos_session(client)
        client.post("/pos/sale", json={"customer_id": 1, "warehouse_id": 1, "items": [{"product_id": 1, "qty": 1, "rate": 100, "discount": 0, "tax_rate": 0}], "payment_mode": "Cash", "cash_tendered": 120})
        rv = client.post("/pos/close-session", data={"closing_cash": "210"})
        assert rv.status_code == 200
        assert b"Z Report" in rv.data
        with app.app_context():
            pos_session = POSSession.query.first()
            assert float(pos_session.expected_closing_cash) == 200
            assert float(pos_session.cash_difference) == 10


def create_issued_invoice_for_payment(app):
    with app.app_context():
        product = Product.query.filter_by(sku="P1").first()
        customer = Customer.query.first()
        warehouse = Warehouse.query.first()
        sale = Sale()
        item = {"product_id": product.id, "quantity": "1", "rate": "100", "discount": "0", "tax_rate": "0", **line_totals("1", "100", "0", "0")}
        create_or_update_invoice(sale, invoice_form(customer, warehouse), [item], 1)
        issue_invoice(sale, 1)
        db.session.commit()
        return sale.id


def razorpay_signature(secret, order_id, payment_id):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), sha256).hexdigest()


def test_razorpay_valid_signature_marks_invoice_paid():
    app = app_with_db()
    sale_id = create_issued_invoice_for_payment(app)
    os.environ["RAZORPAY_KEY_SECRET"] = "secret"
    with app.test_client() as client:
        rv = client.post(f"/invoices/{sale_id}/payment-callback", data={"razorpay_order_id": "order_1", "razorpay_payment_id": "pay_1", "razorpay_signature": razorpay_signature("secret", "order_1", "pay_1")}, follow_redirects=False)
        assert rv.status_code == 302
    with app.app_context():
        sale = Sale.query.get(sale_id)
        assert sale.payment_status == "Paid"
        assert sale.razorpay_payment_id == "pay_1"
        assert sale.razorpay_verified_at is not None


def test_razorpay_invalid_signature_does_not_mark_paid():
    app = app_with_db()
    sale_id = create_issued_invoice_for_payment(app)
    os.environ["RAZORPAY_KEY_SECRET"] = "secret"
    with app.test_client() as client:
        rv = client.post(f"/invoices/{sale_id}/payment-callback", data={"razorpay_order_id": "order_1", "razorpay_payment_id": "pay_bad", "razorpay_signature": "bad"}, follow_redirects=False)
        assert rv.status_code == 302
    with app.app_context():
        sale = Sale.query.get(sale_id)
        assert sale.payment_status == "Unpaid"
        assert sale.razorpay_payment_id is None


def test_razorpay_duplicate_callback_is_ignored():
    app = app_with_db()
    sale_id = create_issued_invoice_for_payment(app)
    os.environ["RAZORPAY_KEY_SECRET"] = "secret"
    payload = {"razorpay_order_id": "order_1", "razorpay_payment_id": "pay_dup", "razorpay_signature": razorpay_signature("secret", "order_1", "pay_dup")}
    with app.test_client() as client:
        assert client.post(f"/invoices/{sale_id}/payment-callback", data=payload).status_code == 302
        assert client.post(f"/invoices/{sale_id}/payment-callback", data=payload).status_code == 302
    with app.app_context():
        assert PaymentReceived.query.filter_by(reference_no="pay_dup").count() == 1


def test_tax_validation_helpers():
    assert is_valid_pan("ABCDE1234F")
    assert not is_valid_pan("BADPAN")
    assert is_valid_hsn("1001")
    assert not is_valid_hsn("10AB")
    assert is_valid_trn("100000000000003")
    assert not is_valid_trn("123")
    assert not is_valid_gstin("22AAAAA0000A1Z0")


def test_tally_export_xml_is_well_formed():
    app = app_with_db()
    sale_id = create_issued_invoice_for_payment(app)
    with app.app_context():
        sale = Sale.query.get(sale_id)
        xml = build_tally_xml("sales", sale.invoice_date, sale.invoice_date)
        assert "<ENVELOPE>" in xml
        assert sale.invoice_no in xml


def test_customization_fields_views_and_modules_workflow():
    app = app_with_db()
    with app.test_client() as client:
        login(client)
        field = client.post("/settings/custom-fields", data={"entity_type": "products", "field_key": "season", "label": "Season", "field_type": "Dropdown", "options": "Summer\nWinter", "is_active": "on"})
        assert field.status_code == 302
        view = client.post("/settings/custom-views", data={"entity_type": "products", "name": "Fast Moving Items", "filters_json": "{\"stock\":\"positive\"}", "columns_json": "[\"sku\",\"name\"]", "sort_json": "{\"name\":\"asc\"}"})
        assert view.status_code == 302
        module_response = client.post("/settings/custom-modules", data={"name": "Service Job", "plural_name": "Service Jobs", "module_key": "service_jobs", "description": "Track repair and service jobs", "show_in_sidebar": "on", "allow_import": "on", "allow_export": "on", "is_active": "on"})
        assert module_response.status_code == 302
        with app.app_context():
            module = CustomModule.query.filter_by(module_key="service_jobs").one()
            module_id = module.id
            assert module.fields.filter_by(field_key="title").count() == 1
            assert CustomField.query.filter_by(field_key="season").count() == 1
            assert CustomView.query.filter_by(name="Fast Moving Items").count() == 1
        add_field = client.post(f"/settings/custom-modules/{module_id}/fields", data={"label": "Due Date", "field_key": "due_date", "field_type": "Date", "is_required": "on", "show_in_list": "on", "sort_order": "2"})
        assert add_field.status_code == 302
        with app.app_context():
            due = CustomModuleField.query.filter_by(module_id=module_id, field_key="due_date").one()
            due_id = due.id
        record = client.post(f"/settings/custom-modules/{module_id}", data={"title": "Repair ticket 1001", "status": "Active", f"field_{due_id}": "2026-06-01"})
        assert record.status_code == 302
        detail = client.get(f"/settings/custom-modules/{module_id}")
        assert detail.status_code == 200
        assert b"Repair ticket 1001" in detail.data
        with app.app_context():
            saved = CustomModuleRecord.query.filter_by(module_id=module_id).one()
            assert "2026-06-01" in saved.data_json
