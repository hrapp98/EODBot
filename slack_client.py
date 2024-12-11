from slack_sdk import WebClient

class SlackClient:
    def __init__(self, token):
        self.client = WebClient(token=token)
        
    def get_user_info(self, user_id):
        """Get user information from Slack"""
        try:
            response = self.client.users_info(user=user_id)
            if response['ok']:
                return response['user']
            else:
                logger.error(f"Error getting user info from Slack: {response.get('error')}")
                return None
        except Exception as e:
            logger.error(f"Error getting user info from Slack: {str(e)}")
            return None 