"""
Call queue management system
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from database.crud import (
    get_pending_calls, add_to_call_queue, update_queue_entry, 
    get_lead, get_all_leads, update_lead
)
from utils.logger import get_logger

logger = get_logger(__name__)

class QueuePriority(Enum):
    """Queue priority levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

@dataclass
class QueuedCall:
    """Represents a call in the queue"""
    queue_id: int
    lead_id: int
    lead_name: str
    phone: str
    scheduled_time: datetime
    priority: int
    attempts: int
    max_attempts: int
    status: str
    notes: str

class CallQueueManager:
    """Manages the call queue and prioritization"""
    
    def __init__(self):
        """Initialize queue manager"""
        self.queue_strategies = {
            'fifo': self._fifo_sort,
            'priority': self._priority_sort,
            'smart': self._smart_sort
        }
        
        logger.info("CallQueueManager initialized")
    
    def get_next_calls(self, limit: int = 10, strategy: str = 'smart') -> List[QueuedCall]:
        """Get next calls to be made using specified strategy"""
        
        try:
            # Get pending calls from database
            pending_entries = get_pending_calls(limit=limit * 2)  # Get more to allow for filtering
            
            if not pending_entries:
                return []
            
            # Convert to QueuedCall objects
            queued_calls = []
            for entry in pending_entries:
                lead = get_lead(entry.lead_id)
                if not lead:
                    continue
                
                queued_call = QueuedCall(
                    queue_id=entry.id,
                    lead_id=entry.lead_id,
                    lead_name=lead.name,
                    phone=lead.phone,
                    scheduled_time=entry.scheduled_time,
                    priority=entry.priority,
                    attempts=entry.attempts,
                    max_attempts=entry.max_attempts,
                    status=entry.status,
                    notes=entry.notes or ""
                )
                
                queued_calls.append(queued_call)
            
            # Apply sorting strategy
            sort_function = self.queue_strategies.get(strategy, self._smart_sort)
            sorted_calls = sort_function(queued_calls)
            
            # Apply business rules filtering
            filtered_calls = self._apply_business_rules(sorted_calls)
            
            # Return limited results
            result = filtered_calls[:limit]
            
            logger.info(f"Retrieved {len(result)} calls using {strategy} strategy")
            return result
            
        except Exception as e:
            logger.error(f"Error getting next calls: {e}")
            return []
    
    def add_leads_to_queue(
        self, 
        lead_ids: List[int], 
        base_time: datetime = None,
        priority: int = 1,
        spread_minutes: int = 5
    ) -> Dict[str, int]:
        """Add multiple leads to call queue with time spreading"""
        
        if not base_time:
            base_time = datetime.utcnow()
        
        results = {
            'added': 0,
            'already_queued': 0,
            'errors': 0
        }
        
        try:
            for i, lead_id in enumerate(lead_ids):
                try:
                    # Spread calls over time to avoid overwhelming
                    scheduled_time = base_time + timedelta(minutes=i * spread_minutes)
                    
                    queue_id = add_to_call_queue(
                        lead_id=lead_id,
                        scheduled_time=scheduled_time,
                        priority=priority,
                        notes=f"Bulk queued at {base_time}"
                    )
                    
                    if queue_id:
                        results['added'] += 1
                    else:
                        results['already_queued'] += 1
                        
                except Exception as e:
                    logger.error(f"Error adding lead {lead_id} to queue: {e}")
                    results['errors'] += 1
            
            logger.info(f"Bulk queue operation completed: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Error in bulk queue operation: {e}")
            return results
    
    def schedule_campaign_calls(
        self, 
        campaign_name: str = "Default Campaign",
        lead_filter: Dict[str, Any] = None,
        start_time: datetime = None,
        calls_per_hour: int = 20,
        business_hours_only: bool = True
    ) -> Dict[str, Any]:
        """Schedule calls for a campaign with rate limiting"""
        
        try:
            # Get leads based on filter
            leads = self._get_filtered_leads(lead_filter or {})
            
            if not leads:
                return {'error': 'No leads found matching filter'}
            
            # Calculate scheduling parameters
            if not start_time:
                start_time = self._get_next_business_time()
            
            minutes_between_calls = 60 / calls_per_hour
            
            scheduled_count = 0
            current_time = start_time
            
            for lead in leads:
                try:
                    # Skip if lead already has pending calls
                    existing_queue = get_pending_calls(limit=1000)
                    if any(entry.lead_id == lead.id for entry in existing_queue):
                        continue
                    
                    # Determine priority based on lead characteristics
                    priority = self._calculate_lead_priority(lead)
                    
                    # Schedule the call
                    queue_id = add_to_call_queue(
                        lead_id=lead.id,
                        scheduled_time=current_time,
                        priority=priority,
                        notes=f"Campaign: {campaign_name}"
                    )
                    
                    if queue_id:
                        scheduled_count += 1
                        logger.debug(f"Scheduled call for {lead.name} at {current_time}")
                    
                    # Calculate next call time
                    current_time += timedelta(minutes=minutes_between_calls)
                    
                    # Adjust for business hours if needed
                    if business_hours_only:
                        current_time = self._adjust_for_business_hours(current_time)
                    
                except Exception as e:
                    logger.error(f"Error scheduling call for lead {lead.id}: {e}")
                    continue
            
            result = {
                'campaign_name': campaign_name,
                'total_leads': len(leads),
                'scheduled_calls': scheduled_count,
                'start_time': start_time.isoformat(),
                'estimated_completion': current_time.isoformat(),
                'calls_per_hour': calls_per_hour
            }
            
            logger.info(f"Campaign scheduled: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error scheduling campaign: {e}")
            return {'error': str(e)}
    
    def get_queue_statistics(self) -> Dict[str, Any]:
        """Get comprehensive queue statistics"""
        
        try:
            # Get all pending calls
            pending_calls = get_pending_calls(limit=10000)
            
            # Basic counts
            total_pending = len(pending_calls)
            
            # Priority breakdown
            priority_counts = {}
            for call in pending_calls:
                priority = call.priority
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
            # Time-based analysis
            now = datetime.utcnow()
            overdue = len([call for call in pending_calls if call.scheduled_time < now])
            next_hour = len([call for call in pending_calls if call.scheduled_time < now + timedelta(hours=1)])
            next_day = len([call for call in pending_calls if call.scheduled_time < now + timedelta(days=1)])
            
            # Retry analysis
            retry_calls = len([call for call in pending_calls if call.attempts > 0])
            avg_attempts = sum(call.attempts for call in pending_calls) / total_pending if total_pending > 0 else 0
            
            # Earliest and latest scheduled times
            earliest_call = min(pending_calls, key=lambda x: x.scheduled_time) if pending_calls else None
            latest_call = max(pending_calls, key=lambda x: x.scheduled_time) if pending_calls else None
            
            statistics = {
                'total_pending': total_pending,
                'overdue_calls': overdue,
                'calls_next_hour': next_hour,
                'calls_next_day': next_day,
                'retry_calls': retry_calls,
                'avg_attempts': round(avg_attempts, 1),
                'priority_breakdown': priority_counts,
                'earliest_scheduled': earliest_call.scheduled_time.isoformat() if earliest_call else None,
                'latest_scheduled': latest_call.scheduled_time.isoformat() if latest_call else None,
                'queue_health': self._assess_queue_health(pending_calls)
            }
            
            return statistics
            
        except Exception as e:
            logger.error(f"Error getting queue statistics: {e}")
            return {}
    
    def optimize_queue(self) -> Dict[str, Any]:
        """Optimize the call queue by redistributing and prioritizing"""
        
        try:
            # Get current queue
            pending_calls = get_pending_calls(limit=10000)
            
            if not pending_calls:
                return {'message': 'No calls to optimize'}
            
            optimizations = {
                'redistributed': 0,
                'reprioritized': 0,
                'cleaned_up': 0
            }
            
            now = datetime.utcnow()
            
            for call_entry in pending_calls:
                try:
                    needs_update = False
                    updates = {}
                    
                    # Redistribute overdue calls
                    if call_entry.scheduled_time < now:
                        new_time = self._get_next_available_slot(call_entry.priority)
                        updates['scheduled_time'] = new_time
                        optimizations['redistributed'] += 1
                        needs_update = True
                    
                    # Re-evaluate priority
                    lead = get_lead(call_entry.lead_id)
                    if lead:
                        new_priority = self._calculate_lead_priority(lead)
                        if new_priority != call_entry.priority:
                            updates['priority'] = new_priority
                            optimizations['reprioritized'] += 1
                            needs_update = True
                    
                    # Clean up invalid entries
                    if not lead or call_entry.attempts >= call_entry.max_attempts:
                        update_queue_entry(call_entry.id, status='failed', notes='Cleaned up during optimization')
                        optimizations['cleaned_up'] += 1
                        continue
                    
                    # Apply updates
                    if needs_update:
                        update_queue_entry(call_entry.id, **updates)
                
                except Exception as e:
                    logger.error(f"Error optimizing queue entry {call_entry.id}: {e}")
                    continue
            
            logger.info(f"Queue optimization completed: {optimizations}")
            return optimizations
            
        except Exception as e:
            logger.error(f"Error optimizing queue: {e}")
            return {'error': str(e)}
    
    # Sorting strategies
    def _fifo_sort(self, calls: List[QueuedCall]) -> List[QueuedCall]:
        """First In, First Out sorting"""
        return sorted(calls, key=lambda x: x.scheduled_time)
    
    def _priority_sort(self, calls: List[QueuedCall]) -> List[QueuedCall]:
        """Priority-based sorting"""
        return sorted(calls, key=lambda x: (-x.priority, x.scheduled_time))
    
    def _smart_sort(self, calls: List[QueuedCall]) -> List[QueuedCall]:
        """Smart sorting considering multiple factors"""
        def sort_key(call):
            # Calculate a composite score
            priority_score = call.priority * 1000
            
            # Time urgency (negative because we want earlier times first)
            now = datetime.utcnow()
            time_diff = (call.scheduled_time - now).total_seconds() / 3600  # hours
            urgency_score = -min(time_diff, 24)  # Cap at 24 hours
            
            # Retry penalty (fewer attempts is better)
            retry_penalty = call.attempts * 10
            
            # Combine scores
            total_score = priority_score + urgency_score - retry_penalty
            
            return -total_score  # Negative for descending order
        
        return sorted(calls, key=sort_key)
    
    # Helper methods
    def _apply_business_rules(self, calls: List[QueuedCall]) -> List[QueuedCall]:
        """Apply business rules to filter calls"""
        
        filtered_calls = []
        now = datetime.utcnow()
        
        for call in calls:
            # Skip calls with invalid phone numbers
            if not call.phone or len(call.phone) < 10:
                continue
            
            # Skip calls that are too far in the future (more than 1 hour)
            if call.scheduled_time > now + timedelta(hours=1):
                continue
            
            # Skip calls that have reached max attempts
            if call.attempts >= call.max_attempts:
                continue
            
            filtered_calls.append(call)
        
        return filtered_calls
    
    def _get_filtered_leads(self, filter_criteria: Dict[str, Any]) -> List:
        """Get leads based on filter criteria"""
        
        # Start with all pending leads
        leads = get_all_leads(status=filter_criteria.get('status', 'pending'))
        
        # Apply additional filters
        if 'priority' in filter_criteria:
            leads = [lead for lead in leads if lead.priority >= filter_criteria['priority']]
        
        if 'industry' in filter_criteria:
            leads = [lead for lead in leads if lead.industry == filter_criteria['industry']]
        
        if 'company' in filter_criteria:
            company_filter = filter_criteria['company'].lower()
            leads = [lead for lead in leads if lead.company and company_filter in lead.company.lower()]
        
        return leads
    
    def _calculate_lead_priority(self, lead) -> int:
        """Calculate priority for a lead based on characteristics"""
        
        priority = 1  # Default
        
        # Increase priority for high-value companies
        if lead.company:
            company_lower = lead.company.lower()
            if any(keyword in company_lower for keyword in ['enterprise', 'corporation', 'inc', 'llc']):
                priority += 1
        
        # Increase priority for certain titles
        if lead.title:
            title_lower = lead.title.lower()
            if any(keyword in title_lower for keyword in ['ceo', 'cto', 'director', 'manager', 'vp']):
                priority += 1
        
        # Use existing lead priority
        if hasattr(lead, 'priority') and lead.priority:
            priority = max(priority, lead.priority)
        
        return min(priority, 4)  # Cap at 4
    
    def _get_next_business_time(self) -> datetime:
        """Get the next business hour time"""
        
        now = datetime.utcnow()
        
        # If it's during business hours on a weekday, return current time
        if (9 <= now.hour < 17 and now.weekday() < 5):
            return now
        
        # Otherwise, return next business day at 9 AM
        next_business = now
        
        # Move to next day if after hours
        if now.hour >= 17:
            next_business += timedelta(days=1)
        
        # Skip weekends
        while next_business.weekday() >= 5:
            next_business += timedelta(days=1)
        
        # Set to 9 AM
        next_business = next_business.replace(hour=9, minute=0, second=0, microsecond=0)
        
        return next_business
    
    def _adjust_for_business_hours(self, target_time: datetime) -> datetime:
        """Adjust time to fall within business hours"""
        
        # If weekend, move to Monday
        if target_time.weekday() >= 5:
            days_until_monday = 7 - target_time.weekday()
            target_time += timedelta(days=days_until_monday)
            target_time = target_time.replace(hour=9, minute=0)
        
        # If before 9 AM, move to 9 AM
        elif target_time.hour < 9:
            target_time = target_time.replace(hour=9, minute=0)
        
        # If after 5 PM, move to next business day 9 AM
        elif target_time.hour >= 17:
            target_time += timedelta(days=1)
            if target_time.weekday() >= 5:
                days_until_monday = 7 - target_time.weekday()
                target_time += timedelta(days=days_until_monday)
            target_time = target_time.replace(hour=9, minute=0)
        
        return target_time
    
    def _get_next_available_slot(self, priority: int) -> datetime:
        """Get next available time slot based on priority"""
        
        now = datetime.utcnow()
        
        # High priority gets immediate slot
        if priority >= 3:
            return now
        
        # Medium priority gets slot in next hour
        elif priority == 2:
            return now + timedelta(hours=1)
        
        # Low priority gets slot in next 4 hours
        else:
            return now + timedelta(hours=4)
    
    def _assess_queue_health(self, pending_calls: List) -> str:
        """Assess the health of the call queue"""
        
        if not pending_calls:
            return "empty"
        
        total_calls = len(pending_calls)
        now = datetime.utcnow()
        
        # Count overdue calls
        overdue = len([call for call in pending_calls if call.scheduled_time < now])
        overdue_percentage = (overdue / total_calls) * 100
        
        # Count high-attempt calls
        high_attempts = len([call for call in pending_calls if call.attempts >= 2])
        high_attempts_percentage = (high_attempts / total_calls) * 100
        
        # Assess health
        if overdue_percentage > 50:
            return "critical"
        elif overdue_percentage > 25 or high_attempts_percentage > 40:
            return "warning"
        elif total_calls > 1000:
            return "congested"
        else:
            return "healthy"

# Global queue manager instance
queue_manager = CallQueueManager()

# Export
__all__ = ['QueuePriority', 'QueuedCall', 'CallQueueManager', 'queue_manager']