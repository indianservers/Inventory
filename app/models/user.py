from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    is_system = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    users = db.relationship('User', backref='role', lazy='dynamic')
    permissions = db.relationship('RolePermission', backref='role', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Role {self.name}>'

    def has_permission(self, module, action):
        perm = Permission.query.filter_by(module=module, action=action).first()
        if not perm:
            return False
        return RolePermission.query.filter_by(role_id=self.id, permission_id=perm.id, granted=True).first() is not None


class Permission(db.Model):
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    module = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    __table_args__ = (db.UniqueConstraint('module', 'action', name='uq_module_action'),)

    def __repr__(self):
        return f'<Permission {self.module}:{self.action}>'


class RolePermission(db.Model):
    __tablename__ = 'role_permissions'
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id', ondelete='CASCADE'), nullable=False)
    granted = db.Column(db.Boolean, default=True)
    __table_args__ = (db.UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    phone = db.Column(db.String(20))
    profile_image = db.Column(db.String(255))
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, module, action):
        if self.role and self.role.name == 'Super Admin':
            return True
        if self.role:
            return self.role.has_permission(module, action)
        return False

    def __repr__(self):
        return f'<User {self.email}>'
