"""
Retry handling logic for failed calls
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
from enum import Enum

from database.crud import get_call_records, add_to_call_queue, get_lead, update_lead
from utils.logger import get_logger

logger = get_logger(__name__)

class RetryReason(Enum):
    """Reasons for call retries"""
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    TECHNICAL_ERROR = "technical_error"
    ANSWERING_MACHINE = "answering_machine"

class RetryStrategy:
    """Defines retry strategy parameters"""
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay_hours: int = 2,
        backoff_multiplier: float = 2.0,
        max_delay_hours: int = 48,
        retry_on_outcomes: List[str] = None
    ):
        self.max_attempts = max_attempts
        self.initial_delay_hours = initial_delay_hours
        self.backoff_multiplier = backoff_multiplier
        self.max_delay_hours = max_delay_hours
        self.retry_on_outcomes = retry_on_outcomes or [
            'no_answer', 'busy', 'timeout', 'network_error', 'technical_error'
        ]

class RetryHandler:
    """Handles retry logic for failed calls"""
    
    def __init__(self):
        """Initialize retry handler with different strategies"""
        self.strategies = {
            'standard': RetryStrategy(
                max_attempts=3,
                initial_delay_hours=2,
                backoff_multiplier=2.0,
                max_delay_hours=24
            ),
            'aggressive': RetryStrategy(
                max_attempts=5,
                initial_delay_hours=1,
                backoff_multiplier=1.5,
                max_delay_hours=12
            ),
            'conservative': RetryStrategy(
                max_attempts=2,
                initial_delay_hours=4,
                backoff_multiplier=3.0,
                max_delay_hours=48
            ),
            'high_value': RetryStrategy(
                max_attempts=4,
                initial_delay_hours=1,
                backoff_multiplier=1.8,
                max_delay_hours=24,
                retry_on_outcomes=['no_answer', 'busy', 'timeout', 'network_error', 'technical_error', 'answering_machine']
            )
        }
        
        logger.info("RetryHandler initialized with strategies")
    
    def should_retry_call(
        self, 
        lead_id: int, 
        call_outcome: str, 
        current_attempts: int = 1,
        strategy_name: str = 'standard'
    ) -> bool:
        """Determine if a call should be retried"""
        
        try:
            strategy = self.strategies.get(strategy_name, self.strategies['standard'])
            
            # Check if we've exceeded max attempts
            if current_attempts >= strategy.max_attempts:
                logger.info(f"Lead {lead_id}: Max attempts ({strategy.max_attempts}) reached")
                return False
            
            # Check if outcome is retryable
            if call_outcome not in strategy.retry_on_outcomes:
                logger.info(f"Lead {lead_id}: Outcome '{call_outcome}' not retryable")
                return False
            
            # Get lead to check business rules
            lead = get_lead(lead_id)
            if not lead:
                logger.warning(f"Lead {lead_id} not found")
                return False
            
            # Don't retry if lead status indicates no interest
            if lead.status in ['not_interested', 'scheduled', 'completed']:
                logger.info(f"Lead {lead_id}: Status '{lead.status}' prevents retry")
                return False
            
            logger.info(f"Lead {lead_id}: Retry approved for outcome '{call_outcome}' (attempt {current_attempts + 1})")
            return True
            
        except Exception as e:
            logger.error(f"Error determining retry for lead {lead_id}: {e}")
            return False
    
    def calculate_retry_time(
        self, 
        attempt_number: int, 
        strategy_name: str = 'standard',
        base_time: datetime = None
    ) -> datetime:
        """Calculate when the next retry should occur"""
        
        try:
            strategy = self.strategies.get(strategy_name, self.strategies['standard'])
            base_time = base_time or datetime.utcnow()
            
            # Calculate delay with exponential backoff
            delay_hours = strategy.initial_delay_hours * (strategy.backoff_multiplier ** (attempt_number - 1))
            
            # Cap at maximum delay
            delay_hours = min(delay_hours, strategy.max_delay_hours)
            
            # Add some randomization to prevent thundering herd
            import random
            jitter_minutes = random.randint(-30, 30)
            
            retry_time = base_time + timedelta(hours=delay_hours, minutes=jitter_minutes)
            
            # Ensure retry is during business hours if it's a business day
            retry_time = self._adjust_for_business_hours(retry_time)
            
            logger.info(f"Calculated retry time: {retry_time} (delay: {delay_hours:.1f}h)")
            return retry_time
            
        except Exception as e:
            logger.error(f"Error calculating retry time: {e}")
            # Fallback to 2 hours from now
            return (base_time or datetime.utcnow()) + timedelta(hours=2)
    
    def schedule_retry(
        self, 
        lead_id: int, 
        call_outcome: str, 
        current_attempts: int = 1,
        strategy_name: str = 'standard',
        notes: str = None
    ) -> bool:
        """Schedule a retry for a failed call"""
        
        try:
            # Check if retry is appropriate
            if not self.should_retry_call(lead_id, call_outcome, current_attempts, strategy_name):
                return False
            
            # Calculate retry time
            retry_time = self.calculate_retry_time(current_attempts + 1, strategy_name)
            
            # Get priority based on strategy and attempt number
            priority = self._calculate_retry_priority(strategy_name, current_attempts)
            
            # Schedule the retry
            retry_notes = notes or f"Retry #{current_attempts + 1} for outcome: {call_outcome}"
            
            queue_id = add_to_call_queue(
                lead_id=lead_id,
                scheduled_time=retry_time,
                priority=priority,
                max_attempts=self.strategies[strategy_name].max_attempts,
                notes=retry_notes
            )
            
            if queue_id:
                logger.info(f"Scheduled retry for lead {lead_id} at {retry_time}")
                return True
            else:
                logger.error(f"Failed to schedule retry for lead {lead_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error scheduling retry for lead {lead_id}: {e}")
            return False
    
    def process_failed_calls(self, hours_lookback: int = 24) -> Dict[str, int]:
        """Process recent failed calls and schedule retries"""
        
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_lookback)
            
            # Get recent failed calls
            call_records = get_call_records(limit=1000)
            failed_calls = [
                record for record in call_records
                if (record.called_at and record.called_at >= cutoff_time and
                    record.outcome in ['no_answer', 'busy', 'timeout', 'network_error', 'technical_error'])
            ]
            
            retry_stats = {
                'processed': 0,
                'retries_scheduled': 0,
                'max_attempts_reached': 0,
                'not_retryable': 0
            }
            
            for call_record in failed_calls:
                retry_stats['processed'] += 1
                
                # Count existing attempts for this lead
                lead_call_count = len([
                    r for r in call_records 
                    if r.lead_id == call_record.lead_id
                ])
                
                # Determine strategy based on lead priority
                lead = get_lead(call_record.lead_id)
                strategy_name = 'standard'
                if lead:
                    if lead.priority >= 3:
                        strategy_name = 'aggressive'
                    elif lead.priority <= 1:
                        strategy_name = 'conservative'
                
                # Schedule retry
                if self.schedule_retry(
                    call_record.lead_id,
                    call_record.outcome,
                    lead_call_count,
                    strategy_name,
                    f"Auto-retry from failed call {call_record.id}"
                ):
                    retry_stats['retries_scheduled'] += 1
                else:
                    if lead_call_count >= self.strategies[strategy_name].max_attempts:
                        retry_stats['max_attempts_reached'] += 1
                    else:
                        retry_stats['not_retryable'] += 1
            
            logger.info(f"Processed failed calls: {retry_stats}")
            return retry_stats
            
        except Exception as e:
            logger.error(f"Error processing failed calls: {e}")
            return {'processed': 0, 'retries_scheduled': 0, 'max_attempts_reached': 0, 'not_retryable': 0}
    
    def _adjust_for_business_hours(self, target_time: datetime) -> datetime:
        """Adjust retry time to fall within business hours"""
        
        # Define business hours (9 AM to 5 PM, Monday-Friday)
        business_start = 9
        business_end = 17
        
        # If it's a weekend, move to Monday
        if target_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
            days_until_monday = 7 - target_time.weekday()
            target_time = target_time + timedelta(days=days_until_monday)
            target_time = target_time.replace(hour=business_start, minute=0, second=0, microsecond=0)
        
        # If it's before business hours, move to business start
        elif target_time.hour < business_start:
            target_time = target_time.replace(hour=business_start, minute=0, second=0, microsecond=0)
        
        # If it's after business hours, move to next business day
        elif target_time.hour >= business_end:
            if target_time.weekday() == 4:  # Friday
                target_time = target_time + timedelta(days=3)  # Move to Monday
            else:
                target_time = target_time + timedelta(days=1)  # Move to next day
            target_time = target_time.replace(hour=business_start, minute=0, second=0, microsecond=0)
        
        return target_time
    
    def _calculate_retry_priority(self, strategy_name: str, attempt_number: int) -> int:
        """Calculate priority for retry based on strategy and attempt"""
        
        base_priority = 1
        
        if strategy_name == 'aggressive':
            base_priority = 2
        elif strategy_name == 'high_value':
            base_priority = 3
        
        # Increase priority with each attempt (up to max of 3)
        priority = min(base_priority + attempt_number - 1, 3)
        
        return priority
    
    def get_retry_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Get retry statistics for the specified period"""
        
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=days)
            
            # Get all call records in the period
            call_records = get_call_records(limit=10000)
            period_calls = [
                record for record in call_records
                if record.called_at and record.called_at >= cutoff_time
            ]
            
            # Group by lead to count attempts
            lead_attempts = {}
            for record in period_calls:
                if record.lead_id not in lead_attempts:
                    lead_attempts[record.lead_id] = []
                lead_attempts[record.lead_id].append(record)
            
            # Calculate statistics
            total_leads_called = len(lead_attempts)
            leads_with_retries = len([attempts for attempts in lead_attempts.values() if len(attempts) > 1])
            total_retry_attempts = sum(len(attempts) - 1 for attempts in lead_attempts.values())
            
            # Success rate after retries
            successful_after_retry = 0
            for attempts in lead_attempts.values():
                if len(attempts) > 1:  # Had retries
                    last_call = max(attempts, key=lambda x: x.called_at)
                    if last_call.outcome in ['meeting_scheduled', 'interested', 'answered']:
                        successful_after_retry += 1
            
            retry_success_rate = (successful_after_retry / leads_with_retries * 100) if leads_with_retries > 0 else 0
            
            statistics = {
                'period_days': days,
                'total_leads_called': total_leads_called,
                'leads_with_retries': leads_with_retries,
                'total_retry_attempts': total_retry_attempts,
                'retry_success_rate': round(retry_success_rate, 1),
                'avg_attempts_per_lead': round(sum(len(attempts) for attempts in lead_attempts.values()) / total_leads_called, 1) if total_leads_called > 0 else 0
            }
            
            return statistics
            
        except Exception as e:
            logger.error(f"Error getting retry statistics: {e}")
            return {}

# Global retry handler instance
retry_handler = RetryHandler()

# Export
__all__ = ['RetryReason', 'RetryStrategy', 'RetryHandler', 'retry_handler']