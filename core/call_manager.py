"""
Main call orchestration and management
"""
import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

from core.ai_engine import AICallEngine
from integrations.twilio_client import TwilioCallManager
from integrations.google_meet import GoogleMeetScheduler
from integrations.speech_processor import SpeechProcessor
from database.crud import get_lead, update_lead, create_call_record, update_call_record, get_call_record_by_sid
from scheduler.queue_manager import CallQueueManager
from utils.logger import get_logger
from config.settings import settings
from integrations.notification_service import notification_service

logger = get_logger(__name__)


class CallOrchestrator:
    def __init__(self):
        self.ai_engine = AICallEngine()
        self.twilio_manager = TwilioCallManager()
        self.meet_scheduler = GoogleMeetScheduler()
        self.speech_processor = SpeechProcessor()
        self.queue_manager = CallQueueManager()

        self.active_calls: Dict[str, Dict] = {}
        self.call_metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "meetings_scheduled": 0,
            "call_duration_total": 0
        }

        logger.info("CallOrchestrator initialized successfully")

    def start_call(self, lead_id: int) -> Tuple[bool, str]:
        try:
            lead = get_lead(lead_id)
            if not lead:
                raise ValueError(f"Lead {lead_id} not found")

            if lead.status == 'calling':
                return False, "Call already in progress for this lead"

            update_lead(lead_id, status='calling')

            lead_info = {
                'id': lead.id,
                'name': lead.name,
                'company': lead.company,
                'email': lead.email,
                'phone': lead.phone
            }

            self.ai_engine.set_lead_info(lead_info)
            self.ai_engine.reset_conversation()

            call_sid = self.twilio_manager.initiate_call(lead.phone, lead_id)

            call_record_id = create_call_record(
                lead_id=lead_id,
                twilio_call_sid=call_sid,
                status='initiated'
            )

            self.active_calls[call_sid] = {
                'lead_id': lead_id,
                'call_record_id': call_record_id,
                'start_time': datetime.now(),
                'lead_info': lead_info,
                'conversation_turns': 0
            }

            self.call_metrics["total_calls"] += 1

            logger.info(f"Call initiated for lead {lead_id} ({lead.name}): {call_sid}")
            return True, call_sid

        except Exception as e:
            logger.error(f"Failed to start call for lead {lead_id}: {e}")
            update_lead(lead_id, status='failed')
            return False, str(e)

    def handle_call_answered(self, call_sid: str, from_number: str) -> str:
        try:
            if call_sid not in self.active_calls:
                logger.warning(f"Received call answered for unknown call: {call_sid}")
                return self._generate_error_twiml("Unknown call session")

            call_state = self.active_calls[call_sid]
            lead_info = call_state['lead_info']

            update_call_record(call_state['call_record_id'], status='answered')

            initial_greeting = self.ai_engine.generate_response(
                "Call started - begin greeting",
                force_stage="greeting"
            )

            twiml = self.twilio_manager.generate_speech_gather_twiml(
                speech_text=initial_greeting,
                action_url=f"/webhook/process-speech/{call_sid}",
                timeout=5
            )

            logger.info(f"Call {call_sid} answered, greeting: {initial_greeting[:50]}...")
            return twiml

        except Exception as e:
            logger.error(f"Error handling call answered {call_sid}: {e}")
            return self._generate_error_twiml("Error processing call")

    def process_conversation_turn(self, call_sid: str, speech_text: str, confidence: float = 1.0) -> str:
        try:
            if call_sid not in self.active_calls:
                logger.warning(f"Received speech for unknown call: {call_sid}")
                return self._generate_hangup_twiml("Thank you for your time.")

            call_state = self.active_calls[call_sid]
            call_state['conversation_turns'] += 1

            speech_text = speech_text.strip()
            if not speech_text:
                return self._generate_clarification_twiml()

            logger.info(f"Call {call_sid} - User said: '{speech_text}'")

            if self._should_end_call(speech_text):
                return self._handle_call_termination(call_sid, speech_text)

            if self.ai_engine.detect_meeting_intent(speech_text):
                return self._handle_meeting_request(call_sid, speech_text)

            if self.ai_engine.detect_rejection(speech_text):
                return self._handle_rejection(call_sid, speech_text)

            ai_response = self.ai_engine.generate_response(speech_text)

            if call_state['conversation_turns'] >= 10:
                ai_response += " It's been great talking with you. Would you like me to schedule a brief call for us to continue this conversation?"
                return self.twilio_manager.generate_speech_gather_twiml(
                    speech_text=ai_response,
                    action_url=f"/webhook/final-response/{call_sid}",
                    timeout=5
                )

            return self.twilio_manager.generate_speech_gather_twiml(
                speech_text=ai_response,
                action_url=f"/webhook/process-speech/{call_sid}",
                timeout=5
            )

        except Exception as e:
            logger.error(f"Error processing conversation turn for {call_sid}: {e}")
            return self._generate_error_twiml("I'm having trouble processing that. Could you repeat?")

    def _should_end_call(self, speech_text: str) -> bool:
        end_phrases = ["goodbye", "bye", "hang up", "end call", "stop", "that's all", "thank you bye", "have to go"]
        return any(phrase in speech_text.lower() for phrase in end_phrases)

    def _generate_error_twiml(self, message: str) -> str:
        return self.twilio_manager.generate_simple_response_twiml(message=f"I apologize, {message}. Thank you for your time.", hangup=True)

    def _generate_hangup_twiml(self, message: str) -> str:
        return self.twilio_manager.generate_simple_response_twiml(message=message, hangup=True)

    def _generate_clarification_twiml(self) -> str:
        return self.twilio_manager.generate_speech_gather_twiml(
            speech_text="I didn't catch that. Could you repeat?",
            action_url="/webhook/clarification",
            timeout=3
        )

    def _generate_transcript(self) -> str:
        return "\n".join([
            f"Customer: {entry['user']}\nAI: {entry['assistant']}"
            for entry in self.ai_engine.conversation_history
        ])

    def _handle_call_termination(self, call_sid: str, speech_text: str) -> str:
        try:
            call_state = self.active_calls[call_sid]
            update_call_record(call_state['call_record_id'], outcome='terminated_by_user')
            return self._generate_hangup_twiml("Thank you for your time. Have a great day!")

        except Exception as e:
            logger.error(f"Error handling call termination for {call_sid}: {e}")
            return self._generate_hangup_twiml("Thank you for your time.")

    def _handle_rejection(self, call_sid: str, speech_text: str) -> str:
        try:
            call_state = self.active_calls.get(call_sid)
            if not call_state:
                logger.warning(f"Rejection received for unknown call SID: {call_sid}")
                return self._generate_hangup_twiml("Thanks for your time. Goodbye!")

            lead_info = call_state['lead_info']
            update_lead(lead_info['id'], status='not_interested')
            update_call_record(call_state['call_record_id'], outcome='rejected')

            logger.info(f"Call {call_sid} rejected by user.")
            return self._generate_hangup_twiml("Understood. Thank you for your time, and have a great day!")

        except Exception as e:
            logger.error(f"Error handling rejection for {call_sid}: {e}")
            return self._generate_hangup_twiml("Thanks again for your time. Goodbye!")

    def _handle_meeting_request(self, call_sid: str, speech_text: str) -> str:
        try:
            call_state = self.active_calls.get(call_sid)
            if not call_state:
                logger.warning(f"Meeting request received for unknown call SID: {call_sid}")
                return self._generate_hangup_twiml("Sorry, there was an issue scheduling. Goodbye.")

            lead_info = call_state['lead_info']
            ai_response = self.ai_engine.generate_response(speech_text, force_stage="closing")

            try:
                meeting_info = self.meet_scheduler.schedule_meeting(lead_info, preferred_time=None)

                update_lead(lead_info['id'], status='meeting_scheduled')
                update_call_record(
                    call_state['call_record_id'],
                    outcome='meeting_scheduled',
                    google_meet_link=meeting_info.get('meet_link', ''),
                    notes=f"Meeting scheduled: {meeting_info.get('meeting_time', '')}"
                )

                self.call_metrics["meetings_scheduled"] += 1

                try:
                    results = notification_service.send_meeting_notifications(lead_info, meeting_info)
                    if results.get('email_sent'):
                        logger.info("Email sent")
                    if results.get('sms_sent'):
                        logger.info("SMS sent")
                except Exception as notify_err:
                    logger.error(f"Notification error: {notify_err}")

                logger.info(f"Meeting scheduled for {lead_info['name']}: {meeting_info.get('meet_link')}")
                return self._generate_hangup_twiml("Great! A meeting has been scheduled and you’ll receive an invite soon. Thank you!")

            except Exception as meet_err:
                logger.error(f"Meeting scheduling failed: {meet_err}")
                update_lead(lead_info['id'], status='interested')
                update_call_record(call_state['call_record_id'], outcome='interested')

                return self._generate_hangup_twiml("I'd love to schedule that, but we ran into a technical issue. We'll follow up with details soon.")

        except Exception as e:
            logger.error(f"Error handling meeting request for {call_sid}: {e}")
            return self._generate_hangup_twiml("Thanks for your interest. We'll be in touch soon.")

    def handle_call_completed(self, call_sid: str, call_duration: int = 0):
        try:
            call_record = get_call_record_by_sid(call_sid)
            if not call_record:
                logger.warning(f"No call record found for SID: {call_sid}")
                return

            call_state = self.active_calls.get(call_sid)

            updates = {
                "status": "completed",
                "duration": call_duration
            }

            if call_state:
                updates["transcript"] = self._generate_transcript()
                updates["ai_summary"] = str(self.ai_engine.get_call_summary())

                del self.active_calls[call_sid]

            update_call_record(call_record.id, **updates)

            logger.info(f"Call {call_sid} completed. Duration: {call_duration}s")

        except Exception as e:
            logger.error(f"Error handling call completion for {call_sid}: {e}")

    def get_call_metrics(self) -> Dict:
        metrics = self.call_metrics.copy()
        metrics["success_rate"] = round((metrics["successful_calls"] / metrics["total_calls"]) * 100, 1) if metrics["total_calls"] else 0
        metrics["meeting_rate"] = round((metrics["meetings_scheduled"] / metrics["total_calls"]) * 100, 1) if metrics["total_calls"] else 0
        metrics["avg_call_duration"] = round(metrics["call_duration_total"] / metrics["successful_calls"], 1) if metrics["successful_calls"] else 0
        metrics["active_calls"] = len(self.active_calls)
        return metrics


class _CallOrchestratorWrapper:
    def __init__(self):
        self._instance = None

    def _get_instance(self):
        if self._instance is None:
            self._instance = CallOrchestrator()
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_instance(), name)

    def __call__(self, *args, **kwargs):
        return self._get_instance()(*args, **kwargs)


call_orchestrator = _CallOrchestratorWrapper()
__all__ = ['CallOrchestrator', 'call_orchestrator']
