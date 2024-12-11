from openai import OpenAI
from config import Config
import logging
from time import sleep

logger = logging.getLogger(__name__)

class OpenAIClient:
    def __init__(self):
        if not Config.openai_config_valid():
            logger.error("OpenAI configuration is not valid")
            raise ValueError("Invalid OpenAI configuration. Please check your API key.")
            
        try:
            self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
            # Test the client with a simple request
            self.client.models.list()
            logger.info("OpenAI client initialized successfully")
            
            # Track API usage
            self._request_count = 0
            self._token_count = 0
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise ValueError(f"OpenAI client initialization failed: {str(e)}")

    def generate_weekly_summary(self, reports):
        """Generate a weekly summary for a contractor's reports"""
        if not reports:
            logger.warning("No reports provided for summary generation")
            return "No reports available for summary."
            
        try:
            # Format reports into a structured text
            report_text = self._format_reports_for_prompt(reports)
            
            # Check rate limits (500 RPM)
            if self._request_count >= 450:  # Buffer for safety
                logger.warning("Approaching rate limit, sleeping for 60 seconds")
                sleep(60)
                self._request_count = 0
            
            # Generate summary using GPT-4-Optimized
            response = self.client.chat.completions.create(
                model="gpt-4o",  # GPT-4 Optimized
                messages=[
                    {"role": "system", "content": """You are a professional report analyzer. 
                    Analyze the week's EOD reports and create a concise but comprehensive summary that includes:
                    1. Key accomplishments and milestones
                    2. Progress on both short-term and long-term projects
                    3. Notable challenges or blockers
                    4. Patterns in tool usage and technical focus
                    5. Areas where help was requested
                    6. Important client feedback
                    7. Recommendations for improving productivity
                    Format the response in Slack-compatible markdown.
                    Keep the response within 2000 tokens."""},  # Ensure we stay well within token limits
                    {"role": "user", "content": f"Here are the EOD reports for the past week:\n\n{report_text}"}
                ],
                max_tokens=2000,  # Reduced to stay well within the 30,000 TPM limit
                temperature=0.7
            )
            
            self._request_count += 1
            self._token_count += response.usage.total_tokens
            
            # Log usage for monitoring
            logger.info(f"API Usage - Requests: {self._request_count}, Tokens: {self._token_count}")
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return "Error generating summary. Please try again later."

    def _format_reports_for_prompt(self, reports):
        """Format reports into a structured text for the prompt"""
        formatted_reports = []
        for report in reports:
            formatted_report = f"""
Date: {report.get('timestamp', 'Unknown').strftime('%Y-%m-%d')}
Short-term Projects: {report.get('short_term_projects', 'None')}
Long-term Projects: {report.get('long_term_projects', 'None')}
Blockers: {report.get('blockers', 'None')}
Goals: {report.get('next_day_goals', 'None')}
Tools Used: {report.get('tools_used', 'None')}
Help Needed: {report.get('help_needed', 'None')}
Client Feedback: {report.get('client_feedback', 'None')}
"""
            formatted_reports.append(formatted_report)
        
        return "\n---\n".join(formatted_reports) 