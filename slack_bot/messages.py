def create_eod_prompt():
    """Create EOD report prompt message"""
    return {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🌟 Time for your End of Day Report! Please provide the following information:"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Short-term Project Work:*\n• What did you work on today?\n• Progress percentage?"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Long-term Project Work:*\n• Any progress on long-term initiatives?\n• Progress percentage?"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Additional Information:*\n• Key accomplishments?\n• Any blockers?\n• Tomorrow's goals?\n• Client interactions?"
                }
            }
        ]
    }

def format_report_message(report):
    """Format EOD report for Slack display"""
    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"EOD Report - {report.contractor.name}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Short-term Work*\n{report.short_term_work}\nProgress: {report.short_term_progress}%"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Long-term Work*\n{report.long_term_work}\nProgress: {report.long_term_progress}%"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Accomplishments*\n{report.accomplishments}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Blockers*\n{report.blockers}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Tomorrow's Goals*\n{report.next_day_goals}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Client Interactions*\n{report.client_interactions}"
                }
            }
        ]
    }
