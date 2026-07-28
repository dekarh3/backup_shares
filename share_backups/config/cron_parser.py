"""
Cron parser wrapper for share_backups.
Uses croniter to parse and evaluate cron expressions.
"""

from datetime import datetime
from typing import Optional, List
try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False


class CronParser:
    """Wrapper around croniter for cron expression parsing."""
    
    def __init__(self, cron_expression: str):
        """
        Initialize with cron expression.
        
        Args:
            cron_expression: Standard cron format (5 fields: minute hour day month weekday)
        """
        self.expression = cron_expression
        self._cron = None
        if CRONITER_AVAILABLE:
            try:
                self._cron = croniter(cron_expression)
            except Exception as e:
                raise ValueError(f"Invalid cron expression: {e}")
    
    def get_next_run(self, start_time: datetime = None) -> datetime:
        """
        Get next scheduled run time after start_time.
        
        Args:
            start_time: Starting point for calculation (default: now)
            
        Returns:
            Next scheduled datetime
        """
        if not CRONITER_AVAILABLE or not self._cron:
            raise RuntimeError("croniter not available")
        
        if start_time is None:
            start_time = datetime.now()
        
        return self._cron.get_next(datetime, start_time)
    
    def get_prev_run(self, end_time: datetime = None) -> datetime:
        """
        Get previous scheduled run time before end_time.
        
        Args:
            end_time: End point for calculation (default: now)
            
        Returns:
            Previous scheduled datetime
        """
        if not CRONITER_AVAILABLE or not self._cron:
            raise RuntimeError("croniter not available")
        
        if end_time is None:
            end_time = datetime.now()
        
        return self._cron.get_prev(datetime, end_time)
    
    def matches(self, check_time: datetime = None) -> bool:
        """
        Check if current time matches cron schedule (within 1 minute window).
        
        Args:
            check_time: Time to check (default: now)
            
        Returns:
            True if time matches cron schedule
        """
        if check_time is None:
            check_time = datetime.now()
        
        if not CRONITER_AVAILABLE or not self._cron:
            return False
        
        # Get the previous scheduled time
        prev_time = self.get_prev_run(check_time)
        
        # Check if we're within 1 minute of the scheduled time
        diff = (check_time - prev_time).total_seconds()
        return 0 <= diff < 60
    
    def is_past_due(self, check_time: datetime = None) -> bool:
        """
        Check if a scheduled run was missed (for "catch up" mode).
        
        Args:
            check_time: Current time to check against
            
        Returns:
            True if there's a missed scheduled run
        """
        if check_time is None:
            check_time = datetime.now()
        
        if not CRONITER_AVAILABLE or not self._cron:
            return False
        
        # Get next scheduled time from a point in the past
        past_time = check_time.replace(second=0, microsecond=0)
        prev_time = self.get_prev_run(past_time)
        
        # If prev_time + 1 minute < now, then we're past due
        due_time = prev_time.replace(second=0, microsecond=0)
        return check_time > due_time
    
    def get_scheduled_time_for(self, check_time: datetime = None) -> datetime:
        """
        Get the exact scheduled time that should have run at/before check_time.
        
        Args:
            check_time: Reference time
            
        Returns:
            The scheduled datetime that applies to check_time
        """
        if check_time is None:
            check_time = datetime.now()
        
        if not CRONITER_AVAILABLE or not self._cron:
            return check_time
        
        prev_time = self.get_prev_run(check_time)
        return prev_time.replace(second=0, microsecond=0)
    
    @staticmethod
    def validate_expression(cron_expression: str) -> bool:
        """
        Validate a cron expression without creating an instance.
        
        Args:
            cron_expression: Cron expression to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not CRONITER_AVAILABLE:
            return False
        
        try:
            croniter(cron_expression)
            return True
        except Exception:
            return False
