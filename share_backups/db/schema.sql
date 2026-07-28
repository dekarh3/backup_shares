-- SQLite schema for share_backups

-- Table: backuped_files - saved files during full and incremental backups
CREATE TABLE IF NOT EXISTS backuped_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_id INTEGER NOT NULL,
    cron_id INTEGER NOT NULL,
    backup_type TEXT NOT NULL CHECK(backup_type IN ('full', 'incremental')),
    share_nic TEXT NOT NULL,
    share_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_attributes TEXT,  -- JSON
    file_permissions TEXT,  -- JSON
    created_time TEXT,
    modified_time TEXT,
    backup_timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_backuped_files_backup_id ON backuped_files(backup_id);
CREATE INDEX IF NOT EXISTS idx_backuped_files_share_nic ON backuped_files(share_nic);
CREATE INDEX IF NOT EXISTS idx_backuped_files_file_path ON backuped_files(file_path);

-- Table: deleted_files - files deleted from source between backups
CREATE TABLE IF NOT EXISTS deleted_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_id INTEGER NOT NULL,
    full_backup_id INTEGER NOT NULL,
    cron_id INTEGER NOT NULL,
    share_nic TEXT NOT NULL,
    share_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    deletion_timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deleted_files_backup_id ON deleted_files(backup_id);
CREATE INDEX IF NOT EXISTS idx_deleted_files_share_nic ON deleted_files(share_nic);

-- Table: current_state - current program state (single row)
CREATE TABLE IF NOT EXISTS current_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    status TEXT NOT NULL DEFAULT 'idle' CHECK(status IN ('idle', 'running', 'error', 'no_space')),
    current_cron_id INTEGER,
    current_backup_id INTEGER,
    current_backup_timestamp TEXT,
    current_backup_type TEXT CHECK(current_backup_type IN ('full', 'incremental')),
    last_success_cron_id INTEGER,
    last_success_backup_id INTEGER,
    last_success_backup_timestamp TEXT,
    last_success_backup_type TEXT CHECK(last_success_backup_type IN ('full', 'incremental')),
    last_processed_cron_time TEXT
);

-- Table: temp_file_list - temporary table for current backup file list
CREATE TABLE IF NOT EXISTS temp_file_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    share_nic TEXT NOT NULL,
    share_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_attributes TEXT,
    file_permissions TEXT,
    created_time TEXT,
    modified_time TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'copied', 'skipped'))
);

-- Table: temp_deleted_list - temporary table for deleted files during incremental backup
CREATE TABLE IF NOT EXISTS temp_deleted_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    share_nic TEXT NOT NULL,
    share_name TEXT NOT NULL,
    file_path TEXT NOT NULL
);

-- Table: backup_log - journal of all backups
CREATE TABLE IF NOT EXISTS backup_log (
    backup_id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_type TEXT NOT NULL CHECK(backup_type IN ('full', 'incremental')),
    cron_id INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running', 'success', 'error', 'cancelled', 'no_space', 'skipped'))
);

-- Table: error_cooldown - cooldown tracking for failed cron jobs
CREATE TABLE IF NOT EXISTS error_cooldown (
    cron_id INTEGER PRIMARY KEY,
    last_error_time TEXT,
    error_count INTEGER NOT NULL DEFAULT 0
);

-- Table: current_file_state - current state of files on shares (snapshot at last backup)
CREATE TABLE IF NOT EXISTS current_file_state (
    share_nic TEXT NOT NULL,
    file_path TEXT NOT NULL,
    last_backup_id INTEGER NOT NULL,
    file_size INTEGER NOT NULL,
    modified_time TEXT,
    attributes_hash TEXT,
    PRIMARY KEY (share_nic, file_path)
);
