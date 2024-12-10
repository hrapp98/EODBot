from extensions import db
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSON

class EODReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Project data
    short_term_projects = db.Column(JSON)
    long_term_projects = db.Column(JSON)
    
    # Progress tracking
    short_term_progress = db.Column(db.Integer)  # Percentage
    long_term_progress = db.Column(db.Integer)  # Percentage
    
    # Additional fields
    accomplishments = db.Column(db.Text)
    blockers = db.Column(db.Text)
    next_day_goals = db.Column(db.Text)
    client_interactions = db.Column(db.Text)
    
    # Metadata
    submitted = db.Column(db.Boolean, default=True)
    reminder_sent = db.Column(db.Boolean, default=False)
    
    @classmethod
    def create_from_text(cls, user_id, text):
        """Parse EOD report text and create report object"""
        # Simple parsing logic - can be enhanced
        lines = text.split('\n')
        data = {
            'short_term_projects': {},
            'long_term_projects': {},
            'accomplishments': '',
            'blockers': '',
            'next_day_goals': '',
            'client_interactions': ''
        }
        
        current_section = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.lower().startswith('short-term:'):
                current_section = 'short_term_projects'
            elif line.lower().startswith('long-term:'):
                current_section = 'long_term_projects'
            elif line.lower().startswith('accomplishments:'):
                current_section = 'accomplishments'
            elif line.lower().startswith('blockers:'):
                current_section = 'blockers'
            elif line.lower().startswith('goals:'):
                current_section = 'next_day_goals'
            elif line.lower().startswith('client:'):
                current_section = 'client_interactions'
            elif current_section:
                if isinstance(data[current_section], dict):
                    data[current_section][len(data[current_section])] = line
                else:
                    data[current_section] = line
        
        return cls(
            user_id=user_id,
            short_term_projects=data['short_term_projects'],
            long_term_projects=data['long_term_projects'],
            accomplishments=data['accomplishments'],
            blockers=data['blockers'],
            next_day_goals=data['next_day_goals'],
            client_interactions=data['client_interactions']
        )
    
    def to_dict(self):
        """Convert report to dictionary format"""
        return {
            'user_id': self.user_id,
            'short_term_projects': self.short_term_projects,
            'long_term_projects': self.long_term_projects,
            'accomplishments': self.accomplishments,
            'blockers': self.blockers,
            'next_day_goals': self.next_day_goals,
            'client_interactions': self.client_interactions,
            'created_at': self.created_at.isoformat()
        }

class SubmissionTracker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    submitted = db.Column(db.Boolean, default=False)
    reminder_count = db.Column(db.Integer, default=0)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='unique_user_date'),
    )
