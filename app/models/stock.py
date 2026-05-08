from datetime import datetime
from app.extensions import db


class InventoryLedger(db.Model):
    __tablename__ = 'inventory_ledger'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    movement_type = db.Column(db.String(30), nullable=False)
    # Types: Opening Stock, Purchase, Purchase Return, Sale, Sales Return,
    # Adjustment In, Adjustment Out, Transfer In, Transfer Out, Damage, Expiry
    reference_type = db.Column(db.String(30))
    reference_id = db.Column(db.Integer)
    reference_no = db.Column(db.String(30))
    qty_in = db.Column(db.Numeric(12, 3), default=0)
    qty_out = db.Column(db.Numeric(12, 3), default=0)
    balance_qty = db.Column(db.Numeric(12, 3), default=0)
    rate = db.Column(db.Numeric(12, 4), default=0)
    value = db.Column(db.Numeric(12, 2), default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product', backref='inventory_ledger')
    warehouse = db.relationship('Warehouse', backref='inventory_ledger')

    def __repr__(self):
        return f'<InventoryLedger {self.product_id} {self.movement_type}>'


class StockAdjustment(db.Model):
    __tablename__ = 'stock_adjustments'
    id = db.Column(db.Integer, primary_key=True)
    adjustment_no = db.Column(db.String(30), unique=True, nullable=False)
    adjustment_date = db.Column(db.Date, nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    reason = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('StockAdjustmentItem', backref='adjustment', lazy='dynamic', cascade='all, delete-orphan')
    warehouse = db.relationship('Warehouse', backref='stock_adjustments')

    def __repr__(self):
        return f'<StockAdjustment {self.adjustment_no}>'


class StockAdjustmentItem(db.Model):
    __tablename__ = 'stock_adjustment_items'
    id = db.Column(db.Integer, primary_key=True)
    adjustment_id = db.Column(db.Integer, db.ForeignKey('stock_adjustments.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    qty_in = db.Column(db.Numeric(12, 3), default=0)
    qty_out = db.Column(db.Numeric(12, 3), default=0)
    rate = db.Column(db.Numeric(12, 4), default=0)
    notes = db.Column(db.String(255))
    product = db.relationship('Product', backref='adjustment_items')

    def __repr__(self):
        return f'<StockAdjustmentItem {self.product_id}>'


class StockTransfer(db.Model):
    __tablename__ = 'stock_transfers'
    id = db.Column(db.Integer, primary_key=True)
    transfer_no = db.Column(db.String(30), unique=True, nullable=False)
    transfer_date = db.Column(db.Date, nullable=False)
    from_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    to_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='Completed')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('StockTransferItem', backref='transfer', lazy='dynamic', cascade='all, delete-orphan')
    from_warehouse = db.relationship('Warehouse', foreign_keys=[from_warehouse_id], backref='transfers_out')
    to_warehouse = db.relationship('Warehouse', foreign_keys=[to_warehouse_id], backref='transfers_in')

    def __repr__(self):
        return f'<StockTransfer {self.transfer_no}>'


class StockTransferItem(db.Model):
    __tablename__ = 'stock_transfer_items'
    id = db.Column(db.Integer, primary_key=True)
    transfer_id = db.Column(db.Integer, db.ForeignKey('stock_transfers.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), default=0)
    product = db.relationship('Product', backref='transfer_items')
