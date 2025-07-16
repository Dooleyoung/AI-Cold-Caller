"""
Database CRUD operations for AI Cold Calling System
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import create_engine, and_, or_, desc
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from database.models import Base, Lead, CallRecord, CallQueue, Campaign, SystemConfig
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Database setup
engine = create_engine(settings.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

def create_tables():
    """Create all database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise

def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        db.close()
        raise

# Lead CRUD operations
def create_lead(
    name: str, 
    phone: str, 
    email: str = None, 
    company: str = None,
    industry: str = None,
    title: str = None,
    priority: int = 1,
    source: str = "manual",
    notes: str = None
) -> Optional[Lead]:
    """Create a new lead"""
    db = get_db()
    try:
        # Check if lead with this phone already exists
        existing_lead = db.query(Lead).filter(Lead.phone == phone).first()
        if existing_lead:
            logger.warning(f"Lead with phone {phone} already exists")
            return existing_lead
        
        lead = Lead(
            name=name,
            phone=phone,
            email=email,
            company=company,
            industry=industry,
            title=title,
            priority=priority,
            source=source,
            notes=notes
        )
        
        db.add(lead)
        db.commit()
        db.refresh(lead)
        
        logger.info(f"Created lead: {name} ({phone})")
        return lead
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating lead: {e}")
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating lead: {e}")
        return None
    finally:
        db.close()

def get_lead(lead_id: int) -> Optional[Lead]:
    """Get lead by ID"""
    db = get_db()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        return lead
    except Exception as e:
        logger.error(f"Error getting lead {lead_id}: {e}")
        return None
    finally:
        db.close()

def get_lead_by_phone(phone: str) -> Optional[Lead]:
    """Get lead by phone number"""
    db = get_db()
    try:
        lead = db.query(Lead).filter(Lead.phone == phone).first()
        return lead
    except Exception as e:
        logger.error(f"Error getting lead by phone {phone}: {e}")
        return None
    finally:
        db.close()

def get_all_leads(
    status: str = None, 
    limit: int = None, 
    offset: int = 0,
    order_by: str = "created_at"
) -> List[Lead]:
    """Get all leads with optional filtering"""
    db = get_db()
    try:
        query = db.query(Lead)
        
        if status:
            query = query.filter(Lead.status == status)
        
        # Order by
        if order_by == "created_at":
            query = query.order_by(desc(Lead.created_at))
        elif order_by == "priority":
            query = query.order_by(desc(Lead.priority), desc(Lead.created_at))
        elif order_by == "name":
            query = query.order_by(Lead.name)
        
        if offset:
            query = query.offset(offset)
        
        if limit:
            query = query.limit(limit)
        
        leads = query.all()
        return leads
        
    except Exception as e:
        logger.error(f"Error getting leads: {e}")
        return []
    finally:
        db.close()

def update_lead(
    lead_id: int, 
    **kwargs
) -> bool:
    """Update lead with provided fields"""
    db = get_db()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            logger.warning(f"Lead {lead_id} not found for update")
            return False
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(lead, key):
                setattr(lead, key, value)
        
        lead.updated_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"Updated lead {lead_id}: {kwargs}")
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating lead {lead_id}: {e}")
        return False
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error updating lead {lead_id}: {e}")
        return False
    finally:
        db.close()

def delete_lead(lead_id: int) -> bool:
    """Delete lead and all related records"""
    db = get_db()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            logger.warning(f"Lead {lead_id} not found for deletion")
            return False
        
        db.delete(lead)
        db.commit()
        
        logger.info(f"Deleted lead {lead_id}")
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting lead {lead_id}: {e}")
        return False
    finally:
        db.close()

# Call Record CRUD operations
def create_call_record(
    lead_id: int,
    twilio_call_sid: str = None,
    status: str = "initiated"
) -> Optional[int]:
    """Create a new call record"""
    db = get_db()
    try:
        call_record = CallRecord(
            lead_id=lead_id,
            twilio_call_sid=twilio_call_sid,
            status=status
        )
        
        db.add(call_record)
        db.commit()
        db.refresh(call_record)
        
        logger.info(f"Created call record for lead {lead_id}: {call_record.id}")
        return call_record.id
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating call record: {e}")
        return None
    finally:
        db.close()

def update_call_record(call_record_id: int, **kwargs) -> bool:
    """Update call record with provided fields"""
    db = get_db()
    try:
        call_record = db.query(CallRecord).filter(CallRecord.id == call_record_id).first()
        if not call_record:
            logger.warning(f"Call record {call_record_id} not found for update")
            return False
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(call_record, key):
                setattr(call_record, key, value)
        
        db.commit()
        logger.info(f"Updated call record {call_record_id}: {kwargs}")
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating call record {call_record_id}: {e}")
        return False
    finally:
        db.close()

