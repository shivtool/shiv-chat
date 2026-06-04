from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile_pic = db.Column(db.String(200), default='default.png')
    online_status = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    
class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message_type = db.Column(db.String(20), default='text')  # text, image, video, audio, file
    # FIX: content nullable=True — file messages may have empty content
    content = db.Column(db.Text, nullable=True, default='')
    file_url = db.Column(db.String(500), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
class CallHistory(db.Model):
    __tablename__ = 'call_history'
    
    id = db.Column(db.Integer, primary_key=True)
    caller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    call_type = db.Column(db.String(10), nullable=False)  # audio, video
    duration = db.Column(db.Integer, default=0)  # in seconds
    call_status = db.Column(db.String(20), default='missed')  # answered, missed, rejected
    # FIX: start_time nullable so missed calls don't crash strftime
    start_time = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    
    caller = db.relationship('User', foreign_keys=[caller_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])
    
class SharedFile(db.Model):
    __tablename__ = 'shared_files'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
