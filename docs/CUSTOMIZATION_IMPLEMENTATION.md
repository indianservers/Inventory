# Customization Implementation

| Feature | Status | Backend File | Frontend File | Database Tables | How to Test | Notes |
|---|---|---|---|---|---|---|
| Custom Fields | Implemented | `app/routes/integration_routes.py` | `app/templates/settings/foundation_list.html` | `custom_fields`, `custom_field_values` | Open `/settings/custom-fields`, add a field for products or customers. | Existing feature retained and linked from the new studio. |
| Custom Views | Implemented | `app/routes/integration_routes.py` | `app/templates/settings/foundation_list.html` | `custom_views` | Open `/settings/custom-views`, save filters and columns JSON. | Existing feature retained and linked from the new studio. |
| Custom Modules | Implemented | `app/routes/integration_routes.py` | `app/templates/settings/custom_modules.html`, `app/templates/settings/custom_module_detail.html` | `custom_modules`, `custom_module_fields`, `custom_module_records` | Open `/settings/custom-modules`, create a module, add fields, then add records. | Supports lightweight user-defined modules such as appointments, service jobs, assets, rentals, or warranties. |
| Customization Studio | Implemented | `app/routes/integration_routes.py` | `app/templates/settings/customization.html` | Uses all customization tables | Open `/settings/customization`. | Gives one place to manage fields, saved views, and modules. |

## Notes

- Custom modules are intentionally generic and original to Vyapara ERP. They are not a clone of any third-party UI.
- Each module gets a required `Title` field by default.
- Dropdown field options accept comma-separated or line-separated values.
- Record data is stored as JSON so new fields do not require new migrations.
- Deactivation is supported for modules; hard deletes are avoided.
