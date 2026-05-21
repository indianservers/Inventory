# Implemented Features

| Feature | Status | Files Changed | Testing Done | Notes |
|---|---|---|---|---|
| Production POS terminal | Implemented | `app/templates/pos/terminal.html`, `app/static/js/pos.js`, `app/routes/pos_routes.py` | `pytest -q` POS hold/recall/sale/stock/session tests | Uses existing POS session and sale backend. |
| Razorpay hardening | Implemented | `app/routes/invoice_routes.py`, `app/models/sales.py`, `migrations/versions/d9b2b9b6e1f1_razorpay_fields.py` | Valid signature, invalid signature and duplicate callback tests | Never marks paid without signature verification. |
| SMTP settings fallback | Implemented | `app/services/email_service.py`, `app/routes/integration_routes.py`, `app/templates/settings/foundation_list.html` | Syntax and unit suite | Reads env vars or active email integration settings. |
| GST/PAN/HSN/TRN validation | Implemented | `app/utils/tax_validation.py`, `app/routes/party_routes.py`, `app/routes/product_routes.py`, `app/routes/settings_routes.py` | Tax utility tests | Integrated into master forms. |
| ITC register | Implemented | `app/models/accounts.py`, `app/routes/accounts_routes.py`, `app/templates/accounts/itc.html`, `migrations/versions/e4c8a40b3b6f_itc_register.py` | Syntax and route import coverage | Purchase create/approve creates or updates ITC entries. |
| GSTR-3B | Implemented | `app/routes/reports_routes.py`, `app/templates/reports/gstr3b.html` | Syntax and unit suite | Includes Excel and JSON export. |
| Reorder suggestions to PO | Implemented | `app/routes/stock_routes.py`, `app/templates/stock/reorder_suggestions.html`, `app/templates/base.html` | Syntax and unit suite | User confirms selected products before draft PO creation. |
| Loyalty and coupons foundation | Implemented | `app/models/settings.py`, `app/services/loyalty_service.py`, `app/services/coupon_service.py`, `app/routes/integration_routes.py`, `migrations/versions/f7a1c2d3e4b5_loyalty_coupons.py` | Syntax and unit suite | POS can apply coupons and earn points. |
| Tally XML export | Implemented | `app/routes/reports_routes.py`, `app/templates/reports/tally_export.html` | XML export test | Supports vouchers, parties and stock items. |
| PWA hardening | Implemented | `app/static/manifest.json`, `app/static/sw.js`, `app/static/icons/icon-192.png`, `app/static/icons/icon-512.png` | Syntax and app smoke | Sensitive data routes are not cached. |
| Security headers/login throttle | Implemented | `app/__init__.py`, `app/routes/auth_routes.py` | `pytest -q` | Adds secure headers, login lockout and audit logs. |
