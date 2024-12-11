from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import Config
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SlackBot:
    def __init__(self):
        self.client = WebClient(token=Config.SLACK_BOT_OAUTH_TOKEN)
    
    def send_eod_prompt(self, trigger_id):
        """Open EOD report modal for user"""
        try:
            logger.info(f"Opening EOD modal with trigger_id: {trigger_id}")
            
            view = {
                "type": "modal",
                "callback_id": "eod_report_modal",
                "title": {
                    "type": "plain_text",
                    "text": "EOD Report"
                },
                "submit": {
                    "type": "plain_text",
                    "text": "Submit"
                },
                "close": {
                    "type": "plain_text",
                    "text": "Cancel"
                },
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "short_term_block",
                        "label": {
                            "type": "plain_text",
                            "text": "Short-term Projects"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "short_term_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "What did you work on today?"
                            }
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "long_term_block",
                        "label": {
                            "type": "plain_text",
                            "text": "Long-term Projects"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "long_term_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Any progress on long-term initiatives?"
                            }
                        },
                        "optional": True
                    },
                    
                    {
                        "type": "input",
                        "block_id": "blockers_block",
                        "label": {
                            "type": "plain_text",
                            "text": "Blockers/Challenges"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "blockers_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Any blockers or challenges that you experienced?"
                            }
                        },
                        "optional": True
                    },
                    {
                        "type": "input",
                        "block_id": "goals_block",
                        "label": {
                            "type": "plain_text",
                            "text": "Tomorrow's Goals"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "goals_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "What are your goals for tomorrow?"
                            }
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "tools_block",
                        "label": {
                            "type": "plain_text",
                            "text": "Software Tools Used Today"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "tools_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "What software tools did you use today?"
                            }
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "help_block",
                        "label": {
                            "type": "plain_text",
                            "text": "Need Help?"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "help_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Is there anything we can help you with?"
                            }
                        }
                    }
                ]
            }
            
            # Open the modal
            self.client.views_open(
                trigger_id=trigger_id,
                view=view
            )
            logger.info("EOD modal opened successfully")
            
        except SlackApiError as e:
            logger.error(f"Error opening modal: {e.response['error']}")
    
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
