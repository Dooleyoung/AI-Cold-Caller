"""
Google Meet integration for scheduling meetings
"""
import os
import pickle
import json
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

class GoogleMeetScheduler:
    """Google Calendar and Meet integration"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/calendar.events'
    ]
    
    def __init__(self):
        """Initialize Google Calendar service"""
        self.service = None
        self.credentials = None
        self._setup_credentials()
    
    def _setup_credentials(self):
        """Setup Google Calendar API credentials"""
        try:
            # Token file stores the user's access and refresh tokens
            token_file = 'token.pickle'
            
            # Load existing credentials
            if os.path.exists(token_file):
                with open(token_file, 'rb') as token:
                    self.credentials = pickle.load(token)
            
            # If no valid credentials, get new ones
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    try:
                        self.credentials.refresh(Request())
                        logger.info("Google credentials refreshed")
                    except Exception as e:
                        logger.warning(f"Failed to refresh credentials: {e}")
                        self.credentials = None
                
                if not self.credentials:
                    # Check for credentials file
                    if not os.path.exists(settings.GOOGLE_CREDENTIALS_FILE):
                        logger.error(f"Google credentials file not found: {settings.GOOGLE_CREDENTIALS_FILE}")
                        logger.error("Please download credentials.json from Google Cloud Console")
                        return
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        settings.GOOGLE_CREDENTIALS_FILE, 
                        self.SCOPES
                    )
                    
                    # Run local server for OAuth
                    self.credentials = flow.run_local_server(port=0)
                    logger.info("New Google credentials obtained")
                
                # Save credentials for next run
                with open(token_file, 'wb') as token:
                    pickle.dump(self.credentials, token)
            
            # Build service
            self.service = build('calendar', 'v3', credentials=self.credentials)
            logger.info("Google Calendar service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to setup Google credentials: {e}")
            self.service = None
    
    def schedule_meeting(
        self, 
        lead_info: Dict[str, Any], 
        preferred_time: Optional[str] = None,
        duration_minutes: int = 30
    ) -> Dict[str, Any]:
        """Schedule a Google Meet meeting"""
        
        if not self.service:
            raise Exception("Google Calendar service not available")
        
        try:
            # Parse or set default meeting time
            meeting_time = self._parse_meeting_time(preferred_time)
            end_time = meeting_time + timedelta(minutes=duration_minutes)
            
            # Create event
            event = {
                'summary': f"Business Discussion with {lead_info.get('name', 'Prospect')}",
                'description': self._generate_meeting_description(lead_info),
                'start': {
                    'dateTime': meeting_time.isoformat(),
                    'timeZone': 'America/New_York',
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'America/New_York',
                },
                'attendees': self._build_attendees_list(lead_info),
                'conferenceData': {
                    'createRequest': {
                        'requestId': f"meet-{lead_info.get('id', 'unknown')}-{int(datetime.now().timestamp())}",
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                    }
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                        {'method': 'popup', 'minutes': 15},  # 15 minutes before
                    ],
                },
                'guestsCanModify': True,
                'guestsCanInviteOthers': False,
            }
            
            # Create the event
            created_event = self.service.events().insert(
                calendarId='primary',
                body=event,
                conferenceDataVersion=1,
                sendUpdates='all'  # Send invites to attendees
            ).execute()
            
            # Extract meeting information
            meet_link = self._extract_meet_link(created_event)
            
            meeting_info = {
                'event_id': created_event.get('id'),
                'meet_link': meet_link,
                'meeting_time': meeting_time.isoformat(),
                'end_time': end_time.isoformat(),
                'calendar_link': created_event.get('htmlLink'),
                'duration_minutes': duration_minutes
            }
            
            logger.info(f"Meeting scheduled successfully for {lead_info.get('name', 'Unknown')}: {meet_link}")
            return meeting_info
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}")
            error_details = json.loads(e.content.decode())
            raise Exception(f"Failed to schedule meeting: {error_details.get('error', {}).get('message', 'Unknown error')}")
        
        except Exception as e:
            logger.error(f"Unexpected error scheduling meeting: {e}")
            raise
    
    def reschedule_meeting(
        self, 
        event_id: str, 
        new_time: datetime, 
        duration_minutes: int = 30
    ) -> Dict[str, Any]:
        """Reschedule an existing meeting"""
        
        if not self.service:
            raise Exception("Google Calendar service not available")
        
        try:
            # Get existing event
            event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
            
            # Update times
            end_time = new_time + timedelta(minutes=duration_minutes)
            event['start']['dateTime'] = new_time.isoformat()
            event['end']['dateTime'] = end_time.isoformat()
            
            # Update event
            updated_event = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event,
                sendUpdates='all'
            ).execute()
            
            meet_link = self._extract_meet_link(updated_event)
            
            logger.info(f"Meeting {event_id} rescheduled to {new_time}")
            
            return {
                'event_id': updated_event.get('id'),
                'meet_link': meet_link,
                'meeting_time': new_time.isoformat(),
                'end_time': end_time.isoformat(),
                'calendar_link': updated_event.get('htmlLink')
            }
            
        except Exception as e:
            logger.error(f"Error rescheduling meeting {event_id}: {e}")
            raise
    
    def cancel_meeting(self, event_id: str, reason: str = "Meeting cancelled") -> bool:
        """Cancel a scheduled meeting"""
        
        if not self.service:
            logger.error("Google Calendar service not available")
            return False
        
        try:
            # Delete the event
            self.service.events().delete(
                calendarId='primary',
                eventId=event_id,
                sendUpdates='all'
            ).execute()
            
            logger.info(f"Meeting {event_id} cancelled: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling meeting {event_id}: {e}")
            return False
    
    def get_available_times(
        self, 
        date: datetime, 
        duration_minutes: int = 30,
        business_hours_only: bool = True
    ) -> list:
        """Get available meeting times for a given date"""
        
        if not self.service:
            return []
        
        try:
            # Set time range for the day
            day_start = date.replace(hour=9 if business_hours_only else 0, minute=0, second=0, microsecond=0)
            day_end = date.replace(hour=17 if business_hours_only else 23, minute=0, second=0, microsecond=0)
            
            # Get busy times
            freebusy_query = {
                'timeMin': day_start.isoformat() + 'Z',
                'timeMax': day_end.isoformat() + 'Z',
                'items': [{'id': 'primary'}]
            }
            
            freebusy_result = self.service.freebusy().query(body=freebusy_query).execute()
            busy_times = freebusy_result.get('calendars', {}).get('primary', {}).get('busy', [])
            
            # Generate available slots
            available_times = []
            current_time = day_start
            
            while current_time + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = current_time + timedelta(minutes=duration_minutes)
                
                # Check if slot conflicts with busy times
                is_available = True
                for busy in busy_times:
                    busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                    busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
                    
                    if (current_time < busy_end and slot_end > busy_start):
                        is_available = False
                        break
                
                if is_available:
                    available_times.append(current_time)
                
                # Move to next 30-minute slot
                current_time += timedelta(minutes=30)
            
            return available_times
            
        except Exception as e:
            logger.error(f"Error getting available times: {e}")
            return []
    
    def _parse_meeting_time(self, preferred_time: Optional[str]) -> datetime:
        """Parse preferred meeting time or return default"""
        
        # Default: next business day at 2 PM
        default_time = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
        
        # If today is Friday, schedule for Monday
        if default_time.weekday() == 4:  # Friday
            default_time += timedelta(days=3)
        # If weekend, schedule for Monday
        elif default_time.weekday() >= 5:  # Weekend
            days_until_monday = 7 - default_time.weekday()
            default_time += timedelta(days=days_until_monday)
        # If before 3 PM on weekday, schedule for tomorrow
        elif datetime.now().hour < 15:
            default_time += timedelta(days=1)
        # If after 3 PM, schedule for day after tomorrow
        else:
            default_time += timedelta(days=2)
        
        if not preferred_time:
            return default_time
        
        # Try to parse preferred time (basic implementation)
        try:
            # Handle common phrases
            preferred_lower = preferred_time.lower()
            
            if "tomorrow" in preferred_lower:
                return (datetime.now() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
            elif "next week" in preferred_lower:
                return (datetime.now() + timedelta(days=7)).replace(hour=14, minute=0, second=0, microsecond=0)
            elif "monday" in preferred_lower:
                days_ahead = 0 - datetime.now().weekday()
                if days_ahead <= 0:  # Target day already happened this week
                    days_ahead += 7
                return (datetime.now() + timedelta(days=days_ahead)).replace(hour=14, minute=0, second=0, microsecond=0)
            # Add more parsing logic as needed
            
        except:
            pass
        
        return default_time
    
    def _generate_meeting_description(self, lead_info: Dict[str, Any]) -> str:
        """Generate meeting description"""
        company = lead_info.get('company', 'their company')
        name = lead_info.get('name', 'the prospect')
        
        description = f"""
