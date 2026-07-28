"""
Database manager for share_backups.
Handles CRUD operations for all tables, mass inserts, and connection management.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager


class DBManager:
    """Database manager for share_backups SQLite database."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._backup_connection: Optional[sqlite3.Connection] = None
        self._init_database()
    
    def _init_database(self):
        """Initialize database with schema."""
        with self.get_connection() as conn:
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = f.read()
            conn.executescript(schema)
            
            # Initialize current_state with default row if not exists
            conn.execute("""
                INSERT OR IGNORE INTO current_state (id, status, last_processed_cron_time)
                VALUES (1, 'idle', ?)
            """, (datetime.now().isoformat(),))
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """Get a database connection with proper settings."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
        finally:
            conn.close()
    
    @contextmanager
    def backup_connection(self):
        """Get dedicated connection for backup process lifecycle."""
        if self._backup_connection is None:
            self._backup_connection = sqlite3.connect(self.db_path, timeout=30.0)
            self._backup_connection.row_factory = sqlite3.Row
            self._backup_connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield self._backup_connection
        finally:
            pass  # Keep connection open for reuse
    
    def close_backup_connection(self):
        """Close the dedicated backup connection."""
        if self._backup_connection:
            self._backup_connection.close()
            self._backup_connection = None
    
    # ==================== Current State Operations ====================
    
    def get_current_state(self) -> Optional[Dict[str, Any]]:
        """Get current state from database."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM current_state WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def update_current_state(self, **kwargs):
        """Update current state fields."""
        if not kwargs:
            return
        
        fields = ', '.join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        
        with self.get_connection() as conn:
            conn.execute(f"UPDATE current_state SET {fields} WHERE id = 1", values)
            conn.commit()
    
    def set_state_idle(self, backup_id: int = None, cron_id: int = None, 
                       backup_type: str = None, timestamp: str = None):
        """Set state to idle after successful backup."""
        with self.get_connection() as conn:
            if backup_id and timestamp and backup_type:
                conn.execute("""
                    UPDATE current_state SET 
                        status = 'idle',
                        current_backup_id = NULL,
                        current_backup_timestamp = NULL,
                        current_backup_type = NULL,
                        current_cron_id = NULL,
                        last_success_backup_id = ?,
                        last_success_backup_timestamp = ?,
                        last_success_backup_type = ?,
                        last_success_cron_id = ?,
                        last_processed_cron_time = ?
                    WHERE id = 1
                """, (backup_id, timestamp, backup_type, cron_id, timestamp))
            else:
                conn.execute("""
                    UPDATE current_state SET 
                        status = 'idle',
                        current_backup_id = NULL,
                        current_backup_timestamp = NULL,
                        current_backup_type = NULL,
                        current_cron_id = NULL
                    WHERE id = 1
                """)
            conn.commit()
    
    def set_state_running(self, backup_id: int, cron_id: int, backup_type: str, timestamp: str):
        """Set state to running at backup start."""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE current_state SET 
                    status = 'running',
                    current_backup_id = ?,
                    current_backup_timestamp = ?,
                    current_backup_type = ?,
                    current_cron_id = ?
                WHERE id = 1
            """, (backup_id, timestamp, backup_type, cron_id))
            conn.commit()
    
    def set_state_error(self, error_type: str = 'error'):
        """Set state to error or no_space."""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE current_state SET 
                    status = ?,
                    current_backup_id = NULL,
                    current_backup_timestamp = NULL,
                    current_backup_type = NULL,
                    current_cron_id = NULL
                WHERE id = 1
            """, (error_type,))
            conn.commit()
    
    # ==================== Backup Log Operations ====================
    
    def create_backup_log(self, backup_type: str, cron_id: int, 
                          start_time: str = None) -> int:
        """Create new backup log entry, return backup_id."""
        if start_time is None:
            start_time = datetime.now().isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO backup_log (backup_type, cron_id, start_time, status)
                VALUES (?, ?, ?, 'running')
            """, (backup_type, cron_id, start_time))
            conn.commit()
            return cursor.lastrowid
    
    def update_backup_log(self, backup_id: int, status: str, end_time: str = None):
        """Update backup log entry."""
        if end_time is None:
            end_time = datetime.now().isoformat()
        
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE backup_log SET status = ?, end_time = ?
                WHERE backup_id = ?
            """, (status, end_time, backup_id))
            conn.commit()
    
    def get_last_full_backup_id(self) -> Optional[int]:
        """Get ID of last successful full backup."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT backup_id FROM backup_log 
                WHERE backup_type = 'full' AND status = 'success'
                ORDER BY backup_id DESC LIMIT 1
            """)
            row = cursor.fetchone()
            return row['backup_id'] if row else None
    
    def get_last_successful_backup(self) -> Optional[Dict[str, Any]]:
        """Get last successful backup info."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM backup_log 
                WHERE status = 'success'
                ORDER BY backup_id DESC LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ==================== Temp Table Operations ====================
    
    def clear_temp_tables(self):
        """Clear temporary tables."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM temp_file_list")
            conn.execute("DELETE FROM temp_deleted_list")
            conn.commit()
    
    def drop_temp_tables(self):
        """Drop temporary tables (for cleanup after interrupted backups)."""
        with self.get_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS temp_file_list")
            conn.execute("DROP TABLE IF EXISTS temp_deleted_list")
            conn.commit()
    
    def insert_temp_file(self, share_nic: str, share_name: str, file_path: str,
                         file_size: int, file_attributes: str = None,
                         file_permissions: str = None, created_time: str = None,
                         modified_time: str = None, status: str = 'pending'):
        """Insert file into temp_file_list."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO temp_file_list 
                (share_nic, share_name, file_path, file_size, file_attributes,
                 file_permissions, created_time, modified_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (share_nic, share_name, file_path, file_size, file_attributes,
                  file_permissions, created_time, modified_time, status))
            conn.commit()
    
    def insert_temp_files_batch(self, files: List[Tuple]):
        """Batch insert files into temp_file_list."""
        with self.get_connection() as conn:
            conn.executemany("""
                INSERT INTO temp_file_list 
                (share_nic, share_name, file_path, file_size, file_attributes,
                 file_permissions, created_time, modified_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, files)
            conn.commit()
    
    def update_temp_file_status(self, file_id: int, status: str):
        """Update status of file in temp_file_list."""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE temp_file_list SET status = ? WHERE id = ?
            """, (status, file_id))
            conn.commit()
    
    def get_temp_files(self, status: str = None) -> List[Dict[str, Any]]:
        """Get files from temp_file_list, optionally filtered by status."""
        with self.get_connection() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM temp_file_list WHERE status = ?", (status,))
            else:
                cursor = conn.execute("SELECT * FROM temp_file_list")
            return [dict(row) for row in cursor.fetchall()]
    
    def insert_temp_deleted_files(self, files: List[Tuple]):
        """Batch insert deleted file paths into temp_deleted_list."""
        with self.get_connection() as conn:
            conn.executemany("""
                INSERT INTO temp_deleted_list (share_nic, share_name, file_path)
                VALUES (?, ?, ?)
            """, files)
            conn.commit()
    
    def get_temp_deleted_files(self) -> List[Dict[str, Any]]:
        """Get deleted files from temp_deleted_list."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM temp_deleted_list")
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== Backuped Files Operations ====================
    
    def copy_temp_to_backuped_files(self, backup_id: int, cron_id: int,
                                    backup_type: str, backup_timestamp: str):
        """Copy all records from temp_file_list to backuped_files."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO backuped_files 
                (backup_id, cron_id, backup_type, share_nic, share_name,
                 file_path, file_size, file_attributes, file_permissions,
                 created_time, modified_time, backup_timestamp)
                SELECT ?, ?, ?, share_nic, share_name, file_path, file_size,
                       file_attributes, file_permissions, created_time,
                       modified_time, ?
                FROM temp_file_list WHERE status = 'copied'
            """, (backup_id, cron_id, backup_type, backup_timestamp))
            conn.commit()
    
    # ==================== Deleted Files Operations ====================
    
    def insert_deleted_files(self, backup_id: int, full_backup_id: int,
                             cron_id: int, files: List[Tuple], 
                             deletion_timestamp: str):
        """Insert deleted files into deleted_files table."""
        with self.get_connection() as conn:
            conn.executemany("""
                INSERT INTO deleted_files 
                (backup_id, full_backup_id, cron_id, share_nic, share_name,
                 file_path, deletion_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [(backup_id, full_backup_id, cron_id) + f + (deletion_timestamp,) 
                  for f in files])
            conn.commit()
    
    # ==================== Current File State Operations ====================
    
    def update_current_file_state(self, files: List[Tuple], 
                                  deleted_paths: List[Tuple] = None):
        """
        Update current_file_state table (UPSERT).
        files: list of (share_nic, file_path, last_backup_id, file_size, 
                        modified_time, attributes_hash)
        deleted_paths: list of (share_nic, file_path) to remove
        """
        with self.get_connection() as conn:
            # Insert or update files
            conn.executemany("""
                INSERT INTO current_file_state 
                (share_nic, file_path, last_backup_id, file_size, 
                 modified_time, attributes_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(share_nic, file_path) DO UPDATE SET
                    last_backup_id = excluded.last_backup_id,
                    file_size = excluded.file_size,
                    modified_time = excluded.modified_time,
                    attributes_hash = excluded.attributes_hash
            """, files)
            
            # Delete removed files
            if deleted_paths:
                conn.executemany("""
                    DELETE FROM current_file_state 
                    WHERE share_nic = ? AND file_path = ?
                """, deleted_paths)
            
            conn.commit()
    
    def get_current_file_state(self, share_nic: str = None) -> Dict[Tuple[str, str], Dict]:
        """Get current file state as dict keyed by (share_nic, file_path)."""
        with self.get_connection() as conn:
            if share_nic:
                cursor = conn.execute(
                    "SELECT * FROM current_file_state WHERE share_nic = ?", 
                    (share_nic,))
            else:
                cursor = conn.execute("SELECT * FROM current_file_state")
            
            result = {}
            for row in cursor.fetchall():
                key = (row['share_nic'], row['file_path'])
                result[key] = dict(row)
            return result
    
    # ==================== Error Cooldown Operations ====================
    
    def record_error(self, cron_id: int):
        """Record error for cron job, increment error count."""
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO error_cooldown (cron_id, last_error_time, error_count)
                VALUES (?, ?, 1)
                ON CONFLICT(cron_id) DO UPDATE SET
                    last_error_time = excluded.last_error_time,
                    error_count = error_count + 1
            """, (cron_id, now))
            conn.commit()
    
    def reset_error_cooldown(self, cron_id: int):
        """Reset error cooldown after successful backup."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO error_cooldown (cron_id, last_error_time, error_count)
                VALUES (?, NULL, 0)
                ON CONFLICT(cron_id) DO UPDATE SET
                    last_error_time = NULL,
                    error_count = 0
            """, (cron_id,))
            conn.commit()
    
    def get_error_cooldown(self, cron_id: int) -> Optional[Dict[str, Any]]:
        """Get error cooldown info for cron job."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM error_cooldown WHERE cron_id = ?", (cron_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ==================== Restore Operations ====================
    
    def get_full_backup_before_date(self, target_date: str) -> Optional[Dict]:
        """Get last successful full backup before target date."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT bl.* FROM backup_log bl
                WHERE bl.backup_type = 'full' 
                  AND bl.status = 'success'
                  AND bl.start_time <= ?
                ORDER BY bl.start_time DESC
                LIMIT 1
            """, (target_date,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_incremental_backups_between(self, start_backup_id: int, 
                                        end_date: str) -> List[Dict]:
        """Get incremental backups between two points."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM backup_log
                WHERE backup_type = 'incremental'
                  AND status = 'success'
                  AND backup_id > ?
                  AND start_time <= ?
                ORDER BY backup_id ASC
            """, (start_backup_id, end_date))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_files_for_backup(self, backup_id: int) -> List[Dict]:
        """Get all files for a specific backup."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM backuped_files WHERE backup_id = ?", 
                (backup_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_deleted_files_before_date(self, date: str) -> List[Dict]:
        """Get deleted files up to specified date."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM deleted_files
                WHERE deletion_timestamp <= ?
                ORDER BY deletion_timestamp ASC
            """, (date,))
            return [dict(row) for row in cursor.fetchall()]
