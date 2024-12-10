from datetime import datetime
from app import db

class Contractor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slack_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    timezone = db.Column(db.String(50), default='UTC')
    reports = db.relationship('EODReport', backref='contractor', lazy=True)

class EODReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractor.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Project details
    short_term_work = db.Column(db.Text)
    long_term_work = db.Column(db.Text)
    short_term_progress = db.Column(db.Integer)  # Percentage
    long_term_progress = db.Column(db.Integer)  # Percentage
    
    # Additional fields
    accomplishments = db.Column(db.Text)
    blockers = db.Column(db.Text)
    next_day_goals = db.Column(db.Text)
    client_interactions = db.Column(db.Text)
    
    # Tracking
    reminder_count = db.Column(db.Integer, default=0)
    is_completed = db.Column(db.Boolean, default=True)

class SubmissionTracker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractor.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    submitted = db.Column(db.Boolean, default=False)
    last_reminder = db.Column(db.DateTime)
    
    __table_args__ = (
        db.UniqueConstraint('contractor_id', 'date', name='unique_daily_submission'),
    )
