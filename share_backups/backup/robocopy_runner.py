"""
Robocopy runner for share_backups.
Handles executing robocopy commands, parsing logs, and scanning files.
"""

import subprocess
import re
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class RobocopyFileInfo:
    """Parsed file info from robocopy output."""
    file_path: str
    file_size: int
    modified_time: str
    attributes: str


class RobocopyRunner:
    """Executes robocopy commands and parses output."""
    
    # Robocopy exit codes
    EXIT_OK = 0
    EXIT_ALL_COPIED = 1
    EXIT_EXTRA_FILES = 2
    EXIT_MISMATCH = 3
    EXIT_SOME_FAILED = 4
    EXIT_SERIOUS_ERROR = 8
    EXIT_DISK_FULL = 16
    
    def __init__(self, log_dir: str = None):
        self.log_dir = log_dir or os.path.join(os.getcwd(), 'robocopy_logs')
        os.makedirs(self.log_dir, exist_ok=True)
    
    def scan_share(self, source: str, share_nic: str, 
                   log_file: str = None) -> List[Dict[str, Any]]:
        """
        Scan share using robocopy /L (list only) mode.
        
        Args:
            source: Source path (UNC or VSS path)
            share_nic: Share identifier for logging
            log_file: Optional custom log file path
            
        Returns:
            List of file info dictionaries
        """
        if log_file is None:
            log_file = os.path.join(self.log_dir, f'scan_{share_nic}.log')
        
        # Build robocopy command for listing
        cmd = [
            'robocopy',
            source,
            'NUL',  # Null destination for list-only
            '/L',   # List only
            '/E',   # Include subdirectories
            '/BYTES',  # File sizes in bytes
            '/NFL',  # No file list in output (we parse differently)
            '/NDL',  # No directory list
            '/NJH',  # No job header
            '/NJS',  # No job summary
            '/nc',   # No class (file type)
            '/ns',   # No size (in standard output)
            '/np',   # No progress
            '/XJ',   # Exclude junction points
            '/LOG', log_file
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            return self._parse_scan_log(log_file, share_nic)
        except subprocess.TimeoutExpired:
            print(f"Robocopy scan timed out for {share_nic}")
            return []
        except Exception as e:
            print(f"Robocopy scan error for {share_nic}: {e}")
            return []
    
    def _parse_scan_log(self, log_file: str, share_nic: str) -> List[Dict[str, Any]]:
        """Parse robocopy scan log into file list."""
        files = []
        
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Robocopy list format: <date> <time> <size> <path>
                    # Example: 2024/01/15 10:30:45    1234567  \folder\file.txt
                    match = re.match(
                        r'^(\d{4}/\d{2}/\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(\d+)\s+(.+)$',
                        line.strip()
                    )
                    if match:
                        date_str, time_str, size_str, path = match.groups()
                        files.append({
                            'share_nic': share_nic,
                            'file_path': path.lstrip('\\'),
                            'file_size': int(size_str),
                            'modified_time': f"{date_str} {time_str}",
                            'created_time': None,  # Not available in scan
                            'file_attributes': None,
                            'file_permissions': None
                        })
        except Exception as e:
            print(f"Error parsing scan log {log_file}: {e}")
        
        return files
    
    def copy_files(self, source: str, dest: str, share_nic: str,
                   mt_threads: int = 8, file_list: List[str] = None,
                   log_file: str = None) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Copy files using robocopy with multi-threading.
        
        Args:
            source: Source path
            dest: Destination path
            share_nic: Share identifier
            mt_threads: Number of threads for /MT option
            file_list: Optional list of specific files to copy
            log_file: Optional custom log file path
            
        Returns:
            Tuple of (exit_code, list of copied files)
        """
        if log_file is None:
            timestamp = re.sub(r'[^0-9]', '', str(__import__('datetime').datetime.now()))
            log_file = os.path.join(self.log_dir, f'copy_{share_nic}_{timestamp}.log')
        
        # Build robocopy command
        cmd = [
            'robocopy',
            source,
            dest,
            '/E',           # Include subdirectories
            '/XJ',          # Exclude junction points
            '/COPY:DATSO',  # Copy Data, Attributes, Timestamps, Security, Owner
            '/DCOPY:DAT',   # Copy directory timestamps
            '/DCOPY:T',     # Copy directory security
            '/R:1',         # Retry count
            '/W:1',         # Wait time between retries
            f'/MT:{mt_threads}',  # Multi-threaded
            '/NP',          # No progress
            '/LOG', log_file
        ]
        
        # Add file list if specified
        temp_filelist = None
        if file_list:
            temp_filelist = os.path.join(self.log_dir, f'filelist_{share_nic}.txt')
            with open(temp_filelist, 'w', encoding='utf-8') as f:
                for path in file_list:
                    f.write(path + '\n')
            cmd.append(f'@{temp_filelist}')
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=7200  # 2 hour timeout
            )
            
            exit_code = result.returncode
            copied_files = self._parse_copy_log(log_file, share_nic, dest)
            
            # Clean up temp filelist
            if temp_filelist and os.path.exists(temp_filelist):
                os.unlink(temp_filelist)
            
            return exit_code, copied_files
        except subprocess.TimeoutExpired:
            print(f"Robocopy copy timed out for {share_nic}")
            if temp_filelist and os.path.exists(temp_filelist):
                os.unlink(temp_filelist)
            return -1, []
        except Exception as e:
            print(f"Robocopy copy error for {share_nic}: {e}")
            if temp_filelist and os.path.exists(temp_filelist):
                os.unlink(temp_filelist)
            return -1, []
    
    def _parse_copy_log(self, log_file: str, share_nic: str, 
                        dest_base: str) -> List[Dict[str, Any]]:
        """Parse robocopy copy log into copied files list."""
        files = []
        
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Copied file format: <date> <time> <size> <path>
                    # Newer files have extra info
                    match = re.match(
                        r'^(\d{4}/\d{2}/\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(\d+)\s+(.+)$',
                        line.strip()
                    )
                    if match:
                        date_str, time_str, size_str, path = match.groups()
                        
                        # Skip special entries
                        if path.startswith('Newer') or path.startswith('Same'):
                            continue
                        
                        files.append({
                            'share_nic': share_nic,
                            'source_path': path.lstrip('\\'),
                            'dest_path': os.path.join(dest_base, path.lstrip('\\')),
                            'file_size': int(size_str),
                            'modified_time': f"{date_str} {time_str}"
                        })
        except Exception as e:
            print(f"Error parsing copy log {log_file}: {e}")
        
        return files
    
    def check_exit_code(self, exit_code: int) -> Dict[str, Any]:
        """
        Interpret robocopy exit code.
        
        Returns dict with 'success', 'error_type', 'message' keys.
        """
        if exit_code < 0:
            return {
                'success': False,
                'error_type': 'timeout_or_exception',
                'message': 'Robocopy timed out or encountered exception'
            }
        
        if exit_code <= 7:
            # Normal completion codes (0-7 are OK with various conditions)
            return {
                'success': True,
                'error_type': None,
                'message': f'Robocopy completed with code {exit_code}'
            }
        
        if exit_code == 8 or exit_code == 16:
            return {
                'success': False,
                'error_type': 'no_space',
                'message': f'Disk full or serious error (code {exit_code})'
            }
        
        return {
            'success': False,
            'error_type': 'unknown_error',
            'message': f'Robocopy failed with code {exit_code}'
        }
