# Vyapara ERP

Vyapara ERP is a Flask, SQLAlchemy, MySQL, Bootstrap 5 business management system for stock, sales, purchases, ledgers, payments, reports, users, and settings.

## Features

- Secure login, logout, profile, change-password, roles, permissions
- Dashboard with sales, purchases, receivables, payables, stock value, low-stock alerts, Chart.js
- Product, category, brand, unit, warehouse, customer, supplier masters
- Purchase invoice flow with stock increase, weighted-average cost, supplier ledger, journal entry
- Sales invoice flow with stock decrease, customer ledger, journal entry, invoice print and PDF
- Receipts, payments, expenses, chart of accounts, journal entries
- Inventory ledger, stock adjustment, current stock, core reports
- REST/AJAX endpoints for products, parties, sales, purchases, stock and profit/loss
- Upload/backup folders and backup service helpers

## Stack

Python, Flask, Jinja2, Flask-SQLAlchemy, Flask-Login, Flask-WTF, MySQL/PyMySQL, Bootstrap 5, Bootstrap Icons, DataTables, Chart.js, ReportLab, pytest.

## Installation

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Update `.env` for local development:

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=stock_accounts_db
DB_USER=root
DB_PASSWORD=123456
SECRET_KEY=change-this-secret-key
APP_ENV=development
```

The app creates the MySQL database automatically if it does not exist.

## Initialize

```powershell
python seed.py
```

This creates tables and inserts roles, permissions, accounts, settings, taxes, units, sample masters, and the default admin.

## Run

```powershell
python run.py
```

Open `http://127.0.0.1:5000`.

Default login:

- Email: `admin@example.com`
- Password: `admin123`

## Development Notes

The deepest completed flows are sales, purchases, inventory ledger, weighted-average costing, customer/supplier ledgers, balanced journals, receipts, payments, and the dashboard/report surface. Return, quotation, proforma, challan, restore, WhatsApp/email, and advanced PDF templates have database models and navigation placeholders ready for extension.

## Phase 3 Upgrades

- Recurring invoices with run-now, due-run route, and `flask recurring run` scheduler command.
- Multi-currency master data, live exchange-rate refresh, and INR snapshots on sales/purchases.
- BOM and manufacturing orders with component issue and finished-good receipt stock ledger entries.
- ABC analysis, dead stock, stock health, and sales velocity reports with Excel exports.
- Mobile PWA install support, service worker, offline fallback, app icons, and mobile bottom navigation.
- Print template editor with Classic, Modern, and Thermal invoice template seeds.
- Scheduled report emails via SMTP and `flask reports send-due`.
- TDS/TCS ledgers, default TDS sections, supplier TDS flags, and purchase-side TDS deduction.

For daily automation, call `flask recurring run` and `flask reports send-due` from Windows Task Scheduler or cron once per day. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, and `SMTP_FROM` before enabling scheduled email delivery.

## Tests

```powershell
pytest
```
