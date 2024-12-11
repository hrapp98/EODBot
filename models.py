from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EODReport:
    def __init__(self, user_id, short_term_projects=None, long_term_projects=None,
                 accomplishments=None, blockers=None, next_day_goals=None,
                 client_interactions=None):
        self.id = None  # Will be set by Firebase
        self.user_id = user_id
        self.created_at = datetime.utcnow()
        self.short_term_projects = short_term_projects or {}
        self.long_term_projects = long_term_projects or {}
        self.accomplishments = accomplishments
        self.blockers = blockers
        self.next_day_goals = next_day_goals
        self.client_interactions = client_interactions
        self.submitted = True
        self.reminder_sent = False

    @classmethod
    def create_from_text(cls, user_id, text):
        """Parse EOD report text and create report object"""
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
        """Convert report to dictionary format for Firebase"""
        return {
            'user_id': self.user_id,
            'short_term_projects': self.short_term_projects,
            'long_term_projects': self.long_term_projects,
            'accomplishments': self.accomplishments,
            'blockers': self.blockers,
            'next_day_goals': self.next_day_goals,
            'client_interactions': self.client_interactions,
            'created_at': self.created_at.isoformat(),
            'submitted': self.submitted,
            'reminder_sent': self.reminder_sent
        }

class SubmissionTracker:
    def __init__(self, user_id, date, submitted=False, reminder_count=0):
        self.user_id = user_id
        self.date = date
        self.submitted = submitted
        self.reminder_count = reminder_count

    def to_dict(self):
        """Convert tracker to dictionary format for Firebase"""
        return {
            'user_id': self.user_id,
            'date': self.date.isoformat(),
            'submitted': self.submitted,
            'reminder_count': self.reminder_count
        }

class EODTracker:
    def __init__(self, user_id, status, timestamp):
        self.user_id = user_id
        self.status = status  # 'submitted', 'skipped', or 'pending'
        self.timestamp = timestamp

    def to_dict(self):
        """Convert EOD tracker to dictionary format for Firebase"""
        return {
            'user_id': self.user_id,
            'status': self.status,
            'timestamp': self.timestamp
        }