def get_call_record_by_sid(call_sid: str) -> Optional[CallRecord]:
    """Get call record by Twilio call SID"""
    db = get_db()
    try:
        call_record = db.query(CallRecord).filter(CallRecord.twilio_call_sid == call_sid).first()
        return call_record
    except Exception as e:
        logger.error(f"Error getting call record by SID {call_sid}: {e}")
        return None
    finally:
        db.close()

def get_call_records(lead_id: int = None, limit: int = None) -> List[CallRecord]:
    """Get call records with proper relationship loading"""
    db = get_db()
    try:
        from sqlalchemy.orm import joinedload

        query = db.query(CallRecord).options(joinedload(CallRecord.lead))

        if lead_id:
            query = query.filter(CallRecord.lead_id == lead_id)

        query = query.order_by(desc(CallRecord.called_at))

        if limit:
            query = query.limit(limit)

        records = query.all()

        # ❌ DO NOT expunge lead objects
        for record in records:
            db.expunge(record)

        return records

    except Exception as e:
        logger.error(f"Error getting call records: {e}")
        return []
    finally:
        db.close()


# Call Queue CRUD operations
def add_to_call_queue(
    lead_id: int,
    scheduled_time: datetime,
    priority: int = 1,
    max_attempts: int = 3,
    notes: str = None
) -> Optional[int]:
    """Add lead to call queue"""
    db = get_db()
    try:
        # Check if lead already in queue
        existing = db.query(CallQueue).filter(
            and_(CallQueue.lead_id == lead_id, CallQueue.status == 'pending')
        ).first()
        
        if existing:
            logger.warning(f"Lead {lead_id} already in call queue")
            return existing.id
        
        queue_entry = CallQueue(
            lead_id=lead_id,
            scheduled_time=scheduled_time,
            priority=priority,
            max_attempts=max_attempts,
            notes=notes
        )
        
        db.add(queue_entry)
        db.commit()
        db.refresh(queue_entry)
        
        logger.info(f"Added lead {lead_id} to call queue for {scheduled_time}")
        return queue_entry.id
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error adding to call queue: {e}")
        return None
    finally:
        db.close()

def get_pending_calls(limit: int = 50) -> List[CallQueue]:
    """Get pending calls from queue"""
    db = get_db()
    try:
        now = datetime.utcnow()
        
        pending_calls = db.query(CallQueue).filter(
            and_(
                CallQueue.status == 'pending',
                CallQueue.scheduled_time <= now,
                CallQueue.attempts < CallQueue.max_attempts
            )
        ).order_by(
            desc(CallQueue.priority),
            CallQueue.scheduled_time
        ).limit(limit).all()
        
        return pending_calls
        
    except Exception as e:
        logger.error(f"Error getting pending calls: {e}")
        return []
    finally:
        db.close()

def update_queue_entry(queue_id: int, **kwargs) -> bool:
    """Update call queue entry"""
    db = get_db()
    try:
        queue_entry = db.query(CallQueue).filter(CallQueue.id == queue_id).first()
        if not queue_entry:
            return False
        
        for key, value in kwargs.items():
            if hasattr(queue_entry, key):
                setattr(queue_entry, key, value)
        
        queue_entry.updated_at = datetime.utcnow()
        
        db.commit()
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating queue entry {queue_id}: {e}")
        return False
    finally:
        db.close()

# Statistics and reporting
# Fix for database/crud.py - Update the get_call_statistics function

def get_call_statistics(days: int = 30) -> Dict[str, Any]:
    """Get call statistics for the last N days"""
    db = get_db()
    try:
        from sqlalchemy import func
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Total calls made
        total_calls = db.query(CallRecord).filter(
            CallRecord.called_at >= cutoff_date
        ).count()
        
        # Calls answered
        answered_calls = db.query(CallRecord).filter(
            and_(
                CallRecord.called_at >= cutoff_date,
                CallRecord.status == 'completed',
                CallRecord.outcome.in_(['answered', 'meeting_scheduled', 'interested'])
            )
        ).count()
        
        # Meetings scheduled
        meetings_scheduled = db.query(CallRecord).filter(
            and_(
                CallRecord.called_at >= cutoff_date,
                CallRecord.outcome == 'meeting_scheduled'
            )
        ).count()
        
        # Average call duration - Fixed the func issue
        avg_duration_result = db.query(
            func.avg(CallRecord.duration)
        ).filter(
            and_(
                CallRecord.called_at >= cutoff_date,
                CallRecord.duration.isnot(None)
            )
        ).scalar()
        
        avg_duration = float(avg_duration_result) if avg_duration_result else 0.0
        
        # Calculate rates
        answer_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0
        meeting_rate = (meetings_scheduled / total_calls * 100) if total_calls > 0 else 0
        
        statistics = {
            'period_days': days,
            'total_calls': total_calls,
            'answered_calls': answered_calls,
            'meetings_scheduled': meetings_scheduled,
            'answer_rate': round(answer_rate, 1),
            'meeting_rate': round(meeting_rate, 1),
            'avg_call_duration': round(avg_duration, 1)
        }
        
        return statistics
        
    except Exception as e:
        logger.error(f"Error getting call statistics: {e}")
        # Return empty stats instead of crashing
        return {
            'period_days': days,
            'total_calls': 0,
            'answered_calls': 0,
            'meetings_scheduled': 0,
            'answer_rate': 0,
            'meeting_rate': 0,
            'avg_call_duration': 0
        }
    finally:
        db.close()

