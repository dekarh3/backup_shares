"""
Scheduler for share_backups.
Handles cron-based backup scheduling with catch-up mode and error cooldown.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import threading
import time

try:
    from share_backups.config.cron_parser import CronParser
except ImportError:
    from config.cron_parser import CronParser


class BackupScheduler:
    """Manages backup scheduling based on cron expressions."""
    
    DEFAULT_COOLDOWN_MINUTES = 60
    
    def __init__(self, db_manager, config_handler, run_backup_callback):
        self.db = db_manager
        self.config = config_handler
        self.run_backup_callback = run_backup_callback
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._catch_up_enabled = False
        self._cooldown_minutes = self.DEFAULT_COOLDOWN_MINUTES
    
    def start(self):
        """Start the scheduler background thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the scheduler background thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def set_catch_up_mode(self, enabled: bool):
        """Enable/disable catch-up mode for missed backups."""
        self._catch_up_enabled = enabled
    
    def set_cooldown_minutes(self, minutes: int):
        """Set cooldown period between failed backup attempts."""
        self._cooldown_minutes = max(1, minutes)
    
    def _run_loop(self):
        """Main scheduler loop - checks every minute."""
        while self._running:
            try:
                self._check_and_run_backups()
            except Exception as e:
                print(f"Scheduler error: {e}")
            
            # Sleep until next minute
            now = datetime.now()
            sleep_seconds = 60 - now.second - (now.microsecond / 1000000)
            time.sleep(min(sleep_seconds, 61))
    
    def _check_and_run_backups(self):
        """Check all cron profiles and run due backups."""
        state = self.db.get_current_state()
        if not state:
            return
        
        # Can only run if idle or in error state
        if state['status'] not in ('idle', 'error'):
            return
        
        now = datetime.now()
        cron_profiles = self.config.get_cron_profiles()
        
        # Sort by priority: full backups first
        full_profiles = [p for p in cron_profiles if p['backup_type'] == 'full']
        incremental_profiles = [p for p in cron_profiles if p['backup_type'] == 'incremental']
        
        # Check for any due backup
        due_full = self._find_due_backup(full_profiles, now, state)
        due_incremental = self._find_due_backup(incremental_profiles, now, state)
        
        # Priority: full backup takes precedence
        if due_full:
            self._try_run_backup(due_full)
        elif due_incremental:
            # Skip if a full backup is also due at this time
            if not due_full:
                self._try_run_backup(due_incremental)
    
    def _find_due_backup(self, profiles: List[Dict], now: datetime, 
                         state: Dict) -> Optional[Dict]:
        """Find first due backup from list of profiles."""
        for profile in profiles:
            if self._is_profile_due(profile, now, state):
                return profile
        return None
    
    def _is_profile_due(self, profile: Dict, now: datetime, 
                        state: Dict) -> bool:
        """
        Check if a cron profile is due to run.
        
        Conditions:
        1. Not in cooldown period after error
        2. Current time matches cron schedule (or past due in catch-up mode)
        3. last_processed_cron_time < scheduled time for this run
        """
        cron_id = profile['cron_id']
        cron_expr = profile['cron_request']
        
        try:
            parser = CronParser(cron_expr)
        except ValueError:
            return False
        
        # Check cooldown
        cooldown_info = self.db.get_error_cooldown(cron_id)
        if cooldown_info and cooldown_info.get('last_error_time'):
            last_error = datetime.fromisoformat(cooldown_info['last_error_time'])
            if now < last_error + timedelta(minutes=self._cooldown_minutes):
                return False  # Still in cooldown
        
        # Get the scheduled time for this moment
        scheduled_time = parser.get_scheduled_time_for(now)
        
        # Check if already processed this scheduled time
        last_processed_str = state.get('last_processed_cron_time')
        if last_processed_str:
            try:
                last_processed = datetime.fromisoformat(last_processed_str)
                if last_processed >= scheduled_time:
                    return False  # Already processed this run
            except Exception:
                pass
        
        # Check if time matches
        if self._catch_up_enabled:
            # Catch-up mode: run if past due
            if not parser.is_past_due(now):
                return False
        else:
            # Normal mode: must match current minute exactly
            if not parser.matches(now):
                return False
        
        return True
    
    def _try_run_backup(self, profile: Dict):
        """Attempt to run backup for given profile."""
        cron_id = profile['cron_id']
        backup_type = profile['backup_type']
        
        try:
            success = self.run_backup_callback(cron_id, backup_type)
            
            if success:
                self.db.reset_error_cooldown(cron_id)
            else:
                self.db.record_error(cron_id)
                
        except Exception as e:
            print(f"Backup execution error for cron {cron_id}: {e}")
            self.db.record_error(cron_id)
    
    def check_next_run_times(self) -> List[Dict[str, Any]]:
        """Get next scheduled run times for all cron profiles."""
        result = []
        now = datetime.now()
        
        for profile in self.config.get_cron_profiles():
            try:
                parser = CronParser(profile['cron_request'])
                next_run = parser.get_next_run(now)
                
                result.append({
                    'cron_id': profile['cron_id'],
                    'backup_type': profile['backup_type'],
                    'cron_expression': profile['cron_request'],
                    'next_run': next_run.isoformat(),
                    'is_past_due': parser.is_past_due(now)
                })
            except Exception as e:
                result.append({
                    'cron_id': profile['cron_id'],
                    'backup_type': profile['backup_type'],
                    'cron_expression': profile['cron_request'],
                    'error': str(e)
                })
        
        return result
