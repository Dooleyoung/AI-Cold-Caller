"""
Call scheduling system for managing when calls should be made
"""
import time
import threading
from datetime import datetime, timedelta
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

from database.crud import get_pending_calls, update_queue_entry, get_lead, update_lead
from core.call_manager import call_orchestrator
from utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

class CallScheduler:
    """Manages scheduled calls and timing"""
    
    def __init__(self, max_concurrent_calls: int = 5, check_interval: int = 30):
        """Initialize call scheduler"""
        self.max_concurrent_calls = max_concurrent_calls
        self.check_interval = check_interval  # seconds
        self.is_running = False
        self.scheduler_thread = None
        self.call_executor = ThreadPoolExecutor(max_workers=max_concurrent_calls)
        self.active_calls = {}  # call_sid -> thread_info
        
        logger.info(f"CallScheduler initialized: {max_concurrent_calls} max concurrent calls")
    
    def start(self):
        """Start the call scheduler"""
        if self.is_running:
            logger.warning("Call scheduler already running")
            return
        
        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Call scheduler started")
    
    def stop(self):
        """Stop the call scheduler"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=10)
        
        # Shutdown executor
        self.call_executor.shutdown(wait=True)
        
        logger.info("Call scheduler stopped")
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        logger.info("Scheduler loop started")
        
        while self.is_running:
            try:
                self._process_pending_calls()
                self._cleanup_completed_calls()
                
                # Sleep for check interval
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(self.check_interval)
        
        logger.info("Scheduler loop ended")
    
    def _process_pending_calls(self):
        """Process pending calls from the queue"""
        try:
            # Check if we can make more calls
            available_slots = self.max_concurrent_calls - len(self.active_calls)
            if available_slots <= 0:
                return
            
            # Get pending calls
            pending_calls = get_pending_calls(limit=available_slots)
            
            if not pending_calls:
                return
            
            logger.info(f"Processing {len(pending_calls)} pending calls")
            
            for queue_entry in pending_calls:
                try:
                    # Check if we still have available slots
                    if len(self.active_calls) >= self.max_concurrent_calls:
                        break
                    
                    # Validate lead
                    lead = get_lead(queue_entry.lead_id)
                    if not lead:
                        logger.warning(f"Lead {queue_entry.lead_id} not found, skipping")
                        update_queue_entry(queue_entry.id, status='failed', notes='Lead not found')
                        continue
                    
                    # Check if lead is in a callable state
                    if lead.status in ['calling', 'scheduled']:
                        logger.info(f"Lead {lead.id} status is {lead.status}, skipping")
                        continue
                    
                    # Mark queue entry as processing
                    update_queue_entry(
                        queue_entry.id, 
                        status='processing',
                        attempts=queue_entry.attempts + 1,
                        last_attempt=datetime.utcnow()
                    )
                    
                    # Submit call to thread pool
                    future = self.call_executor.submit(self._make_call, queue_entry, lead)
                    
                    # Track active call
                    self.active_calls[f"queue_{queue_entry.id}"] = {
                        'queue_entry': queue_entry,
                        'lead': lead,
                        'future': future,
                        'started_at': datetime.utcnow()
                    }
                    
                    logger.info(f"Submitted call for lead {lead.id} ({lead.name})")
                    
                except Exception as e:
                    logger.error(f"Error processing queue entry {queue_entry.id}: {e}")
                    update_queue_entry(queue_entry.id, status='failed', notes=f'Processing error: {str(e)}')
                    
        except Exception as e:
            logger.error(f"Error processing pending calls: {e}")
    
    def _make_call(self, queue_entry, lead):
        """Make a call to a lead"""
        try:
            logger.info(f"Making call to {lead.name} ({lead.phone})")
            
            # Attempt to start call
            success, result = call_orchestrator.start_call(lead.id)
            
            if success:
                call_sid = result
                logger.info(f"Call started successfully: {call_sid}")
                
                # Update queue entry
                update_queue_entry(
                    queue_entry.id,
                    status='completed',
                    notes=f'Call initiated: {call_sid}'
                )
                
                return {'success': True, 'call_sid': call_sid}
                
            else:
                error_msg = result
                logger.error(f"Call failed for lead {lead.id}: {error_msg}")
                
                # Determine if we should retry
                should_retry = (
                    queue_entry.attempts < queue_entry.max_attempts and
                    'invalid phone' not in error_msg.lower() and
                    'blocked' not in error_msg.lower()
                )
                
                if should_retry:
                    # Schedule retry
                    retry_time = datetime.utcnow() + timedelta(hours=1)
                    update_queue_entry(
                        queue_entry.id,
                        status='pending',
                        scheduled_time=retry_time,
                        notes=f'Retry scheduled due to: {error_msg}'
                    )
                    logger.info(f"Scheduled retry for lead {lead.id} at {retry_time}")
                else:
                    # Mark as failed
                    update_queue_entry(
                        queue_entry.id,
                        status='failed',
                        notes=f'Max attempts reached: {error_msg}'
                    )
                    update_lead(lead.id, status='failed')
                    logger.info(f"Max attempts reached for lead {lead.id}")
                
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logger.error(f"Unexpected error making call to lead {lead.id}: {e}")
            
            # Mark as failed
            update_queue_entry(
                queue_entry.id,
                status='failed',
                notes=f'Unexpected error: {str(e)}'
            )
            
            return {'success': False, 'error': str(e)}
    
    def _cleanup_completed_calls(self):
        """Clean up completed calls from active tracking"""
        completed_keys = []
        
        for key, call_info in self.active_calls.items():
            future = call_info['future']
            
            if future.done():
                try:
                    result = future.result(timeout=1)
                    logger.debug(f"Call {key} completed: {result}")
                except Exception as e:
                    logger.error(f"Call {key} failed: {e}")
                
                completed_keys.append(key)
        
        # Remove completed calls
        for key in completed_keys:
            del self.active_calls[key]
        
        if completed_keys:
            logger.debug(f"Cleaned up {len(completed_keys)} completed calls")
    
    def schedule_immediate_call(self, lead_id: int, priority: int = 2) -> bool:
        """Schedule an immediate call for a lead"""
        try:
            from database.crud import add_to_call_queue
            
            # Schedule for immediate execution
            scheduled_time = datetime.utcnow()
            
            queue_id = add_to_call_queue(
                lead_id=lead_id,
                scheduled_time=scheduled_time,
                priority=priority,
                notes="Immediate call requested"
            )
            
            if queue_id:
                logger.info(f"Scheduled immediate call for lead {lead_id}")
                return True
            else:
                logger.error(f"Failed to schedule immediate call for lead {lead_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error scheduling immediate call for lead {lead_id}: {e}")
            return False
    
    def schedule_call(self, lead_id: int, scheduled_time: datetime, priority: int = 1) -> bool:
        """Schedule a call for a specific time"""
        try:
            from database.crud import add_to_call_queue
            
            queue_id = add_to_call_queue(
                lead_id=lead_id,
                scheduled_time=scheduled_time,
                priority=priority,
                notes=f"Scheduled call for {scheduled_time}"
            )
            
            if queue_id:
                logger.info(f"Scheduled call for lead {lead_id} at {scheduled_time}")
                return True
            else:
                logger.error(f"Failed to schedule call for lead {lead_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error scheduling call for lead {lead_id}: {e}")
            return False
    
    def get_status(self) -> dict:
        """Get scheduler status"""
        return {
            'running': self.is_running,
            'active_calls': len(self.active_calls),
            'max_concurrent_calls': self.max_concurrent_calls,
            'check_interval': self.check_interval,
            'scheduler_thread_alive': self.scheduler_thread.is_alive() if self.scheduler_thread else False
        }

# Global scheduler instance
call_scheduler = CallScheduler(
    max_concurrent_calls=getattr(settings, 'MAX_CONCURRENT_CALLS', 5),
    check_interval=getattr(settings, 'SCHEDULER_CHECK_INTERVAL', 30)
)

# Export
__all__ = ['CallScheduler', 'call_scheduler']