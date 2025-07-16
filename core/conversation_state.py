"""
Conversation state management for tracking call progress
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

class CallStage(Enum):
    """Enumeration of call stages"""
    GREETING = "greeting"
    PITCH = "pitch"
    OBJECTION_HANDLING = "objection_handling"
    CLOSING = "closing"
    MEETING_SCHEDULING = "meeting_scheduling"
    ENDING = "ending"

class CallOutcome(Enum):
    """Enumeration of possible call outcomes"""
    MEETING_SCHEDULED = "meeting_scheduled"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CALLBACK_REQUESTED = "callback_requested"
    HUNG_UP = "hung_up"
    TECHNICAL_ISSUE = "technical_issue"
    WRONG_NUMBER = "wrong_number"
    VOICEMAIL = "voicemail"

@dataclass
class ConversationTurn:
    """Single conversation exchange"""
    timestamp: datetime
    user_input: str
    ai_response: str
    stage: CallStage
    confidence: float = 1.0
    detected_intent: Optional[str] = None
    detected_emotion: Optional[str] = None

@dataclass
class ConversationContext:
    """Conversation context and metadata"""
    lead_id: int
    call_sid: str
    start_time: datetime
    current_stage: CallStage = CallStage.GREETING
    turns: List[ConversationTurn] = field(default_factory=list)
    
    # Intent tracking
    objections_raised: List[str] = field(default_factory=list)
    interests_mentioned: List[str] = field(default_factory=list)
    pain_points: List[str] = field(default_factory=list)
    
    # Engagement metrics
    meeting_interest_level: int = 0
    engagement_score: float = 0.0
    sentiment_trend: List[float] = field(default_factory=list)
    
    # Call metadata
    total_duration: int = 0
    user_talking_time: int = 0
    ai_talking_time: int = 0
    
    # Outcomes
    outcome: Optional[CallOutcome] = None
    meeting_scheduled: bool = False
    callback_requested: bool = False
    
    def add_turn(self, user_input: str, ai_response: str, confidence: float = 1.0):
        """Add a conversation turn"""
        turn = ConversationTurn(
            timestamp=datetime.now(),
            user_input=user_input,
            ai_response=ai_response,
            stage=self.current_stage,
            confidence=confidence
        )
        
        self.turns.append(turn)
        self._analyze_turn(turn)
    
    def _analyze_turn(self, turn: ConversationTurn):
        """Analyze conversation turn for insights"""
        user_lower = turn.user_input.lower()
        
        # Detect objections
        objection_patterns = {
            "price": ["expensive", "cost", "budget", "money", "price", "afford"],
            "time": ["busy", "time", "later", "not now", "schedule"],
            "authority": ["decision", "boss", "manager", "team", "discuss"],
            "need": ["don't need", "not interested", "satisfied", "happy with"],
            "trust": ["scam", "sales", "pitch", "suspicious", "legitimate"]
        }
        
        for objection_type, keywords in objection_patterns.items():
            if any(keyword in user_lower for keyword in keywords):
                if objection_type not in self.objections_raised:
                    self.objections_raised.append(objection_type)
        
        # Detect interests
        interest_patterns = {
            "efficiency": ["efficient", "streamline", "optimize", "improve"],
            "cost_saving": ["save money", "reduce cost", "ROI", "return"],
            "time_saving": ["save time", "faster", "quick", "automate"],
            "growth": ["scale", "grow", "expand", "increase"],
            "technology": ["AI", "automation", "digital", "tech"]
        }
        
        for interest_type, keywords in interest_patterns.items():
            if any(keyword in user_lower for keyword in keywords):
                if interest_type not in self.interests_mentioned:
                    self.interests_mentioned.append(interest_type)
        
        # Update meeting interest
        positive_meeting = ["yes", "sure", "interested", "schedule", "meeting", "call"]
        negative_meeting = ["no", "not interested", "busy", "can't"]
        
        if any(word in user_lower for word in positive_meeting):
            self.meeting_interest_level += 1
        elif any(word in user_lower for word in negative_meeting):
            self.meeting_interest_level -= 1
        
        # Simple sentiment analysis
        positive_words = ["good", "great", "excellent", "perfect", "yes", "sure", "love", "like"]
        negative_words = ["no", "bad", "terrible", "hate", "dislike", "wrong", "problem"]
        
        positive_count = sum(1 for word in positive_words if word in user_lower)
        negative_count = sum(1 for word in negative_words if word in user_lower)
        
        if positive_count > 0 or negative_count > 0:
            sentiment = (positive_count - negative_count) / (positive_count + negative_count)
            self.sentiment_trend.append(sentiment)
    
    def advance_stage(self, new_stage: CallStage):
        """Advance to new conversation stage"""
        if new_stage != self.current_stage:
            self.current_stage = new_stage
    
    def calculate_engagement_score(self) -> float:
        """Calculate overall engagement score"""
        if not self.turns:
            return 0.0
        
        # Factors for engagement
        factors = {
            "conversation_length": min(len(self.turns) / 10, 1.0),  # 10 turns = max score
            "meeting_interest": max(0, min(self.meeting_interest_level / 3, 1.0)),
            "avg_confidence": sum(turn.confidence for turn in self.turns) / len(self.turns),
            "sentiment": sum(self.sentiment_trend) / len(self.sentiment_trend) if self.sentiment_trend else 0.0,
            "interests": min(len(self.interests_mentioned) / 3, 1.0)  # 3 interests = max score
        }
        
        # Weighted average
        weights = {
            "conversation_length": 0.2,
            "meeting_interest": 0.3,
            "avg_confidence": 0.2,
            "sentiment": 0.2,
            "interests": 0.1
        }
        
        self.engagement_score = sum(factors[key] * weights[key] for key in factors)
        return self.engagement_score
    
    def should_advance_stage(self) -> Optional[CallStage]:
        """Determine if conversation should advance to next stage"""
        turn_count = len(self.turns)
        
        if self.current_stage == CallStage.GREETING:
            # Advance after successful greeting (1-2 turns)
            if turn_count >= 1 and not self._indicates_rejection():
                return CallStage.PITCH
        
        elif self.current_stage == CallStage.PITCH:
            # Advance if objections raised or after 2-3 turns
            if self.objections_raised or turn_count >= 3:
                return CallStage.OBJECTION_HANDLING
            elif self.meeting_interest_level >= 1:
                return CallStage.CLOSING
        
        elif self.current_stage == CallStage.OBJECTION_HANDLING:
            # Advance to closing after handling objections
            if turn_count >= 5 or self.meeting_interest_level >= 1:
                return CallStage.CLOSING
        
        elif self.current_stage == CallStage.CLOSING:
            # Move to meeting scheduling if interest shown
            if self.meeting_interest_level >= 2:
                return CallStage.MEETING_SCHEDULING
            elif turn_count >= 8:  # End if conversation too long
                return CallStage.ENDING
        
        return None
    
    def _indicates_rejection(self) -> bool:
        """Check if recent turns indicate rejection"""
        if not self.turns:
            return False
        
        recent_turns = self.turns[-2:]  # Last 2 turns
        rejection_keywords = ["no", "not interested", "busy", "hang up", "stop", "remove"]
        
        for turn in recent_turns:
            user_lower = turn.user_input.lower()
            if any(keyword in user_lower for keyword in rejection_keywords):
                return True
        
        return False
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """Get comprehensive conversation summary"""
        return {
            "lead_id": self.lead_id,
            "call_sid": self.call_sid,
            "duration_minutes": round(self.total_duration / 60, 1),
            "total_turns": len(self.turns),
            "final_stage": self.current_stage.value,
            "outcome": self.outcome.value if self.outcome else None,
            "engagement_score": round(self.calculate_engagement_score(), 2),
            "meeting_interest_level": self.meeting_interest_level,
            "objections_raised": self.objections_raised,
            "interests_mentioned": self.interests_mentioned,
            "pain_points": self.pain_points,
            "meeting_scheduled": self.meeting_scheduled,
            "callback_requested": self.callback_requested,
            "avg_sentiment": round(sum(self.sentiment_trend) / len(self.sentiment_trend), 2) if self.sentiment_trend else 0.0
        }

class ConversationStateManager:
    """Manager for conversation states across multiple calls"""
    
    def __init__(self):
        self.active_conversations: Dict[str, ConversationContext] = {}
    
    def start_conversation(self, call_sid: str, lead_id: int) -> ConversationContext:
        """Start new conversation tracking"""
        context = ConversationContext(
            lead_id=lead_id,
            call_sid=call_sid,
            start_time=datetime.now()
        )
        
        self.active_conversations[call_sid] = context
        return context
    
    def get_conversation(self, call_sid: str) -> Optional[ConversationContext]:
        """Get conversation context by call SID"""
        return self.active_conversations.get(call_sid)
    
    def end_conversation(self, call_sid: str, outcome: CallOutcome) -> Optional[ConversationContext]:
        """End conversation and return final context"""
        if call_sid in self.active_conversations:
            context = self.active_conversations[call_sid]
            context.outcome = outcome
            context.total_duration = int((datetime.now() - context.start_time).total_seconds())
            
            # Remove from active conversations
            del self.active_conversations[call_sid]
            
            return context
        
        return None
    
    def get_active_conversation_count(self) -> int:
        """Get number of active conversations"""
        return len(self.active_conversations)
    
    def cleanup_stale_conversations(self, max_age_hours: int = 2):
        """Clean up conversations older than specified hours"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        stale_sids = []
        
        for call_sid, context in self.active_conversations.items():
            if context.start_time < cutoff_time:
                stale_sids.append(call_sid)
        
        for call_sid in stale_sids:
            del self.active_conversations[call_sid]
        
        return len(stale_sids)

# Global conversation state manager
conversation_state_manager = ConversationStateManager()

# Export
__all__ = [
    'CallStage', 'CallOutcome', 'ConversationTurn', 'ConversationContext',
    'ConversationStateManager', 'conversation_state_manager'
]