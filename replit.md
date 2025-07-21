# EOD Reporting System

## Overview

This is a comprehensive End-of-Day (EOD) reporting system built as a Slack bot application. The system automates the collection of daily work reports from contractors, stores them in Firebase and Google Sheets, and generates weekly summaries using OpenAI's API. It includes a web dashboard for monitoring submissions and team management.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Framework**: Flask web application
- **Language**: Python 3.x
- **Database**: Firebase Firestore (NoSQL document database)
- **External Storage**: Google Sheets API for data export/backup
- **Scheduler**: APScheduler for background tasks and automated reminders
- **AI Integration**: OpenAI GPT-4 for weekly report summarization

### Frontend Architecture
- **Templates**: Jinja2 HTML templates with Bootstrap 5 for responsive UI
- **Styling**: Custom CSS with dark theme support
- **JavaScript**: Vanilla JS for dashboard interactions and data visualization
- **Charts**: Chart.js for data visualization

### Communication Layer
- **Slack Integration**: Slack SDK for Python (WebClient)
- **Modal Interface**: Slack Block Kit for interactive forms
- **Real-time Updates**: Slack Events API for handling user interactions

## Key Components

### Core Application Files
- **app.py**: Main Flask application with route handlers
- **config.py**: Configuration management with environment variables
- **models.py**: Data models for EOD reports and submission tracking
- **scheduler.py**: Background job scheduling for automated tasks

### Integration Clients
- **slack_bot.py**: Slack API integration and modal management
- **firebase_client.py**: Firebase Firestore database operations
- **sheets_client.py**: Google Sheets API integration for data export
- **openai_client.py**: OpenAI API client for report summarization

### Web Dashboard
- **templates/**: HTML templates for web interface
- **static/**: CSS and JavaScript assets
- **Web Routes**: Dashboard, team management, report viewing, and statistics

## Data Flow

### Daily EOD Process
1. **Scheduled Prompt**: APScheduler triggers EOD prompts at 4:00 PM ET
2. **User Interaction**: Users receive Slack modal with structured form fields
3. **Data Capture**: Reports include short-term/long-term projects, accomplishments, blockers, and goals
4. **Storage**: Data stored in Firebase Firestore with automatic timestamps
5. **Sheet Export**: Reports automatically exported to Google Sheets for backup
6. **Channel Posting**: Formatted reports posted to designated Slack channels

### Reminder System
1. **Automated Reminders**: System checks for missing submissions at 6:00 PM ET
2. **Escalation**: Multiple reminder levels with management notifications
3. **Tracking**: Persistent tracking of submission patterns and missed reports

### Weekly Summarization
1. **Data Aggregation**: Weekly reports collected from Firebase
2. **AI Processing**: OpenAI GPT-4 analyzes and summarizes contractor progress
3. **Distribution**: Summaries posted to Slack and appended to Google Sheets

## External Dependencies

### Required APIs and Services
- **Slack API**: Bot token, signing secret, and webhook configuration
- **Firebase**: Service account credentials with Firestore access
- **Google Sheets API**: Service account with spreadsheet permissions
- **OpenAI API**: API key for GPT-4 access

### Environment Variables
- `SLACK_BOT_OAUTH_TOKEN`: Slack bot authentication token
- `SLACK_SIGNING_SECRET`: Slack webhook verification
- `FIREBASE_PROJECT_ID`, `FIREBASE_PRIVATE_KEY`, `FIREBASE_CLIENT_EMAIL`: Firebase configuration
- `GOOGLE_SERVICE_ACCOUNT`: Google Sheets service account JSON
- `OPENAI_API_KEY`: OpenAI API access token

### Third-Party Libraries
- **Flask**: Web framework with templating
- **slack-sdk**: Official Slack Python SDK
- **firebase-admin**: Firebase Admin SDK
- **google-api-python-client**: Google Sheets API client
- **openai**: OpenAI Python client
- **APScheduler**: Advanced Python Scheduler

## Deployment Strategy

### Development Environment
- **Platform**: Replit-compatible with secrets management
- **Configuration**: Environment variables loaded from .env or Replit secrets
- **Database**: Firebase Firestore (cloud-hosted)
- **Scheduler**: Background scheduler runs within Flask application

### Production Considerations
- **WSGI Server**: Recommendation to use production WSGI server instead of Flask dev server
- **Error Handling**: Comprehensive logging and graceful error recovery
- **Rate Limiting**: Built-in rate limiting for OpenAI API calls
- **Scalability**: Firebase provides automatic scaling for database operations

### Security Features
- **Slack Verification**: Request signature verification for webhooks
- **Service Account Auth**: Secure authentication for external APIs
- **Secret Management**: Environment variables for sensitive configuration
- **Input Validation**: Form validation and sanitization for user inputs

### Monitoring and Maintenance
- **Logging**: Structured logging with configurable levels
- **Health Checks**: Web dashboard provides system status monitoring
- **Data Backup**: Automatic Google Sheets export for data redundancy
- **Holiday Handling**: Built-in holiday calendar to skip non-working days