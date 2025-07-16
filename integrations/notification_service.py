"""
Email and SMS notification service for meeting scheduling
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from datetime import datetime

from twilio.rest import Client as TwilioClient
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

class NotificationService:
    """Service for sending email and SMS notifications"""
    
    def __init__(self):
        """Initialize notification service"""
        self.twilio_client = None
        self._setup_twilio()
    
    def _setup_twilio(self):
        """Setup Twilio client for SMS"""
        try:
            if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
                self.twilio_client = TwilioClient(
                    settings.TWILIO_ACCOUNT_SID,
                    settings.TWILIO_AUTH_TOKEN
                )
                logger.info("Twilio client initialized for SMS notifications")
            else:
                logger.warning("Twilio credentials not available for SMS notifications")
        except Exception as e:
            logger.error(f"Failed to initialize Twilio for notifications: {e}")
    
    def send_meeting_notifications(
        self, 
        lead_info: Dict[str, Any], 
        meeting_info: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Send both email and SMS notifications for scheduled meeting"""
        
        results = {
            'email_sent': False,
            'sms_sent': False
        }
        
        # Send email notification
        if lead_info.get('email') and settings.NOTIFICATION_EMAIL:
            try:
                results['email_sent'] = self.send_email_notification(lead_info, meeting_info)
            except Exception as e:
                logger.error(f"Failed to send email notification: {e}")
        
        # Send SMS notification
        if lead_info.get('phone'):
            try:
                results['sms_sent'] = self.send_sms_notification(lead_info, meeting_info)
            except Exception as e:
                logger.error(f"Failed to send SMS notification: {e}")
        
        return results
    
    def send_email_notification(
        self, 
        lead_info: Dict[str, Any], 
        meeting_info: Dict[str, Any]
    ) -> bool:
        """Send email notification with meeting details"""
        
        try:
            # Format meeting time
            meeting_time = datetime.fromisoformat(meeting_info['meeting_time'].replace('Z', '+00:00'))
            formatted_time = meeting_time.strftime("%B %d, %Y at %I:%M %p %Z")
            
            # Create email content
            subject = f"Meeting Scheduled - {lead_info.get('name', 'Business Discussion')}"
            
            html_body = self._create_email_template(lead_info, meeting_info, formatted_time)
            text_body = self._create_text_email(lead_info, meeting_info, formatted_time)
            
            # Send via SMTP
            if settings.SMTP_SERVER:
                return self._send_smtp_email(
                    to_email=settings.NOTIFICATION_EMAIL,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body
                )
            # Send via SendGrid (if configured)
            elif settings.SENDGRID_API_KEY:
                return self._send_sendgrid_email(
                    to_email=settings.NOTIFICATION_EMAIL,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body
                )
            else:
                logger.warning("No email service configured")
                return False
                
        except Exception as e:
            logger.error(f"Email notification failed: {e}")
            return False
    
    def send_sms_notification(
        self, 
        lead_info: Dict[str, Any], 
        meeting_info: Dict[str, Any]
    ) -> bool:
        """Send SMS notification to the lead's phone number"""
        
        if not self.twilio_client:
            logger.warning("Twilio not configured for SMS notifications")
            return False
        
        try:
            # Format meeting time
            meeting_time = datetime.fromisoformat(meeting_info['meeting_time'].replace('Z', '+00:00'))
            formatted_time = meeting_time.strftime("%B %d at %I:%M %p")
            
            # Create SMS message
            message_body = (
                f"Hi {lead_info.get('name', 'there')}! 📅\n\n"
                f"Great news - your meeting is scheduled for {formatted_time}.\n\n"
                f"Google Meet Link: {meeting_info.get('meet_link', '')}\n\n"
                f"Looking forward to our discussion!\n"
                f"- Sarah from DataSphere Solutions"
            )
            
            # Send SMS using Twilio
            message = self.twilio_client.messages.create(
                body=message_body,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=lead_info['phone']
            )
            
            logger.info(f"SMS sent successfully to {lead_info['phone']}: {message.sid}")
            return True
            
        except Exception as e:
            logger.error(f"SMS notification failed for {lead_info.get('phone', 'unknown')}: {e}")
            return False
    
    def _create_email_template(
        self, 
        lead_info: Dict[str, Any], 
        meeting_info: Dict[str, Any], 
        formatted_time: str
    ) -> str:
        """Create HTML email template"""
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Meeting Scheduled</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; text-align: center; margin-bottom: 30px;">
                <h1 style="margin: 0; font-size: 28px;">Meeting Scheduled! 🎉</h1>
                <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Your conversation with {lead_info.get('name', 'the prospect')} is confirmed</p>
            </div>
            
            <div style="background: #f8f9fa; padding: 25px; border-radius: 8px; border-left: 4px solid #667eea; margin-bottom: 25px;">
                <h2 style="color: #667eea; margin-top: 0;">Meeting Details</h2>
                <p style="margin: 5px 0;"><strong>👤 Contact:</strong> {lead_info.get('name', 'Unknown')}</p>
                <p style="margin: 5px 0;"><strong>🏢 Company:</strong> {lead_info.get('company', 'Not specified')}</p>
                <p style="margin: 5px 0;"><strong>📞 Phone:</strong> {lead_info.get('phone', 'Not provided')}</p>
                <p style="margin: 5px 0;"><strong>✉️ Email:</strong> {lead_info.get('email', 'Not provided')}</p>
                <p style="margin: 5px 0;"><strong>📅 Date & Time:</strong> {formatted_time}</p>
                <p style="margin: 5px 0;"><strong>⏱️ Duration:</strong> {meeting_info.get('duration_minutes', 30)} minutes</p>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{meeting_info.get('meet_link', '#')}" 
                   style="display: inline-block; background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">
                    🎥 Join Google Meet
                </a>
            </div>
            
            <div style="background: #e3f2fd; padding: 20px; border-radius: 8px; margin: 25px 0;">
                <h3 style="color: #1976d2; margin-top: 0;">Quick Access Links</h3>
                <p style="margin: 8px 0;"><a href="{meeting_info.get('meet_link', '#')}" style="color: #1976d2;">🎥 Google Meet Link</a></p>
                <p style="margin: 8px 0;"><a href="{meeting_info.get('calendar_link', '#')}" style="color: #1976d2;">📅 View in Google Calendar</a></p>
            </div>
            
            <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px; padding: 20px; margin: 25px 0;">
                <h3 style="color: #856404; margin-top: 0;">📋 Meeting Agenda</h3>
                <ul style="color: #856404; margin: 0; padding-left: 20px;">
                    <li>Understanding current business challenges</li>
                    <li>Exploring our solutions for {lead_info.get('company', 'your company')}</li>
                    <li>Discussing ROI and implementation timeline</li>
                    <li>Q&A session</li>
                </ul>
            </div>
            
            <div style="border-top: 2px solid #eee; padding-top: 20px; margin-top: 30px; text-align: center; color: #666;">
                <p>Best regards,<br>
                <strong>Sarah from DataSphere Solutions</strong></p>
                <p style="font-size: 14px; margin-top: 15px;">
                    Need to reschedule? Reply to this email or call us directly.
                </p>
            </div>
        </body>
        </html>
        """
    
    def _create_text_email(
        self, 
        lead_info: Dict[str, Any], 
        meeting_info: Dict[str, Any], 
        formatted_time: str
    ) -> str:
        """Create plain text email"""
        
        return f"""
