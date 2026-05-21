from datetime import date

from app import create_app
from app.extensions import db
from app.models import (
    AccountGroup,
    Brand,
    Category,
    ChartOfAccounts,
    CompanySetting,
    Customer,
    ExpenseCategory,
    FinancialYear,
    Permission,
    Product,
    Role,
    RolePermission,
    Supplier,
    Tax,
    Unit,
    User,
    Warehouse,
)

app = create_app()

ROLES = ["Super Admin", "Admin", "Accountant", "Sales Executive", "Purchase Executive", "Stock Manager", "Viewer"]
MODULES = ["dashboard", "products", "categories", "brands", "units", "warehouses", "customers", "suppliers", "purchases", "sales", "invoices", "returns", "quotations", "payments", "stock", "accounts", "expenses", "reports", "settings", "backup", "audit"]
ACTIONS = ["view", "create", "edit", "delete", "print", "export", "approve"]


def get_or_create(model, defaults=None, **filters):
    obj = model.query.filter_by(**filters).first()
    if obj:
        return obj
    obj = model(**filters)
    for key, value in (defaults or {}).items():
        setattr(obj, key, value)
    db.session.add(obj)
    db.session.flush()
    return obj


with app.app_context():
    db.create_all()

    roles = {name: get_or_create(Role, name=name, defaults={"description": name, "is_system": True}) for name in ROLES}
    permissions = []
    for module in MODULES:
        for action in ACTIONS:
            permissions.append(get_or_create(Permission, module=module, action=action, defaults={"description": f"{action} {module}"}))
    db.session.flush()
    for role_name, role in roles.items():
        for perm in permissions:
            allowed = role_name in ["Super Admin", "Admin"] or perm.action == "view"
            if role_name == "Accountant" and perm.module in ["accounts", "payments", "expenses", "reports"]:
                allowed = True
            if role_name == "Sales Executive" and perm.module in ["sales", "invoices", "customers", "quotations", "reports"]:
                allowed = perm.action != "delete"
            if role_name == "Purchase Executive" and perm.module in ["purchases", "suppliers", "reports"]:
                allowed = perm.action != "delete"
            if role_name == "Stock Manager" and perm.module in ["products", "stock", "warehouses", "reports"]:
                allowed = perm.action != "delete"
            rp = RolePermission.query.filter_by(role_id=role.id, permission_id=perm.id).first()
            if not rp:
                db.session.add(RolePermission(role_id=role.id, permission_id=perm.id, granted=allowed))
            else:
                rp.granted = allowed

    admin = User.query.filter_by(email="admin@example.com").first()
    if not admin:
        admin = User(name="Administrator", email="admin@example.com", role_id=roles["Super Admin"].id, is_active=True)
        admin.set_password("admin123")
        db.session.add(admin)

    setting = CompanySetting.query.first()
    if not setting:
        db.session.add(CompanySetting(company_name="Vyapara ERP", address="Your business address", phone="9999999999", email="admin@example.com", tax_number="GSTIN000000000", default_invoice_terms="Goods once sold are subject to business terms."))

    warehouse = get_or_create(Warehouse, code="MAIN", defaults={"name": "Main Warehouse", "status": True})
    unit = get_or_create(Unit, name="Piece", defaults={"short_name": "pcs", "decimal_allowed": False, "status": True})
    get_or_create(Unit, name="Kilogram", defaults={"short_name": "kg", "decimal_allowed": True, "status": True})
    category = get_or_create(Category, name="General", defaults={"description": "General items", "status": True})
    brand = get_or_create(Brand, name="Generic", defaults={"description": "Generic brand", "status": True})
    tax = get_or_create(Tax, name="GST 18%", defaults={"rate": 18, "tax_type": "GST", "status": True})
    get_or_create(Tax, name="GST 5%", defaults={"rate": 5, "tax_type": "GST", "status": True})

    customer = get_or_create(Customer, customer_code="CUST-001", defaults={"name": "Cash Customer", "phone": "9999999999", "country": "India", "status": True})
    supplier = get_or_create(Supplier, supplier_code="SUP-001", defaults={"name": "Default Supplier", "phone": "8888888888", "country": "India", "status": True})

    if not Product.query.filter_by(sku="SKU-001").first():
        db.session.add(Product(sku="SKU-001", barcode="890000000001", name="Sample Product", category_id=category.id, brand_id=brand.id, unit_id=unit.id, tax_id=tax.id, purchase_price=100, sales_price=150, mrp=175, opening_stock=50, current_stock=50, average_cost=100, min_stock=10, warehouse_id=warehouse.id, is_active=True))

    groups = {
        "Cash": "Asset", "Bank": "Asset", "Accounts Receivable": "Asset", "Inventory": "Asset",
        "Accounts Payable": "Liability", "Tax Payable": "Liability", "Loans": "Liability",
        "Sales": "Income", "Other Income": "Income",
        "Purchases": "Expense", "Cost of Goods Sold": "Expense", "Rent": "Expense", "Salary": "Expense", "Utilities": "Expense", "General Expense": "Expense",
        "Capital": "Equity", "Drawings": "Equity", "Retained Earnings": "Equity",
    }
    group_objs = {name: get_or_create(AccountGroup, name=name, defaults={"type": typ, "is_system": True}) for name, typ in groups.items()}
    for idx, name in enumerate(groups.keys(), start=1000):
        get_or_create(ChartOfAccounts, account_name=name, defaults={"account_code": str(idx), "account_group_id": group_objs[name].id, "is_system": True, "is_active": True})

    get_or_create(ExpenseCategory, name="General Expense", defaults={"status": True})
    get_or_create(FinancialYear, name="2026-27", defaults={"start_date": date(2026, 4, 1), "end_date": date(2027, 3, 31), "is_current": True})

    db.session.commit()
    print("Seed data inserted. Login: admin@example.com / admin123")
