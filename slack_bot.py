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
            logger.info(f"Attempting to send EOD prompt to user {user_id}")
            # First verify if we can access the user's DM channel
            try:
                response = self.client.conversations_open(users=[user_id])
                channel_id = response['channel']['id']
            except SlackApiError as e:
                logger.error(f"Error opening DM channel: {e.response['error']}")
                return
                
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Time for your EOD report! Please provide the following information:"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Format your response as follows:*\n"
                                "Short-term:\n[Your updates]\n"
                                "Long-term:\n[Your updates]\n"
                                "Accomplishments:\n[Your updates]\n"
                                "Blockers:\n[Any blockers]\n"
                                "Goals:\n[Tomorrow's goals]\n"
                                "Client:\n[Any client interactions]"
                    }
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
                            "value": "skip_eod"
                        }
                    ]
                }
            ]
            
            self.client.chat_postMessage(
                channel=user_id,
                blocks=blocks,
                text="Time for your EOD report!"
            )
            
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

    def send_message(self, user_id, text, thread_ts=None):
        """Send a simple message to a user"""
        try:
            message_params = {
                'channel': user_id,
                'text': text
            }
            if thread_ts:
                message_params['thread_ts'] = thread_ts
                
            self.client.chat_postMessage(**message_params)
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
