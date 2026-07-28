"""
Backup verifier for share_backups.
Verifies copied files match expected state.
"""

import os
from typing import List, Dict, Any, Tuple
from datetime import datetime


class BackupVerifier:
    """Verifies backup integrity by comparing source and destination."""
    
    # Allowed time delta for modified_time comparison (1 minute)
    TIME_DELTA_SECONDS = 60
    
    def __init__(self):
        self.mismatches: List[Dict[str, Any]] = []
    
    def verify_copied_files(self, temp_files: List[Dict[str, Any]], 
                           backup_dest_path: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Verify locally copied files match temp_file_list entries.
        Only verifies files with status='copied'.
        
        Args:
            temp_files: List from temp_file_list with file info
            backup_dest_path: Base path of backup destination
            
        Returns:
            Tuple of (success, list of mismatches)
        """
        self.mismatches = []
        
        for file_info in temp_files:
            if file_info.get('status') != 'copied':
                continue
            
            share_nic = file_info['share_nic']
            file_path = file_info['file_path']
            expected_size = file_info['file_size']
            expected_mtime = file_info.get('modified_time')
            
            # Build local file path
            # Structure: <backup_id>_<date>_main/<share_nic>/<file_path>
            local_path = os.path.join(backup_dest_path, share_nic, file_path)
            
            if not os.path.exists(local_path):
                self.mismatches.append({
                    'file_path': file_path,
                    'share_nic': share_nic,
                    'error_type': 'missing',
                    'expected_size': expected_size,
                    'actual_size': None,
                    'message': f'File not found at {local_path}'
                })
                continue
            
            # Check file size
            actual_size = os.path.getsize(local_path)
            if actual_size != expected_size:
                self.mismatches.append({
                    'file_path': file_path,
                    'share_nic': share_nic,
                    'error_type': 'size_mismatch',
                    'expected_size': expected_size,
                    'actual_size': actual_size,
                    'message': f'Size mismatch: expected {expected_size}, got {actual_size}'
                })
                continue
            
            # Check modified time (with tolerance)
            if expected_mtime:
                try:
                    actual_mtime = os.path.getmtime(local_path)
                    actual_mtime_str = datetime.fromtimestamp(actual_mtime).strftime('%Y/%m/%d %H:%M:%S')
                    
                    # Parse expected time
                    expected_dt = datetime.strptime(expected_mtime, '%Y/%m/%d %H:%M:%S')
                    actual_dt = datetime.fromtimestamp(actual_mtime)
                    
                    time_diff = abs((actual_dt - expected_dt).total_seconds())
                    if time_diff > self.TIME_DELTA_SECONDS:
                        self.mismatches.append({
                            'file_path': file_path,
                            'share_nic': share_nic,
                            'error_type': 'time_mismatch',
                            'expected_mtime': expected_mtime,
                            'actual_mtime': actual_mtime_str,
                            'message': f'Time difference {time_diff}s exceeds tolerance'
                        })
                        continue
                        
                except Exception as e:
                    self.mismatches.append({
                        'file_path': file_path,
                        'share_nic': share_nic,
                        'error_type': 'time_check_error',
                        'message': f'Error checking time: {e}'
                    })
                    continue
        
        return len(self.mismatches) == 0, self.mismatches
    
    def get_mismatch_report(self) -> str:
        """Generate human-readable mismatch report."""
        if not self.mismatches:
            return "All files verified successfully."
        
        lines = [f"Verification failed: {len(self.mismatches)} mismatch(es)\n"]
        
        for m in self.mismatches:
            lines.append(f"  File: {m['share_nic']}/{m['file_path']}")
            lines.append(f"    Error: {m['error_type']}")
            lines.append(f"    Message: {m['message']}")
            if 'expected_size' in m and m['expected_size']:
                lines.append(f"    Expected size: {m['expected_size']}")
            if 'actual_size' in m and m['actual_size']:
                lines.append(f"    Actual size: {m['actual_size']}")
            lines.append("")
        
        return "\n".join(lines)
