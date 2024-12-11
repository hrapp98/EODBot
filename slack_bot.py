from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import Config
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SlackBot:
    def __init__(self):
        self.client = WebClient(token=Config.SLACK_BOT_OAUTH_TOKEN)
    
    def send_eod_prompt(self, user_id):
        """Send EOD report prompt to user"""
        try:
            logger.debug(f"Sending EOD prompt to user {user_id}")
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📝 End of Day Report"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Please provide your EOD report with the following information:"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Format your response as follows:*\n\n"
                                ">*Short-term:*\n>[Project updates & progress]\n\n"
                                ">*Long-term:*\n>[Strategic project updates]\n\n"
                                ">*Accomplishments:*\n>[Key wins today]\n\n"
                                ">*Blockers:*\n>[Any challenges]\n\n"
                                ">*Goals:*\n>[Tomorrow's priorities]\n\n"
                                ">*Client:*\n>[Important interactions]"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💡 *Tip:* Copy the template above and replace the bracketed text with your updates"
                        }
                    ]
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Skip Today"
                            },
                            "style": "danger",
                            "value": "skip_eod",
                            "action_id": "skip_eod"
                        }
                    ]
                }
            ]
            
            logger.debug(f"Attempting to send message to Slack API - Channel: {user_id}")
            response = self.client.chat_postMessage(
                channel=user_id,
                blocks=blocks,
                text="Time for your EOD report!"
            )
            logger.debug(f"Slack API Response: {response}")
            logger.info(f"EOD prompt sent successfully to {user_id}")
            
        except SlackApiError as e:
            logger.error(f"Error sending message: {e.response['error']}")
    
    def send_reminder(self, user_id):
        """Send reminder for missing EOD report"""
        try:
            self.client.chat_postMessage(
                channel=user_id,
                text="Reminder: You haven't submitted your EOD report yet!"
            )
        except SlackApiError as e:
            logger.error(f"Error sending reminder: {e.response['error']}")
    
    def post_report_to_channel(self, report_data):
        """Post EOD report to designated channel"""
        try:
            text = self._format_report_for_channel(report_data)
            self.client.chat_postMessage(
                channel=Config.SLACK_EOD_CHANNEL,
                text=text,
                unfurl_links=False
            )
        except SlackApiError as e:
            logger.error(f"Error posting to channel: {e.response['error']}")
    
    def send_error_message(self, user_id):
        """Send error message to user"""
        self.send_message(user_id, "Sorry, there was an error processing your EOD report. Please try again.")

    def send_message(self, user_id, text):
        """Send a simple message to a user"""
        try:
            self.client.chat_postMessage(
                channel=user_id,
                text=text
            )
        except SlackApiError as e:
            logger.error(f"Error sending message: {e.response['error']}")
            
    def send_status_update(self, user_id):
        """Send status update to user"""
        try:
            from models import EODReport
            today_report = EODReport.query.filter_by(
                user_id=user_id,
                created_at=datetime.utcnow().date()
            ).first()
            
            status = "You have submitted your EOD report for today." if today_report else "You haven't submitted your EOD report for today yet."
            self.send_message(user_id, status)
        except Exception as e:
            logger.error(f"Error sending status update: {str(e)}")
            self.send_message(user_id, "Sorry, I couldn't fetch your status right now.")
    
    def send_help_message(self, user_id):
        """Send help message with bot instructions"""
        try:
            help_text = """
*EOD Bot Help*
• Submit your EOD report by typing "eod report"
• Format your submission as shown in the prompt
• Reports are due by 5 PM daily
• Use "status" to check your submission status
            """
            self.client.chat_postMessage(
                channel=user_id,
                text=help_text
            )
        except SlackApiError as e:
            logger.error(f"Error sending help message: {e.response['error']}")
    
    def _format_report_for_channel(self, report_data):
        """Format EOD report for Slack channel display"""
        return f"""
*EOD Report from <@{report_data['user_id']}>*
*Short-term Projects:*
{self._format_dict_items(report_data['short_term_projects'])}

*Long-term Projects:*
{self._format_dict_items(report_data['long_term_projects'])}

*Key Accomplishments:*
{report_data['accomplishments']}

*Blockers/Challenges:*
{report_data['blockers']}

*Tomorrow's Goals:*
{report_data['next_day_goals']}

*Client Interactions:*
{report_data['client_interactions']}
        """.strip()
    
    def _format_dict_items(self, items):
        if not items:
            return "None reported"
        return "\n".join([f"• {item}" for item in items.values()])
