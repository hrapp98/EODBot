import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_apscheduler import APScheduler

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
scheduler = APScheduler()

# Create the app
app = Flask(__name__)

# Setup configuration
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Configure scheduler
app.config['SCHEDULER_API_ENABLED'] = True
app.config['SCHEDULER_TIMEZONE'] = "UTC"

# Initialize extensions
db.init_app(app)
scheduler.init_app(app)

with app.app_context():
    # Import routes and models
    from routes import *  # noqa: F403
    from models import *  # noqa: F403
    
    # Create database tables
    db.create_all()
    
    # Start scheduler
    scheduler.start()

# Import and register blueprints
from slack_bot.handlers import slack_bp
app.register_blueprint(slack_bp)
