"""
AI conversation engine using Groq for natural dialogue
"""
import os
import re
from typing import Dict, List, Optional, Tuple
from groq import Groq
from config.prompts import COLD_CALL_PROMPTS, RESPONSE_TEMPLATES, VOICE_PERSONALITIES
from config.credentials import credential_manager
from utils.logger import get_logger

logger = get_logger(__name__)

class AICallEngine:
    """AI engine for managing cold call conversations"""
    
    def __init__(self, voice: str = "af_sarah"):
        """Initialize AI engine with Groq client"""
        self.groq_client = Groq(api_key=credential_manager.get_groq_api_key())
        self.conversation_history: List[Dict[str, str]] = []
        self.voice = voice
        self.call_stage = "greeting"
        self.lead_info: Dict = {}
        self.conversation_context = {
            "objections_raised": [],
            "interests_mentioned": [],
            "pain_points": [],
            "meeting_interest_level": 0
        }
    
    def set_lead_info(self, lead_info: Dict):
        """Set lead information for personalized responses"""
        self.lead_info = lead_info
        logger.info(f"Lead info set for {lead_info.get('name', 'Unknown')}")
    
    def reset_conversation(self):
        """Reset conversation state for new call"""
        self.conversation_history = []
        self.call_stage = "greeting"
        self.conversation_context = {
            "objections_raised": [],
            "interests_mentioned": [],
            "pain_points": [],
            "meeting_interest_level": 0
        }
        logger.info("Conversation state reset")
    
    def generate_response(self, user_input: str, force_stage: Optional[str] = None) -> str:
        """Generate AI response based on user input and conversation context"""
        try:
            # Use forced stage or current stage
            stage = force_stage or self.call_stage
            
            # Analyze user input for context
            self._analyze_user_input(user_input)
            
            # Get system prompt for current stage
            system_prompt = self._build_system_prompt(stage)
            
            # Build message history
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add recent conversation history (last 6 exchanges)
            for exchange in self.conversation_history[-6:]:
                messages.append({"role": "user", "content": exchange["user"]})
                messages.append({"role": "assistant", "content": exchange["assistant"]})
            
            # Add current user input
            messages.append({"role": "user", "content": user_input})
            
            # Generate response using Groq
            response = self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=0.7,
                max_completion_tokens=150,
                top_p=0.9,
                stream=False
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # Post-process response
            ai_response = self._post_process_response(ai_response)
            
            # Save to conversation history
            self.conversation_history.append({
                "user": user_input,
                "assistant": ai_response,
                "stage": stage
            })
            
            # Maybe advance conversation stage
            self._maybe_advance_stage(user_input, ai_response)
            
            logger.info(f"Generated response in {stage} stage: {ai_response[:50]}...")
            return ai_response
            
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            return self._get_fallback_response(user_input)
    
    def _build_system_prompt(self, stage: str) -> str:
        """Build system prompt for current stage"""
        base_prompt = COLD_CALL_PROMPTS.get(stage, COLD_CALL_PROMPTS["greeting"])
        
        # Personalize with lead info
        prompt = base_prompt.format(
            lead_name=self.lead_info.get('name', 'there'),
            company=self.lead_info.get('company', 'your company')
        )
        
        # Add voice personality
        if self.voice in VOICE_PERSONALITIES:
            prompt += f"\n\nPersonality: {VOICE_PERSONALITIES[self.voice]}"
        
        # Add conversation context if available
        if self.conversation_context['objections_raised']:
            prompt += f"\n\nPrevious objections raised: {', '.join(self.conversation_context['objections_raised'])}"
        
        if self.conversation_context['interests_mentioned']:
            prompt += f"\n\nCustomer interests: {', '.join(self.conversation_context['interests_mentioned'])}"
        
        return prompt
    
    def _analyze_user_input(self, user_input: str):
        """Analyze user input to update conversation context"""
        user_lower = user_input.lower()
        
        # Detect objections
        objection_keywords = [
            "expensive", "cost", "budget", "money", "price",
            "busy", "time", "later", "not now",
            "happy with", "already have", "satisfied",
            "not interested", "don't need"
        ]
        
        for keyword in objection_keywords:
            if keyword in user_lower and keyword not in self.conversation_context['objections_raised']:
                self.conversation_context['objections_raised'].append(keyword)
        
        # Detect interests
        interest_keywords = [
            "efficiency", "save time", "automation", "streamline",
            "ROI", "cost saving", "productivity", "scale"
        ]
        
        for keyword in interest_keywords:
            if keyword in user_lower and keyword not in self.conversation_context['interests_mentioned']:
                self.conversation_context['interests_mentioned'].append(keyword)
        
        # Detect meeting interest
        meeting_positive = ["yes", "sure", "interested", "sounds good", "tell me more", "schedule"]
        meeting_negative = ["no", "not interested", "busy", "can't"]
        
        if any(word in user_lower for word in meeting_positive):
            self.conversation_context['meeting_interest_level'] += 1
        elif any(word in user_lower for word in meeting_negative):
            self.conversation_context['meeting_interest_level'] -= 1
    
    def _post_process_response(self, response: str) -> str:
        """Clean up and validate AI response"""
        # Remove any unwanted characters or formatting
        response = re.sub(r'\*+', '', response)  # Remove markdown asterisks
        response = re.sub(r'\n+', ' ', response)  # Replace newlines with spaces
        response = response.strip()
        
        # Ensure response isn't too long (for phone calls)
        if len(response) > 300:
            sentences = response.split('. ')
            response = '. '.join(sentences[:2]) + '.'
        
        # Ensure response ends with proper punctuation
        if response and response[-1] not in '.!?':
            response += '.'
        
        return response
    
    def _maybe_advance_stage(self, user_input: str, ai_response: str):
        """Determine if conversation should advance to next stage"""
        conversation_turns = len(self.conversation_history)
        
        if self.call_stage == "greeting":
            # Advance after successful greeting exchange
            if conversation_turns >= 1 and not self.detect_rejection(user_input):
                self.call_stage = "pitch"
                logger.info("Advanced to pitch stage")
        
        elif self.call_stage == "pitch":
            # Advance to objection handling if objections raised or after 2-3 exchanges
            if self.conversation_context['objections_raised'] or conversation_turns >= 3:
                self.call_stage = "objection_handling"
                logger.info("Advanced to objection handling stage")
        
        elif self.call_stage == "objection_handling":
            # Advance to closing after handling objections or extended conversation
            if conversation_turns >= 5:
                self.call_stage = "closing"
                logger.info("Advanced to closing stage")
    
    def detect_meeting_intent(self, user_input: str) -> bool:
        """Detect if user wants to schedule a meeting"""
        positive_indicators = [
            "yes", "sure", "sounds good", "interested", "schedule", 
            "meeting", "call", "discuss", "learn more", "okay",
            "show me", "demo", "presentation", "tell me more"
        ]
        
        user_lower = user_input.lower()
        
        # Check for explicit positive responses
        explicit_positive = any(indicator in user_lower for indicator in positive_indicators)
        
        # Check meeting interest level from conversation context
        high_interest = self.conversation_context['meeting_interest_level'] >= 2
        
        return explicit_positive or high_interest
    
    def detect_rejection(self, user_input: str) -> bool:
        """Detect if user is rejecting the call or offer"""
        rejection_indicators = [
            "no", "not interested", "remove", "stop calling", "busy", 
            "hang up", "don't call", "unsubscribe", "not right now",
            "can't talk", "bad time", "call back", "not available"
        ]
        
        user_lower = user_input.lower()
        return any(indicator in user_lower for indicator in rejection_indicators)
    
    def detect_objection_type(self, user_input: str) -> Optional[str]:
        """Detect specific type of objection"""
        user_lower = user_input.lower()
        
        if any(word in user_lower for word in ["expensive", "cost", "budget", "money", "price"]):
            return "price"
        elif any(word in user_lower for word in ["busy", "time", "later", "not now"]):
            return "time"
        elif any(word in user_lower for word in ["happy with", "already have", "satisfied"]):
            return "competition"
        elif any(word in user_lower for word in ["not interested", "don't need"]):
            return "need"
        
        return None
    
    def get_call_summary(self) -> Dict:
        """Generate summary of the call for records"""
        return {
            "total_exchanges": len(self.conversation_history),
            "final_stage": self.call_stage,
            "objections_raised": self.conversation_context['objections_raised'],
            "interests_mentioned": self.conversation_context['interests_mentioned'],
            "meeting_interest_level": self.conversation_context['meeting_interest_level'],
            "outcome": self._determine_call_outcome()
        }
    
    def _determine_call_outcome(self) -> str:
        """Determine the outcome of the call"""
        if self.conversation_context['meeting_interest_level'] >= 2:
            return "meeting_scheduled"
        elif self.conversation_context['meeting_interest_level'] >= 1:
            return "interested"
        elif self.conversation_context['objections_raised']:
            return "objections_raised"
        elif len(self.conversation_history) < 2:
            return "hung_up_early"
        else:
            return "completed"
    
    def _get_fallback_response(self, user_input: str) -> str:
        """Get fallback response when AI generation fails"""
        if self.detect_rejection(user_input):
            return RESPONSE_TEMPLATES["not_interested"]
        elif "busy" in user_input.lower():
            return RESPONSE_TEMPLATES["too_busy"]
        else:
            return "I apologize, could you repeat that? I want to make sure I understand correctly."

# Export main class
__all__ = ['AICallEngine']