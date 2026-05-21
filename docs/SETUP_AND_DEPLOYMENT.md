# Setup And Deployment Notes

## Database

Run migrations after pulling this strengthening pass:

```powershell
flask db upgrade
```

Applied migrations in this pass:

| Migration | Purpose |
|---|---|
| `d9b2b9b6e1f1_razorpay_fields.py` | Stores Razorpay order/payment/signature verification fields on sales. |
| `e4c8a40b3b6f_itc_register.py` | Adds ITC register table. |
| `f7a1c2d3e4b5_loyalty_coupons.py` | Adds loyalty, coupon and promotion tables. |

## Integration Configuration

Set credentials through environment variables or active integration settings:

| Integration | Environment Variables |
|---|---|
| Razorpay | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` |
| SMTP Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` |
| WhatsApp Cloud API | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID` |

## Scheduled Tasks

Existing CLI commands:

```powershell
flask recurring run
flask reports send-due
flask scheduler run
```

Use Windows Task Scheduler or cron to call these commands on the desired cadence.

## Verification

Commands run successfully during this pass:

```powershell
python -m compileall app migrations tests
pytest -q
flask db upgrade
```

Result: `17 passed`.

Authenticated smoke checks also returned `200` for:

| Route | Result |
|---|---|
| `/stock/reorder-suggestions` | OK |
| `/accounts/itc` | OK |
| `/reports/gstr3b` | OK |
| `/reports/tally-export` | OK |
| `/settings/loyalty` | OK |
| `/settings/coupons` | OK |
