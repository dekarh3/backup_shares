"""
Incremental backup implementation for share_backups.
Implements the incremental backup process as specified in section 9 of the requirements.
"""

import os
import shutil
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple

from .robocopy_runner import RobocopyRunner
from .vss_manager import VSSManager
from .verifier import BackupVerifier


class IncrementalBackup:
    """Handles incremental backup operations."""
    
    def __init__(self, db_manager, config_handler, target_path: str):
        self.db = db_manager
        self.config = config_handler
        self.target_path = target_path
        self.runner = RobocopyRunner()
        self.vss = VSSManager()
        self.verifier = BackupVerifier()
        
        self.backup_id: Optional[int] = None
        self.full_backup_id: Optional[int] = None
        self.cron_id: Optional[int] = None
        self.backup_timestamp: Optional[str] = None
        self.temp_dir: Optional[str] = None
        self.main_dir: Optional[str] = None
        self.trash_dir: Optional[str] = None
    
    def execute(self, cron_id: int) -> bool:
        """
        Execute incremental backup process.
        
        Args:
            cron_id: ID of the cron profile triggering this backup
            
        Returns:
            True if backup completed successfully
        """
        shares = self.config.get_shares()
        if not shares:
            print("No shares configured for backup")
            return False
        
        # Step 9.2: Get last successful full backup
        self.full_backup_id = self.db.get_last_full_backup_id()
        if not self.full_backup_id:
            print("No previous full backup found, must run full backup first")
            return False
        
        self.cron_id = cron_id
        self.backup_timestamp = datetime.now().isoformat()
        date_str = datetime.now().strftime('%d%m%y%H')
        
        try:
            # Step 9.1: Cleanup from previous interrupted backups
            self._cleanup_interrupted()
            
            # Step 9.2: Create backup log entry
            self.backup_id = self.db.create_backup_log('incremental', cron_id, self.backup_timestamp)
            print(f"Started incremental backup #{self.backup_id} (based on full #{self.full_backup_id})")
            
            # Step 9.3: Scan shares and compare with current_file_state
            changed_files = []
            deleted_files_paths = []
            
            for share in shares:
                share_nic = share['share_nic']
                share_name = share['share_name']
                
                # Scan current state of share
                current_files = self.runner.scan_share(share_name, share_nic)
                for f in current_files:
                    f['share_name'] = share_name
                
                # Get previous state from database
                prev_state = self.db.get_current_file_state(share_nic)
                
                # Build set of current file paths
                current_paths: Set[Tuple[str, str]] = set()
                
                # Find changed files
                for file_info in current_files:
                    key = (share_nic, file_info['file_path'])
                    current_paths.add(key)
                    
                    # Compute attributes hash
                    attr_hash = f"{file_info['file_size']}_{file_info.get('modified_time', '')}"
                    
                    if key not in prev_state:
                        # New file
                        file_info['attributes_hash'] = attr_hash
                        changed_files.append(file_info)
                    else:
                        # Check if changed
                        prev = prev_state[key]
                        if (prev['file_size'] != file_info['file_size'] or
                            prev.get('modified_time') != file_info.get('modified_time') or
                            prev.get('attributes_hash') != attr_hash):
                            file_info['attributes_hash'] = attr_hash
                            changed_files.append(file_info)
                
                # Find deleted files
                for key in prev_state.keys():
                    if key[0] == share_nic and key not in current_paths:
                        deleted_files_paths.append((key[0], share_name, key[1]))
            
            # Save changed files to temp_file_list
            batch_data = [
                (f['share_nic'], f['share_name'], f['file_path'], f['file_size'],
                 f.get('file_attributes'), f.get('file_permissions'),
                 f.get('created_time'), f.get('modified_time'), 'pending')
                for f in changed_files
            ]
            if batch_data:
                self.db.insert_temp_files_batch(batch_data)
            
            # Save deleted files to temp_deleted_list
            if deleted_files_paths:
                self.db.insert_temp_deleted_files(deleted_files_paths)
            
            # Step 9.4: Check disk space
            total_size = sum(f['file_size'] for f in changed_files)
            required_space = int(total_size * 1.10)  # 10% buffer
            
            if not self._check_disk_space(required_space):
                self.db.update_backup_log(self.backup_id, 'no_space')
                self.db.set_state_error('no_space')
                print(f"Insufficient disk space. Need {required_space} bytes")
                return False
            
            # Step 9.5: Set state to running
            self.db.set_state_running(self.backup_id, self.cron_id, 'incremental', self.backup_timestamp)
            
            # Step 9.6: Create temp directory
            self.temp_dir = os.path.join(self.target_path, f'{self.backup_id}_{date_str}_temp')
            self.main_dir = os.path.join(self.target_path, f'{self.backup_id}_{date_str}_main')
            self.trash_dir = os.path.join(self.target_path, f'{self.backup_id}_{date_str}_trash')
            
            os.makedirs(self.temp_dir, exist_ok=True)
            
            # Create subdirectories for each share
            for share in shares:
                share_dir = os.path.join(self.temp_dir, share['share_nic'])
                os.makedirs(share_dir, exist_ok=True)
            
            # Step 9.7: Create VSS shadow copies
            for share in shares:
                shadow_path = self.vss.create_shadow_copy(share['share_name'])
                if shadow_path:
                    share['shadow_path'] = shadow_path
            
            # Step 9.8: Copy only changed files using robocopy
            for share in shares:
                source = share.get('shadow_path', share['share_name'])
                dest = os.path.join(self.temp_dir, share['share_nic'])
                mt_threads = share.get('mt_threads', 8)
                
                # Get list of changed files for this share
                share_changed = [f['file_path'] for f in changed_files if f['share_nic'] == share_nic]
                
                if share_changed:
                    print(f"Copying {len(share_changed)} changed files for {share['share_nic']}...")
                    exit_code, copied = self.runner.copy_files(
                        source, dest, share['share_nic'], mt_threads, share_changed)
                    
                    result = self.runner.check_exit_code(exit_code)
                    if not result['success']:
                        if result['error_type'] == 'no_space':
                            self.db.update_backup_log(self.backup_id, 'no_space')
                            self.db.set_state_error('no_space')
                            return False
            
            # Step 9.9: Update file statuses
            self._update_copied_statuses()
            
            # Step 9.11: Verify copied files
            success, mismatches = self.verifier.verify_copied_files(
                self.db.get_temp_files('copied'),
                self.temp_dir
            )
            
            if not success:
                # Step 9.12: Verification failed
                self.db.update_backup_log(self.backup_id, 'error')
                self.db.set_state_error('error')
                print(self.verifier.get_mismatch_report())
                return False
            
            # Step 9.13: Verification successful - finalize backup
            if not self._finalize_backup(date_str, shares, deleted_files_paths):
                return False
            
            # Step 9.14: Delete VSS shadow copies
            self.vss.delete_all_shadow_copies()
            
            print(f"Incremental backup #{self.backup_id} completed successfully")
            return True
            
        except Exception as e:
            print(f"Incremental backup error: {e}")
            self.db.update_backup_log(self.backup_id, 'error')
            self.db.set_state_error('error')
            self.vss.delete_all_shadow_copies()
            return False
    
    def _cleanup_interrupted(self):
        """Clean up temp directories and tables from interrupted backups."""
        self.db.drop_temp_tables()
    
    def _check_disk_space(self, required_bytes: int) -> bool:
        """Check if target drive has sufficient free space."""
        try:
            free_space = shutil.disk_usage(self.target_path).free
            return free_space >= required_bytes
        except Exception:
            return False
    
    def _update_copied_statuses(self):
        """Update temp_file_list with copied status based on actual files."""
        with self.db.get_connection() as conn:
            conn.execute("""
                UPDATE temp_file_list SET status = 'copied' WHERE status = 'pending'
            """)
            conn.commit()
    
    def _finalize_backup(self, date_str: str, shares: List[Dict], 
                         deleted_files_paths: List[Tuple]) -> bool:
        """
        Finalize successful backup: rename directories, update database.
        """
        try:
            # Rename main to trash if exists
            for item in os.listdir(self.target_path):
                if item.endswith('_main'):
                    trash_path = item.replace('_main', '_trash')
                    old_path = os.path.join(self.target_path, item)
                    new_trash = os.path.join(self.target_path, trash_path)
                    
                    if os.path.exists(new_trash):
                        shutil.rmtree(new_trash)
                    shutil.move(old_path, new_trash)
            
            # Rename temp to main
            shutil.move(self.temp_dir, self.main_dir)
            
            # Remove trash
            for item in os.listdir(self.target_path):
                if item.endswith('_trash'):
                    trash_path = os.path.join(self.target_path, item)
                    shutil.rmtree(trash_path)
            
            # Copy temp to backuped_files
            self.db.copy_temp_to_backuped_files(
                self.backup_id, self.cron_id, 'incremental', self.backup_timestamp)
            
            # Insert deleted files
            deleted_in_temp = self.db.get_temp_deleted_files()
            if deleted_in_temp:
                del_tuples = [(d['share_nic'], d['share_name'], d['file_path']) 
                              for d in deleted_in_temp]
                self.db.insert_deleted_files(
                    self.backup_id, self.full_backup_id, self.cron_id,
                    del_tuples, self.backup_timestamp)
            
            # Update current_file_state
            files = self.db.get_temp_files('copied')
            state_updates = []
            for f in files:
                attr_hash = f"{f['file_size']}_{f.get('modified_time', '')}"
                state_updates.append((
                    f['share_nic'], f['file_path'], self.backup_id,
                    f['file_size'], f.get('modified_time'), attr_hash
                ))
            
            # Prepare deleted paths for removal from current_file_state
            del_paths = [(d['share_nic'], d['file_path']) for d in deleted_in_temp] if deleted_in_temp else None
            
            self.db.update_current_file_state(state_updates, del_paths)
            
            # Clear temp tables
            self.db.clear_temp_tables()
            
            # Update state to idle
            self.db.set_state_idle(
                self.backup_id, self.cron_id, 'incremental', self.backup_timestamp)
            
            # Update backup log
            self.db.update_backup_log(self.backup_id, 'success')
            
            return True
            
        except Exception as e:
            print(f"Error finalizing backup: {e}")
            self.db.update_backup_log(self.backup_id, 'error')
            self.db.set_state_error('error')
            return False
    
    def cancel(self):
        """Cancel current backup operation."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            cancelled_dir = self.temp_dir.replace('_temp', '_cancelled')
            shutil.move(self.temp_dir, cancelled_dir)
        
        if self.backup_id:
            self.db.update_backup_log(self.backup_id, 'cancelled')
        
        self.db.set_state_idle()
        self.vss.delete_all_shadow_copies()
