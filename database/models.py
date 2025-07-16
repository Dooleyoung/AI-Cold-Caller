"""
SQLAlchemy database models for the AI Cold Calling System
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Lead(Base):
    """Lead/prospect model"""
    __tablename__ = 'leads'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False, unique=True)
    email = Column(String(100))
    company = Column(String(100))
    industry = Column(String(50))
    title = Column(String(100))
    status = Column(String(20), default='pending')  # pending, calling, called, scheduled, failed, not_interested
    priority = Column(Integer, default=1)  # 1=low, 2=medium, 3=high
    source = Column(String(50))  # csv_import, manual, api, etc.
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_called = Column(DateTime)
    
    # Relationships
    call_records = relationship("CallRecord", back_populates="lead", cascade="all, delete-orphan")
    queue_entries = relationship("CallQueue", back_populates="lead", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Lead(id={self.id}, name='{self.name}', phone='{self.phone}', status='{self.status}')>"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'company': self.company,
            'industry': self.industry,
            'title': self.title,
            'status': self.status,
            'priority': self.priority,
            'source': self.source,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_called': self.last_called.isoformat() if self.last_called else None
        }

class CallRecord(Base):
    """Call record model"""
    __tablename__ = 'call_records'
    
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey('leads.id'), nullable=False)
    twilio_call_sid = Column(String(50), unique=True)
    
    # Call details
    status = Column(String(20), default='initiated')  # initiated, ringing, answered, completed, failed
    duration = Column(Integer)  # seconds
    outcome = Column(String(30))  # answered, no_answer, busy, meeting_scheduled, rejected, etc.
    
    # Conversation data
    transcript = Column(Text)
    ai_summary = Column(Text)
    conversation_turns = Column(Integer, default=0)
    engagement_score = Column(Float)
    
    # Meeting info
    google_meet_link = Column(String(200))
    meeting_scheduled_time = Column(DateTime)
    
    # Timestamps
    called_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime)
    ended_at = Column(DateTime)
    
    # Metadata
    notes = Column(Text)
    recording_url = Column(String(200))
    
    # Relationships
    lead = relationship("Lead", back_populates="call_records")
    
    def __repr__(self):
        return f"<CallRecord(id={self.id}, lead_id={self.lead_id}, status='{self.status}', outcome='{self.outcome}')>"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'lead_id': self.lead_id,
            'twilio_call_sid': self.twilio_call_sid,
            'status': self.status,
            'duration': self.duration,
            'outcome': self.outcome,
            'transcript': self.transcript,
            'ai_summary': self.ai_summary,
            'conversation_turns': self.conversation_turns,
            'engagement_score': self.engagement_score,
            'google_meet_link': self.google_meet_link,
            'meeting_scheduled_time': self.meeting_scheduled_time.isoformat() if self.meeting_scheduled_time else None,
            'called_at': self.called_at.isoformat() if self.called_at else None,
            'answered_at': self.answered_at.isoformat() if self.answered_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'notes': self.notes,
            'recording_url': self.recording_url
        }

class CallQueue(Base):
    """Call queue model for scheduled calls"""
    __tablename__ = 'call_queue'
    
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey('leads.id'), nullable=False)
    
    # Scheduling
    scheduled_time = Column(DateTime, nullable=False)
    priority = Column(Integer, default=1)  # 1=low, 2=medium, 3=high
    
    # Retry logic
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    last_attempt = Column(DateTime)
    
    # Status
    status = Column(String(20), default='pending')  # pending, processing, completed, failed, cancelled
    
    # Metadata
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    lead = relationship("Lead", back_populates="queue_entries")
    
    def __repr__(self):
        return f"<CallQueue(id={self.id}, lead_id={self.lead_id}, scheduled_time={self.scheduled_time}, status='{self.status}')>"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'lead_id': self.lead_id,
            'scheduled_time': self.scheduled_time.isoformat() if self.scheduled_time else None,
            'priority': self.priority,
            'attempts': self.attempts,
            'max_attempts': self.max_attempts,
            'last_attempt': self.last_attempt.isoformat() if self.last_attempt else None,
            'status': self.status,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Campaign(Base):
    """Campaign model for organizing calling campaigns"""
    __tablename__ = 'campaigns'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    
    # Campaign settings
    voice_id = Column(String(20), default='af_sarah')
    max_call_duration = Column(Integer, default=300)  # seconds
    retry_attempts = Column(Integer, default=3)
    retry_delay_hours = Column(Integer, default=24)
    
    # Campaign status
    status = Column(String(20), default='draft')  # draft, active, paused, completed
    
    # Statistics
    total_leads = Column(Integer, default=0)
    calls_made = Column(Integer, default=0)
    calls_answered = Column(Integer, default=0)
    meetings_scheduled = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    def __repr__(self):
        return f"<Campaign(id={self.id}, name='{self.name}', status='{self.status}')>"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'voice_id': self.voice_id,
            'max_call_duration': self.max_call_duration,
            'retry_attempts': self.retry_attempts,
            'retry_delay_hours': self.retry_delay_hours,
            'status': self.status,
            'total_leads': self.total_leads,
            'calls_made': self.calls_made,
            'calls_answered': self.calls_answered,
            'meetings_scheduled': self.meetings_scheduled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

class SystemConfig(Base):
    """System configuration model"""
    __tablename__ = 'system_config'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, nullable=False)
    value = Column(Text)
    description = Column(Text)
    config_type = Column(String(20), default='string')  # string, int, float, bool, json
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<SystemConfig(key='{self.key}', value='{self.value}')>"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'config_type': self.config_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

# Export all models
__all__ = ['Base', 'Lead', 'CallRecord', 'CallQueue', 'Campaign', 'SystemConfig']