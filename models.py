from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Contact(db.Model):
    __tablename__ = 'contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    is_online = db.Column(db.Boolean, default=False)
    last_online_at = db.Column(db.DateTime)
    last_offline_at = db.Column(db.DateTime)
    total_online_seconds = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    online_statuses = db.relationship('OnlineStatus', backref='contact', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'is_online': self.is_online,
            'last_online_at': self.last_online_at.isoformat() if self.last_online_at else None,
            'total_online_seconds': self.total_online_seconds,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class OnlineStatus(db.Model):
    __tablename__ = 'online_statuses'
    
    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id'), nullable=False)
    online_at = db.Column(db.DateTime, nullable=False)
    offline_at = db.Column(db.DateTime, nullable=False)
    duration_seconds = db.Column(db.Integer, nullable=False)