Meeting Scheduled! 🎉

Your conversation with {lead_info.get('name', 'the prospect')} is confirmed.

MEETING DETAILS:
👤 Contact: {lead_info.get('name', 'Unknown')}
🏢 Company: {lead_info.get('company', 'Not specified')}
📞 Phone: {lead_info.get('phone', 'Not provided')}
✉️ Email: {lead_info.get('email', 'Not provided')}
📅 Date & Time: {formatted_time}
⏱️ Duration: {meeting_info.get('duration_minutes', 30)} minutes

QUICK ACCESS:
🎥 Google Meet: {meeting_info.get('meet_link', '')}
📅 Calendar: {meeting_info.get('calendar_link', '')}

MEETING AGENDA:
• Understanding current business challenges
• Exploring our solutions for {lead_info.get('company', 'your company')}
• Discussing ROI and implementation timeline
• Q&A session

Best regards,
Sarah from DataSphere Solutions

Need to reschedule? Reply to this email or call us directly.
        """.strip()
    
    def _send_smtp_email(
        self, 
        to_email: str, 
        subject: str, 
        html_body: str, 
        text_body: str
    ) -> bool:
        """Send email via SMTP"""
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = settings.SMTP_FROM_EMAIL
            msg['To'] = to_email
            
            # Add text and HTML parts
            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send email
            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                
                server.send_message(msg)
            
            logger.info(f"Email sent successfully via SMTP to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP email failed: {e}")
            return False
    
    def _send_sendgrid_email(
        self, 
        to_email: str, 
        subject: str, 
        html_body: str, 
        text_body: str
    ) -> bool:
        """Send email via SendGrid"""
        
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail
            
            sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
            
            message = Mail(
                from_email=settings.SENDGRID_FROM_EMAIL,
                to_emails=to_email,
                subject=subject,
                html_content=html_body,
                plain_text_content=text_body
            )
            
            response = sg.send(message)
            
            if response.status_code == 202:
                logger.info(f"Email sent successfully via SendGrid to {to_email}")
                return True
            else:
                logger.error(f"SendGrid email failed with status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"SendGrid email failed: {e}")
            return False

# Global notification service instance
notification_service = NotificationService()

# Export
__all__ = ['NotificationService', 'notification_service']