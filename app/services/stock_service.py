from datetime import date
from decimal import Decimal

from flask import abort

from app.extensions import db
from app.models import CompanySetting, InventoryLedger, Product
from app.utils.helpers import money, qty


def _negative_stock_allowed():
    setting = CompanySetting.query.first()
    return bool(setting and setting.enable_negative_stock)


def add_inventory_entry(product, warehouse_id, movement_type, reference_type, reference_id, reference_no, qty_in=0, qty_out=0, rate=0, notes=None):
    qty_in, qty_out, rate = qty(qty_in), qty(qty_out), Decimal(str(rate or 0))
    product.current_stock = qty(product.current_stock) + qty_in - qty_out
    if product.current_stock < 0 and not _negative_stock_allowed():
        abort(400, f"Insufficient stock for {product.name}")

    entry = InventoryLedger(
        date=date.today(),
        product_id=product.id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        reference_type=reference_type,
        reference_id=reference_id,
        reference_no=reference_no,
        qty_in=qty_in,
        qty_out=qty_out,
        balance_qty=product.current_stock,
        rate=rate,
        value=money((qty_in or qty_out) * rate),
        notes=notes,
    )
    db.session.add(entry)
    return entry


def apply_purchase_item(product_id, warehouse_id, quantity, rate, purchase_id, purchase_no):
    product = Product.query.get_or_404(product_id)
    quantity, rate = qty(quantity), Decimal(str(rate or 0))
    old_qty = qty(product.current_stock)
    old_value = old_qty * Decimal(str(product.average_cost or 0))
    new_value = old_value + quantity * rate
    new_qty = old_qty + quantity
    product.average_cost = money(new_value / new_qty) if new_qty else money(rate)
    product.purchase_price = money(rate)
    add_inventory_entry(product, warehouse_id, "Purchase", "Purchase", purchase_id, purchase_no, qty_in=quantity, rate=rate)
    return product


def apply_sale_item(product_id, warehouse_id, quantity, sale_id, invoice_no):
    product = Product.query.get_or_404(product_id)
    quantity = qty(quantity)
    cost = Decimal(str(product.average_cost or product.purchase_price or 0))
    add_inventory_entry(product, warehouse_id, "Sale", "Sale", sale_id, invoice_no, qty_out=quantity, rate=cost)
    return cost


def apply_stock_adjustment(product_id, warehouse_id, qty_in, qty_out, rate, adjustment_id, adjustment_no, reason):
    product = Product.query.get_or_404(product_id)
    add_inventory_entry(product, warehouse_id, "Adjustment In" if qty(qty_in) else "Adjustment Out", "StockAdjustment", adjustment_id, adjustment_no, qty_in=qty_in, qty_out=qty_out, rate=rate, notes=reason)


def apply_stock_transfer(product_id, from_warehouse_id, to_warehouse_id, quantity, rate, transfer_id, transfer_no, notes=None):
    product = Product.query.get_or_404(product_id)
    quantity = qty(quantity)
    rate = Decimal(str(rate or product.average_cost or product.purchase_price or 0))
    add_inventory_entry(product, from_warehouse_id, "Transfer Out", "StockTransfer", transfer_id, transfer_no, qty_out=quantity, rate=rate, notes=notes)
    add_inventory_entry(product, to_warehouse_id, "Transfer In", "StockTransfer", transfer_id, transfer_no, qty_in=quantity, rate=rate, notes=notes)


def apply_sales_return_item(product_id, warehouse_id, quantity, rate, return_id, return_no):
    product = Product.query.get_or_404(product_id)
    add_inventory_entry(product, warehouse_id, "Sales Return", "SalesReturn", return_id, return_no, qty_in=quantity, rate=rate)


def apply_purchase_return_item(product_id, warehouse_id, quantity, rate, return_id, return_no):
    product = Product.query.get_or_404(product_id)
    add_inventory_entry(product, warehouse_id, "Purchase Return", "PurchaseReturn", return_id, return_no, qty_out=quantity, rate=rate)
