from datetime import datetime
from decimal import Decimal
from app.extensions import db


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    description = db.Column(db.Text)
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    children = db.relationship('Category', backref=db.backref('parent', remote_side=[id]))
    products = db.relationship('Product', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<Category {self.name}>'


class Brand(db.Model):
    __tablename__ = 'brands'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    products = db.relationship('Product', backref='brand', lazy='dynamic')

    def __repr__(self):
        return f'<Brand {self.name}>'


class Unit(db.Model):
    __tablename__ = 'units'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    short_name = db.Column(db.String(20), nullable=False)
    decimal_allowed = db.Column(db.Boolean, default=False)
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    products = db.relationship('Product', backref='unit', lazy='dynamic')

    def __repr__(self):
        return f'<Unit {self.name}>'


class Warehouse(db.Model):
    __tablename__ = 'warehouses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.Text)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(150))
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Warehouse {self.name}>'


class Tax(db.Model):
    __tablename__ = 'taxes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    tax_type = db.Column(db.String(20), default='GST')  # GST, VAT, Sales Tax, None
    is_inclusive = db.Column(db.Boolean, default=False)
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    products = db.relationship('Product', backref='tax', lazy='dynamic')

    def __repr__(self):
        return f'<Tax {self.name} {self.rate}%>'


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    barcode = db.Column(db.String(100))
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=True)
    tax_id = db.Column(db.Integer, db.ForeignKey('taxes.id'), nullable=True)
    hsn_code = db.Column(db.String(20))
    purchase_price = db.Column(db.Numeric(12, 2), default=0)
    sales_price = db.Column(db.Numeric(12, 2), default=0)
    mrp = db.Column(db.Numeric(12, 2), default=0)
    current_stock = db.Column(db.Numeric(12, 3), default=0)
    average_cost = db.Column(db.Numeric(12, 4), default=0)
    opening_stock = db.Column(db.Numeric(12, 3), default=0)
    min_stock = db.Column(db.Numeric(12, 3), default=0)
    max_stock = db.Column(db.Numeric(12, 3), default=0)
    reorder_level = db.Column(db.Numeric(12, 3), default=0)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    rack_bin = db.Column(db.String(50))
    batch_tracking = db.Column(db.Boolean, default=False)
    serial_tracking = db.Column(db.Boolean, default=False)
    expiry_tracking = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    images = db.relationship('ProductImage', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    warehouse = db.relationship('Warehouse', backref='products', foreign_keys=[warehouse_id])

    @property
    def stock_value(self):
        return float(self.current_stock or 0) * float(self.average_cost or 0)

    @property
    def is_low_stock(self):
        return float(self.current_stock or 0) <= float(self.min_stock or 0) and float(self.min_stock or 0) > 0

    def __repr__(self):
        return f'<Product {self.sku} {self.name}>'


class ProductImage(db.Model):
    __tablename__ = 'product_images'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProductBatch(db.Model):
    __tablename__ = 'product_batches'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    batch_no = db.Column(db.String(100), nullable=False)
    serial_no = db.Column(db.String(100))
    manufacture_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    quantity = db.Column(db.Numeric(12, 3), default=0)
    cost_rate = db.Column(db.Numeric(12, 4), default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product', backref='batches')
    warehouse = db.relationship('Warehouse', backref='product_batches')

    @property
    def is_expired(self):
        from datetime import date

        return bool(self.expiry_date and self.expiry_date < date.today())


class PriceList(db.Model):
    __tablename__ = 'price_lists'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    discount_pct = db.Column(db.Numeric(5, 2), default=0)
    is_default = db.Column(db.Boolean, default=False)
    currency = db.Column(db.String(10), default='INR')
    valid_from = db.Column(db.Date)
    valid_to = db.Column(db.Date)
    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('PriceListItem', backref='price_list', lazy='dynamic', cascade='all, delete-orphan')


class PriceListItem(db.Model):
    __tablename__ = 'price_list_items'
    id = db.Column(db.Integer, primary_key=True)
    price_list_id = db.Column(db.Integer, db.ForeignKey('price_lists.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    sales_price = db.Column(db.Numeric(12, 2), nullable=False)
    min_qty = db.Column(db.Numeric(12, 3), default=1)
    product = db.relationship('Product', backref='price_list_items')
    __table_args__ = (db.UniqueConstraint('price_list_id', 'product_id', 'min_qty', name='uq_price_list_item'),)


class BillOfMaterials(db.Model):
    __tablename__ = 'bill_of_materials'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    yield_qty = db.Column(db.Numeric(12, 3), default=1)
    version = db.Column(db.String(20), default='1')
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product', backref='boms', foreign_keys=[product_id])
    items = db.relationship('BOMItem', backref='bom', lazy='dynamic', cascade='all, delete-orphan')


class BOMItem(db.Model):
    __tablename__ = 'bom_items'
    id = db.Column(db.Integer, primary_key=True)
    bom_id = db.Column(db.Integer, db.ForeignKey('bill_of_materials.id', ondelete='CASCADE'), nullable=False)
    component_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=True)
    waste_pct = db.Column(db.Numeric(5, 2), default=0)
    component = db.relationship('Product', backref='bom_component_lines', foreign_keys=[component_id])
    unit = db.relationship('Unit', backref='bom_items')


class ManufacturingOrder(db.Model):
    __tablename__ = 'manufacturing_orders'
    id = db.Column(db.Integer, primary_key=True)
    mo_no = db.Column(db.String(30), unique=True, nullable=False)
    bom_id = db.Column(db.Integer, db.ForeignKey('bill_of_materials.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    planned_qty = db.Column(db.Numeric(12, 3), nullable=False)
    produced_qty = db.Column(db.Numeric(12, 3), default=0)
    planned_date = db.Column(db.Date)
    completed_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='Draft')
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bom = db.relationship('BillOfMaterials', backref='manufacturing_orders')
    warehouse = db.relationship('Warehouse', backref='manufacturing_orders')
