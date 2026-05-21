# Remaining Gaps

| Area | Remaining Gap | Priority | Notes |
|---|---|---|---|
| Third-party integrations | Razorpay, SMTP and Meta WhatsApp require live credentials. | High | Logic is implemented; configure env vars or integration settings. |
| Loyalty redemption | Points earning exists; redemption UI and expiry batch processing are not yet complete. | Medium | Tables and ledger are ready. |
| Promotion engine | Coupon rules exist; complex promotion stacking and invoice-form promotions are still foundation-level. | Medium | POS coupon application works. |
| ITC split rules | Current purchase ITC split defaults to CGST/SGST split. | Medium | Add interstate/vendor-place logic for IGST automation. |
| Tally import mapping | XML is valid and shaped for Tally import, but ledger names must match the target Tally company. | Medium | Do one accountant-supervised import test. |
| Offline POS | PWA is installable and has offline fallback, but offline billing is intentionally not enabled. | Low | Avoids unsafe offline stock/accounting conflicts. |
| Distributed rate limiting | Login uses session throttle; production multi-worker deployments should use Redis or gateway rate limits. | Medium | API token routes already have basic controls. |