Thank you for your interest in learning more about how we can help {company}!

This meeting will cover:
- Understanding your current business challenges
- Exploring how our solutions can help streamline your operations
- Discussing potential ROI and implementation timeline
- Answering any questions you may have

Looking forward to speaking with {name}!

Best regards,
Sarah - TechSolutions Team
        """.strip()
        
        return description
    
    def _build_attendees_list(self, lead_info: Dict[str, Any]) -> list:
        """Build attendees list for the meeting"""
        attendees = []
        
        # Add lead if email available
        if lead_info.get('email'):
            attendees.append({
                'email': lead_info['email'],
                'displayName': lead_info.get('name', ''),
                'responseStatus': 'needsAction'
            })
        
        # Add your email (you might want to configure this)
        # attendees.append({
        #     'email': 'sarah@techsolutions.com',
        #     'displayName': 'Sarah - TechSolutions',
        #     'responseStatus': 'accepted'
        # })
        
        return attendees
    
    def _extract_meet_link(self, event: Dict[str, Any]) -> str:
        """Extract Google Meet link from event"""
        try:
            conference_data = event.get('conferenceData', {})
            entry_points = conference_data.get('entryPoints', [])
            
            for entry_point in entry_points:
                if entry_point.get('entryPointType') == 'video':
                    return entry_point.get('uri', '')
            
            # Fallback: check hangoutLink
            return event.get('hangoutLink', '')
            
        except Exception as e:
            logger.error(f"Error extracting meet link: {e}")
            return ""
    
    def test_connection(self) -> bool:
        """Test Google Calendar connection"""
        try:
            if not self.service:
                return False
            
            # Try to access calendar
            calendar_list = self.service.calendarList().list(maxResults=1).execute()
            logger.info("Google Calendar connection test successful")
            return True
            
        except Exception as e:
            logger.error(f"Google Calendar connection test failed: {e}")
            return False

# Export
__all__ = ['GoogleMeetScheduler']