from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import Config
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

class SlackBot:
    def __init__(self):
        self.client = WebClient(token=Config.SLACK_BOT_OAUTH_TOKEN)
    
    def _ensure_in_channels(self):
        """Ensure bot is in required channels - kept for documentation"""
        # Example of how to join channels if needed in the future:
        """
        try:
            channel_name = Config.SLACK_WEEKLY_SUMMARY_CHANNEL.lstrip('#')
            logger.debug(f"Looking for channel: {channel_name}")
            
            # First get the channel ID
            try:
                response = self.client.conversations_list(types="public_channel,private_channel")
                channel_id = None
                
                for channel in response['channels']:
                    if channel['name'] == channel_name:
                        channel_id = channel['id']
                        logger.debug(f"Found channel ID: {channel_id} for channel: {channel_name}")
                        break
                
                if not channel_id:
                    logger.error(f"Channel '{channel_name}' not found in workspace")
                    return
                
                # Try to join the channel
                try:
                    response = self.client.conversations_join(channel=channel_id)
                    if response['ok']:
                        logger.info(f"Successfully joined channel {channel_name}")
                except SlackApiError as e:
                    if e.response['error'] == 'is_archived':
                        logger.error(f"Channel {channel_name} is archived")
                    elif e.response['error'] == 'already_in_channel':
                        logger.debug(f"Already in channel {channel_name}")
                    else:
                        logger.error(f"Error joining channel: {e.response['error']}")
                        
            except SlackApiError as e:
                logger.error(f"Error getting channel list: {e.response['error']}")
                
        except Exception as e:
            logger.error(f"Error ensuring channel membership: {str(e)}")
        """
        pass
    
    def send_eod_prompt(self, trigger_id, private_metadata=None, existing_data=None):
        """Send EOD report modal"""
        try:
            logger.debug(f"Opening modal with trigger_id: {trigger_id}")
            
            # Build modal view
            view = self._build_eod_modal(private_metadata, existing_data)

            logger.debug(f"Sending modal view: {json.dumps(view, indent=2)}")
            
            # Open the modal
            response = self.client.views_open(
                trigger_id=trigger_id,
                view=view
            )
            
            if response["ok"]:
                logger.info("Successfully opened modal")
            else:
                logger.error(f"Error opening modal: {response.get('error')}")
                
        except Exception as e:
            logger.error(f"Error sending EOD prompt: {str(e)}")
    
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
            channel = Config.SLACK_CHANNEL
            formatted_report = self._format_report_for_channel(report_data)
            
            self.client.chat_postMessage(
                channel=channel,
                text=formatted_report,
                parse='mrkdwn'
            )
            logger.info(f"Posted report to channel {channel}")
        except SlackApiError as e:
            logger.error(f"Error posting report to channel: {e.response['error']}")
    
    def send_error_message(self, user_id):
        """Send error message to user"""
        self.send_message(user_id, "Sorry, there was an error processing your EOD report. Please try again.")

    def send_message(self, channel_id, text, thread_ts=None):
        """Send a simple message to a channel or user"""
        try:
            # If it's a channel (starts with 'C'), try to join it first
            if channel_id.startswith('C'):
                try:
                    self.client.conversations_join(channel=channel_id)
                    logger.info(f"Joined channel {channel_id}")
                except SlackApiError as e:
                    if e.response['error'] != 'already_in_channel':
                        logger.error(f"Error joining channel: {e.response['error']}")
            
            message_params = {
                'channel': channel_id,
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
        client_feedback = report_data.get('client_feedback', '').strip()
        client_feedback_section = f"""
*Client Feedback:*
{client_feedback}
""" if client_feedback else ""

        return f"""
*EOD Report from <@{report_data['user_id']}>*
*Short-term Projects:*
{report_data['short_term_projects']}

*Long-term Projects:*
{report_data['long_term_projects']}

*Blockers/Challenges:*
{report_data['blockers']}

*Tomorrow's Goals:*
{report_data['next_day_goals']}

*Software Tools Used Today:*
{report_data['tools_used']}
{client_feedback_section}
*Need Help?*
{report_data['help_needed']}
        """.strip()
    
    def _format_dict_items(self, items):
        if not items:
            return "None reported"
        return "\n".join([f" {item}" for item in items.values()])
    
    def send_already_submitted_message(self, channel_id, user_id, date):
        """Send message indicating report was already submitted with interactive buttons"""
        try:
            logger.debug(f"Sending already submitted message to channel {channel_id} for user {user_id}")
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Your EOD Report has already been submitted for {date.strftime('%B %d, %Y')}"
                    }
                },
                {
                    "type": "actions",
                    "block_id": "already_submitted_actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View",
                                "emoji": True
                            },
                            "style": "primary",
                            "value": "view_report",
                            "action_id": "view_report"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Edit",
                                "emoji": True
                            },
                            "style": "primary",
                            "value": "edit_report",
                            "action_id": "edit_report"
                        }
                    ]
                }
            ]
            
            # Send as an ephemeral message in the channel where command was triggered
            response = self.client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                blocks=blocks,
                text=f"Your EOD Report has already been submitted for {date.strftime('%B %d, %Y')}"  # Fallback text
            )
            logger.debug(f"Slack API Response: {response}")
            logger.info(f"Sent already submitted message in channel {channel_id} to user {user_id}")
        except SlackApiError as e:
            logger.error(f"Error sending already submitted message: {e.response['error']}")
    
    def show_report(self, user_id, report):
        """Show an existing report to the user"""
        try:
            formatted_report = self._format_report_for_channel(report)
            self.client.chat_postMessage(
                channel=user_id,  # DM the user
                text=formatted_report,
                parse='mrkdwn'
            )
        except SlackApiError as e:
            logger.error(f"Error showing report: {e.response['error']}")
    
    def _build_eod_modal(self, private_metadata=None, existing_data=None):
        """Build EOD report modal view"""
        blocks = [
            {
                "type": "input",
                "block_id": "short_term_block",
                "label": {"type": "plain_text", "text": "Short-term Projects"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "short_term_input",
                    "multiline": True,
                    "initial_value": existing_data.get('short_term_projects', '') if existing_data else '',
                    "placeholder": {"type": "plain_text", "text": "What did you work on today?"}
                }
            },
            {
                "type": "input",
                "block_id": "long_term_block",
                "label": {"type": "plain_text", "text": "Long-term Projects"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "long_term_input",
                    "multiline": True,
                    "initial_value": existing_data.get('long_term_projects', '') if existing_data else '',
                    "placeholder": {"type": "plain_text", "text": "Any progress on longer-term initiatives?"}
                }
            },
            {
                "type": "input",
                "block_id": "blockers_block",
                "label": {"type": "plain_text", "text": "Blockers"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "blockers_input",
                    "multiline": True,
                    "initial_value": existing_data.get('blockers', '') if existing_data else '',
                    "placeholder": {"type": "plain_text", "text": "Any challenges or blockers?"}
                }
            },
            {
                "type": "input",
                "block_id": "goals_block",
                "label": {"type": "plain_text", "text": "Next Day Goals"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "goals_input",
                    "multiline": True,
                    "initial_value": existing_data.get('next_day_goals', '') if existing_data else '',
                    "placeholder": {"type": "plain_text", "text": "What are your goals for tomorrow?"}
                }
            },
            {
                "type": "input",
                "block_id": "tools_block",
                "label": {"type": "plain_text", "text": "Tools Used"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "tools_input",
                    "initial_value": existing_data.get('tools_used', '') if existing_data else '',
                    "placeholder": {"type": "plain_text", "text": "What tools/technologies did you use today?"}
                }
            },
            {
                "type": "input",
                "block_id": "help_block",
                "label": {"type": "plain_text", "text": "Help Needed"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "help_input",
                    "multiline": True,
                    "initial_value": existing_data.get('help_needed', '') if existing_data else '',
                    "placeholder": {"type": "plain_text", "text": "Do you need any help or support?"}
                }
            },
            {
                "type": "input",
                "block_id": "client_feedback_block",
                "label": {"type": "plain_text", "text": "Client Feedback"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "client_feedback_input",
                    "multiline": True,
                    "initial_value": existing_data.get('client_feedback', '') if existing_data else '',
                    "placeholder": {"type": "plain_text", "text": "Any feedback received from clients?"}
                },
                "optional": True
            }
        ]

        return {
            "type": "modal",
            "callback_id": "eod_submission",
            "title": {"type": "plain_text", "text": "EOD Report"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": blocks,
            "private_metadata": private_metadata or ""
        }

    def get_channel_members(self, channel_id):
        """Get list of members in a channel"""
        try:
            # First, try to join the channel if not already a member
            try:
                self.client.conversations_join(channel=channel_id)
            except SlackApiError as e:
                if e.response['error'] not in ['already_in_channel', 'is_archived']:
                    logger.error(f"Error joining channel: {e.response['error']}")

            # Get channel info including members
            response = self.client.conversations_members(channel=channel_id)
            members = response['members']
            
            # Filter out bots and inactive users
            active_members = []
            for member in members:
                try:
                    user_info = self.client.users_info(user=member)['user']
                    if not user_info.get('is_bot', False) and not user_info.get('deleted', False):
                        active_members.append(member)
                except SlackApiError as e:
                    logger.error(f"Error getting user info for {member}: {e.response['error']}")
                    continue
            
            logger.info(f"Found {len(active_members)} active members in channel {channel_id}")
            return active_members
            
        except SlackApiError as e:
            logger.error(f"Error getting channel members: {e.response['error']}")
            return []

    def post_weekly_summary(self, user_id, summary):
        """Post weekly summary to the weekly summaries channel"""
        try:
            # Get channel ID first
            try:
                response = self.client.conversations_list(types="private_channel")
                channel_id = None
                for channel in response['channels']:
                    if channel['name'] == Config.SLACK_WEEKLY_SUMMARY_CHANNEL.lstrip('#'):
                        channel_id = channel['id']
                        break
                
                if not channel_id:
                    raise ValueError(f"Channel {Config.SLACK_WEEKLY_SUMMARY_CHANNEL} not found")
                
                # Post to weekly summaries channel
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=f"*Weekly Summary for <@{user_id}>*\n\n{summary}",
                    parse='mrkdwn'
                )
                
                # Also send to the user
                self.send_message(
                    user_id,
                    f"Your weekly summary has been generated and posted to <#{channel_id}>:\n\n{summary}"
                )
                
                logger.info(f"Posted weekly summary for user {user_id}")
            except SlackApiError as e:
                logger.error(f"Error posting weekly summary: {e.response['error']}")
                
        except Exception as e:
            logger.error(f"Error in post_weekly_summary: {str(e)}")
