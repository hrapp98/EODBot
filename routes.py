from flask import render_template
from datetime import datetime, timedelta
from app import app, db
from models import Contractor, EODReport, SubmissionTracker

@app.route('/')
def dashboard():
    """Display the main dashboard"""
    # Get today's submissions
    today = datetime.utcnow().date()
    today_submissions = SubmissionTracker.query.filter_by(date=today).all()
    
    # Get missing reports from last 3 days
    three_days_ago = today - timedelta(days=3)
    missing_reports = (
        db.session.query(
            SubmissionTracker,
            db.func.count(SubmissionTracker.id).label('missing_days')
        )
        .filter(
            SubmissionTracker.date >= three_days_ago,
            SubmissionTracker.submitted == False
        )
        .group_by(SubmissionTracker.contractor_id)
        .having(db.func.count(SubmissionTracker.id) > 0)
        .all()
    )
    
    # Get recent reports
    recent_reports = EODReport.query.order_by(
        EODReport.submitted_at.desc()
    ).limit(10).all()
    
    return render_template('dashboard.html',
                         today_submissions=today_submissions,
                         missing_reports=missing_reports,
                         recent_reports=recent_reports)

@app.route('/report/<int:report_id>')
def view_report(report_id):
    """View detailed EOD report"""
    report = EODReport.query.get_or_404(report_id)
    return render_template('report_detail.html', report=report)