def get_lead_statistics() -> Dict[str, Any]:
    """Get lead statistics"""
    db = get_db()
    try:
        total_leads = db.query(Lead).count()
        
        # Leads by status
        status_counts = {}
        statuses = ['pending', 'calling', 'called', 'scheduled', 'not_interested', 'failed']
        
        for status in statuses:
            count = db.query(Lead).filter(Lead.status == status).count()
            status_counts[status] = count
        
        # Recent leads (last 7 days)
        recent_cutoff = datetime.utcnow() - timedelta(days=7)
        recent_leads = db.query(Lead).filter(Lead.created_at >= recent_cutoff).count()
        
        statistics = {
            'total_leads': total_leads,
            'recent_leads': recent_leads,
            'status_breakdown': status_counts
        }
        
        return statistics
        
    except Exception as e:
        logger.error(f"Error getting lead statistics: {e}")
        return {}
    finally:
        db.close()

# Bulk operations
def bulk_import_leads(leads_data: List[Dict[str, Any]]) -> Dict[str, int]:
    """Bulk import leads from list of dictionaries"""
    db = get_db()
    created_count = 0
    updated_count = 0
    error_count = 0
    
    try:
        for lead_data in leads_data:
            try:
                phone = lead_data.get('phone', '').strip()
                if not phone:
                    error_count += 1
                    continue
                
                # Check if lead exists
                existing_lead = db.query(Lead).filter(Lead.phone == phone).first()
                
                if existing_lead:
                    # Update existing lead
                    for key, value in lead_data.items():
                        if hasattr(existing_lead, key) and value:
                            setattr(existing_lead, key, value)
                    existing_lead.updated_at = datetime.utcnow()
                    updated_count += 1
                else:
                    # Create new lead
                    lead = Lead(**lead_data)
                    db.add(lead)
                    created_count += 1
                
            except Exception as e:
                logger.error(f"Error processing lead data {lead_data}: {e}")
                error_count += 1
                continue
        
        db.commit()
        
        logger.info(f"Bulk import completed: {created_count} created, {updated_count} updated, {error_count} errors")
        
        return {
            'created': created_count,
            'updated': updated_count,
            'errors': error_count
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk import failed: {e}")
        return {'created': 0, 'updated': 0, 'errors': len(leads_data)}
    finally:
        db.close()

# System configuration
def get_config(key: str, default: Any = None) -> Any:
    """Get system configuration value"""
    db = get_db()
    try:
        config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if config:
            # Convert value based on type
            if config.config_type == 'int':
                return int(config.value)
            elif config.config_type == 'float':
                return float(config.value)
            elif config.config_type == 'bool':
                return config.value.lower() in ('true', '1', 'yes')
            elif config.config_type == 'json':
                import json
                return json.loads(config.value)
            else:
                return config.value
        
        return default
        
    except Exception as e:
        logger.error(f"Error getting config {key}: {e}")
        return default
    finally:
        db.close()

def set_config(key: str, value: Any, description: str = None) -> bool:
    """Set system configuration value"""
    db = get_db()
    try:
        config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        
        # Determine type
        config_type = 'string'
        if isinstance(value, int):
            config_type = 'int'
        elif isinstance(value, float):
            config_type = 'float'
        elif isinstance(value, bool):
            config_type = 'bool'
        elif isinstance(value, (dict, list)):
            config_type = 'json'
            import json
            value = json.dumps(value)
        
        if config:
            config.value = str(value)
            config.config_type = config_type
            if description:
                config.description = description
            config.updated_at = datetime.utcnow()
        else:
            config = SystemConfig(
                key=key,
                value=str(value),
                config_type=config_type,
                description=description
            )
            db.add(config)
        
        db.commit()
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting config {key}: {e}")
        return False
    finally:
        db.close()

# Export functions
__all__ = [
    'create_tables', 'get_db',
    'create_lead', 'get_lead', 'get_lead_by_phone', 'get_all_leads', 'update_lead', 'delete_lead',
    'create_call_record', 'update_call_record', 'get_call_record_by_sid', 'get_call_records',
    'add_to_call_queue', 'get_pending_calls', 'update_queue_entry',
    'get_call_statistics', 'get_lead_statistics', 'bulk_import_leads',
    'get_config', 'set_config'
]