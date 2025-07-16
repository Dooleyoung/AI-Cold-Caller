"""
Twilio integration for voice calls and TwiML generation
"""
import os
from typing import Optional, Dict, Any
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Say
from twilio.base.exceptions import TwilioException

from config.credentials import credential_manager
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

class TwilioCallManager:
    """Manages Twilio voice calls and TwiML generation"""
    
    def __init__(self):
        """Initialize Twilio client"""
        try:
            sid, token, phone = credential_manager.get_twilio_credentials()
            self.client = Client(sid, token)
            self.from_number = phone
            
            # Test connection
            self.client.api.accounts(sid).fetch()
            logger.info(f"Twilio client initialized successfully with phone: {phone}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")
            raise
    
    def initiate_call(self, to_number: str, lead_id: int) -> str:
        """Initiate outbound call to lead with DEBUG logging"""
        try:
            # Clean phone number
            to_number = self._clean_phone_number(to_number)
            logger.info(f"DEBUG: Cleaned phone number: {to_number}")
        
            # Construct webhook URLs
            webhook_base = settings.WEBHOOK_BASE_URL.rstrip('/')
            logger.info(f"DEBUG: Webhook base URL: {webhook_base}")
        
            call_url = f"{webhook_base}/webhook/call-start?lead_id={lead_id}"
            status_url = f"{webhook_base}/webhook/call-status"
        
            logger.info(f"DEBUG: Call URL: {call_url}")
            logger.info(f"DEBUG: Status URL: {status_url}")
        
            # DEBUG: Test Twilio client first
            try:
                account = self.client.api.accounts(self.client.account_sid).fetch()
                logger.info(f"DEBUG: Account status: {account.status}")
            except Exception as e:
                logger.error(f"DEBUG: Account fetch failed: {e}")
                raise
        
            # Create the call
            logger.info(f"DEBUG: Creating call from {self.from_number} to {to_number}")
        
            call = self.client.calls.create(
                to=to_number,
                from_=self.from_number,
                url=call_url,
                method='POST',
                status_callback=status_url,
                status_callback_event=['initiated', 'ringing', 'answered', 'completed', 'failed'],
                status_callback_method='POST',
                record=True,
                timeout=settings.CALL_TIMEOUT,
                machine_detection='Enable',
                machine_detection_timeout=10
            )
        
            logger.info(f"DEBUG: Call object created: {call}")
            logger.info(f"DEBUG: Call SID: {call.sid}")
            logger.info(f"DEBUG: Call status: {call.status}")
            logger.info(f"DEBUG: Call to: {call.to}")
        
            logger.info(f"Call initiated to {to_number} for lead {lead_id}, SID: {call.sid}")
            return call.sid
        
        except TwilioException as e:
            logger.error(f"DEBUG: TwilioException details: {e}")
            logger.error(f"DEBUG: Exception code: {getattr(e, 'code', 'N/A')}")
            logger.error(f"DEBUG: Exception msg: {getattr(e, 'msg', 'N/A')}")
            raise
        except Exception as e:
            logger.error(f"DEBUG: Unexpected exception: {e}")
            logger.error(f"DEBUG: Exception type: {type(e)}")
            import traceback
            logger.error(f"DEBUG: Traceback: {traceback.format_exc()}")
            raise
    
    def generate_speech_gather_twiml(
        self, 
        speech_text: str, 
        action_url: str, 
        timeout: int = 5,
        speech_timeout: str = "2",
        gather_timeout: int = 3
    ) -> str:
        """Generate TwiML with speech recognition"""
        try:
            response = VoiceResponse()
            
            # Create gather element for speech input
            gather = Gather(
                input='speech',
                timeout=gather_timeout,
                speech_timeout=speech_timeout,
                action=action_url,
                method='POST',
                enhanced=True,  # Better speech recognition
                speech_model='phone_call'  # Optimized for phone calls
            )
            
            # Add speech to gather
            gather.say(
                speech_text,
                voice='alice',
                language='en-US'
            )
            
            response.append(gather)
            
            # Fallback if no speech detected
            response.say(
                "I didn't hear anything. Thank you for your time, and have a great day!",
                voice='alice'
            )
            response.hangup()
            
            twiml_str = str(response)
            logger.debug(f"Generated TwiML: {twiml_str}")
            return twiml_str
            
        except Exception as e:
            logger.error(f"Error generating speech gather TwiML: {e}")
            return self._generate_error_twiml()
    
    def generate_simple_response_twiml(
        self, 
        message: str, 
        hangup: bool = False,
        voice: str = 'alice'
    ) -> str:
        """Generate simple TwiML response"""
        try:
            response = VoiceResponse()
            
            response.say(message, voice=voice, language='en-US')
            
            if hangup:
                response.hangup()
            
            return str(response)
            
        except Exception as e:
            logger.error(f"Error generating simple TwiML: {e}")
            return self._generate_error_twiml()
    
    def generate_transfer_twiml(self, transfer_number: str, message: str = None) -> str:
        """Generate TwiML to transfer call"""
        try:
            response = VoiceResponse()
            
            if message:
                response.say(message, voice='alice')
            
            response.dial(transfer_number, timeout=30)
            
            # Fallback if transfer fails
            response.say("I'm unable to transfer you right now. Thank you for calling!")
            response.hangup()
            
            return str(response)
            
        except Exception as e:
            logger.error(f"Error generating transfer TwiML: {e}")
            return self._generate_error_twiml()
    
    def handle_machine_detection(self, machine_detected: str) -> str:
        """Handle answering machine detection"""
        if machine_detected == "machine":
            # Leave voicemail
            message = (
                "Hello! This is Sarah from TechSolutions. I called to discuss how we can help "
                "streamline your business operations. Please call me back at your convenience. "
                "Thank you!"
            )
            logger.info("Answering machine detected, leaving voicemail")
            return self.generate_simple_response_twiml(message, hangup=True)
        
        elif machine_detected == "fax":
            logger.info("Fax machine detected")
            return self.generate_simple_response_twiml("", hangup=True)  # Silent hangup
        
        else:
            # Human answered or unknown
            logger.info(f"Machine detection result: {machine_detected}")
            return None  # Continue with normal call flow
    
    def get_call_details(self, call_sid: str) -> Optional[Dict[str, Any]]:
        """Get call details from Twilio"""
        try:
            call = self.client.calls(call_sid).fetch()
            
            return {
                'sid': call.sid,
                'status': call.status,
                'duration': call.duration,
                'from_number': call.from_,
                'to_number': call.to,
                'start_time': call.start_time,
                'end_time': call.end_time,
                'price': call.price,
                'direction': call.direction
            }
            
        except TwilioException as e:
            logger.error(f"Error fetching call details for {call_sid}: {e}")
            return None
    
    def get_call_recordings(self, call_sid: str) -> list:
        """Get recordings for a call"""
        try:
            recordings = self.client.recordings.list(call_sid=call_sid)
            
            recording_list = []
            for record in recordings:
                recording_list.append({
                    'sid': record.sid,
                    'duration': record.duration,
                    'date_created': record.date_created,
                    'uri': record.uri,
                    'media_url': f"https://api.twilio.com{record.uri.replace('.json', '.mp3')}"
                })
            
            return recording_list
            
        except TwilioException as e:
            logger.error(f"Error fetching recordings for {call_sid}: {e}")
            return []
    
    def _clean_phone_number(self, phone: str) -> str:
        """Clean and format phone number"""
        # Remove all non-digit characters
        cleaned = ''.join(filter(str.isdigit, phone))
        
        # Add country code if missing
        if len(cleaned) == 10:
            cleaned = '1' + cleaned
        
        # Add + prefix
        if not cleaned.startswith('+'):
            cleaned = '+' + cleaned
        
        return cleaned
    
    def _generate_error_twiml(self) -> str:
        """Generate error TwiML"""
        response = VoiceResponse()
        response.say(
            "I apologize, but I'm experiencing technical difficulties. "
            "Thank you for your time, and have a great day!",
            voice='alice'
        )
        response.hangup()
        return str(response)
    
    def validate_phone_number(self, phone: str) -> bool:
        """Validate phone number format"""
        try:
            cleaned = self._clean_phone_number(phone)
            
            # Basic validation
            if len(cleaned) < 10 or len(cleaned) > 15:
                return False
            
            # Use Twilio's lookup service for advanced validation
            try:
                lookup = self.client.lookups.v1.phone_numbers(cleaned).fetch()
                return lookup.phone_number is not None
            except:
                # Fallback to basic validation if lookup fails
                return len(cleaned) >= 10
                
        except Exception:
            return False

# Export
__all__ = ['TwilioCallManager']