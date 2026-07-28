"""
Main window for share_backups application.
TCL/TK based GUI with tabs for configuration, status, and restore.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from typing import Optional
import os
import sys

# Add paths for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from share_backups.db.db_manager import DBManager
    from share_backups.config.ini_handler import ConfigHandler
    from share_backups.auth.credentials import CredentialsManager
    from share_backups.scheduler.scheduler import BackupScheduler
    from share_backups.backup.full_backup import FullBackup
    from share_backups.backup.incremental_backup import IncrementalBackup
except ImportError:
    from db.db_manager import DBManager
    from config.ini_handler import ConfigHandler
    from auth.credentials import CredentialsManager
    from scheduler.scheduler import BackupScheduler
    from backup.full_backup import FullBackup
    from backup.incremental_backup import IncrementalBackup


class MainWindow:
    """Main application window."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Share Backups")
        self.root.geometry("800x600")
        
        # Paths
        self.app_dir = os.path.join(os.path.expanduser("~"), ".share_backups")
        os.makedirs(self.app_dir, exist_ok=True)
        
        self.db_path = os.path.join(self.app_dir, "backups.db")
        self.ini_path = os.path.join(self.app_dir, "config.ini")
        self.cred_path = os.path.join(self.app_dir, "credentials.bin")
        
        # Initialize components
        self.db = DBManager(self.db_path)
        self.cm = CredentialsManager(self.cred_path)
        self.config = ConfigHandler(self.ini_path)
        
        self.master_key: Optional[bytes] = None
        self.scheduler: Optional[BackupScheduler] = None
        
        # State tracking
        self.catch_up_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="idle")
        
        # Build UI
        self._build_ui()
        
        # Check if first run
        if not self.cm.exists():
            self._show_init_dialog()
        else:
            self._show_login_dialog()
    
    def _build_ui(self):
        """Build the main UI."""
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Settings", command=self._show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)
        
        # Main notebook (tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Status tab
        self.status_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.status_frame, text="Status")
        self._build_status_tab()
        
        # Config tab
        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text="Configuration")
        self._build_config_tab()
        
        # Restore tab
        self.restore_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.restore_frame, text="Restore")
        self._build_restore_tab()
        
        # Status bar
        self.status_bar = ttk.Label(
            self.root, 
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Update status periodically
        self._update_status()
    
    def _build_status_tab(self):
        """Build status tab content."""
        # Current state frame
        state_frame = ttk.LabelFrame(self.status_frame, text="Current State", padding=10)
        state_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.state_label = ttk.Label(state_frame, text="Status: idle", font=("Arial", 12))
        self.state_label.pack(anchor=tk.W)
        
        self.last_backup_label = ttk.Label(state_frame, text="Last backup: N/A")
        self.last_backup_label.pack(anchor=tk.W)
        
        # Controls
        control_frame = ttk.Frame(self.status_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Checkbutton(
            control_frame,
            text="Запуск просроченных бэкапов",
            variable=self.catch_up_var,
            command=self._toggle_catch_up
        ).pack(side=tk.LEFT)
        
        self.cancel_btn = ttk.Button(
            control_frame,
            text="Отменить текущий бэкап",
            command=self._cancel_backup,
            state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.RIGHT)
    
    def _build_config_tab(self):
        """Build configuration tab content."""
        # Placeholder - would have full config editor
        ttk.Label(
            self.config_frame,
            text="Configuration Editor\n(Shares, Cron Profiles, Target Path)"
        ).pack(pady=20)
        
        ttk.Button(
            self.config_frame,
            text="Edit Shares",
            command=self._edit_shares
        ).pack(pady=5)
        
        ttk.Button(
            self.config_frame,
            text="Edit Cron Profiles",
            command=self._edit_cron
        ).pack(pady=5)
        
        ttk.Button(
            self.config_frame,
            text="Change Master Password",
            command=self._change_password
        ).pack(pady=20)
    
    def _build_restore_tab(self):
        """Build restore tab content."""
        # Placeholder - would have restore dialog
        ttk.Label(
            self.restore_frame,
            text="Restore Files from Backup\n(Select Date, Share, Destination)"
        ).pack(pady=20)
        
        ttk.Button(
            self.restore_frame,
            text="Restore...",
            command=self._show_restore_dialog
        ).pack(pady=10)
    
    def _show_init_dialog(self):
        """Show initial setup dialog for new users."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Initial Setup")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Set Master Password").pack(pady=10)
        
        pass_entry = ttk.Entry(dialog, show="*")
        pass_entry.pack(pady=5)
        
        confirm_entry = ttk.Entry(dialog, show="*")
        confirm_entry.pack(pady=5)
        
        def on_submit():
            password = pass_entry.get()
            confirm = confirm_entry.get()
            
            if password != confirm:
                messagebox.showerror("Error", "Passwords do not match")
                return
            
            if len(password) < 4:
                messagebox.showerror("Error", "Password too short (min 4 chars)")
                return
            
            if self.cm.initialize(password):
                self.master_key = self.cm.get_derived_key(password)
                self.config.load(self.master_key)
                dialog.destroy()
                self._start_scheduler()
            else:
                messagebox.showerror("Error", "Failed to initialize credentials")
        
        ttk.Button(dialog, text="OK", command=on_submit).pack(pady=10)
    
    def _show_login_dialog(self):
        """Show login dialog for existing users."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Login")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Enter Master Password").pack(pady=10)
        
        pass_entry = ttk.Entry(dialog, show="*")
        pass_entry.pack(pady=5)
        pass_entry.focus()
        
        def on_submit():
            password = pass_entry.get()
            
            if self.cm.verify_password(password):
                self.master_key = self.cm.get_derived_key(password)
                self.config.load(self.master_key)
                dialog.destroy()
                self._start_scheduler()
            else:
                messagebox.showerror("Error", "Invalid password")
        
        pass_entry.bind("<Return>", lambda e: on_submit())
        ttk.Button(dialog, text="OK", command=on_submit).pack(pady=10)
    
    def _start_scheduler(self):
        """Start the backup scheduler."""
        self.scheduler = BackupScheduler(
            self.db, 
            self.config,
            self._run_backup
        )
        self.scheduler.set_catch_up_mode(self.catch_up_var.get())
        self.scheduler.start()
    
    def _run_backup(self, cron_id: int, backup_type: str) -> bool:
        """Execute backup (called by scheduler)."""
        target_path = self.config.get_target_path()
        
        if backup_type == 'full':
            backup = FullBackup(self.db, self.config, target_path)
        else:
            backup = IncrementalBackup(self.db, self.config, target_path)
        
        return backup.execute(cron_id)
    
    def _update_status(self):
        """Update status display from database."""
        state = self.db.get_current_state()
        if state:
            status = state['status']
            self.status_var.set(f"Status: {status}")
            
            if status == 'running':
                self.state_label.config(text=f"Status: RUNNING (Backup #{state.get('current_backup_id')})")
                self.cancel_btn.config(state=tk.NORMAL)
            else:
                last_id = state.get('last_success_backup_id')
                last_time = state.get('last_success_backup_timestamp', 'N/A')
                self.state_label.config(text=f"Status: {status}")
                self.last_backup_label.config(text=f"Last successful backup: #{last_id} at {last_time}")
                self.cancel_btn.config(state=tk.DISABLED)
        
        # Schedule next update
        self.root.after(5000, self._update_status)
    
    def _toggle_catch_up(self):
        """Toggle catch-up mode."""
        if self.scheduler:
            self.scheduler.set_catch_up_mode(self.catch_up_var.get())
    
    def _cancel_backup(self):
        """Cancel current backup."""
        # Would need reference to running backup object
        messagebox.showinfo("Info", "Cancel requested")
    
    def _show_settings(self):
        """Show settings dialog."""
        messagebox.showinfo("Settings", "Settings dialog placeholder")
    
    def _show_about(self):
        """Show about dialog."""
        messagebox.showinfo("About", "Share Backups v1.0\nBackup SMB shares with incremental support")
    
    def _edit_shares(self):
        """Open share editor."""
        messagebox.showinfo("Edit Shares", "Share editor placeholder")
    
    def _edit_cron(self):
        """Open cron editor."""
        messagebox.showinfo("Edit Cron", "Cron editor placeholder")
    
    def _change_password(self):
        """Open change password dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Change Master Password")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Current Password").pack(pady=5)
        old_pass = ttk.Entry(dialog, show="*")
        old_pass.pack(pady=5)
        
        ttk.Label(dialog, text="New Password").pack(pady=5)
        new_pass = ttk.Entry(dialog, show="*")
        new_pass.pack(pady=5)
        
        ttk.Label(dialog, text="Confirm New Password").pack(pady=5)
        confirm_pass = ttk.Entry(dialog, show="*")
        confirm_pass.pack(pady=5)
        
        def on_submit():
            old = old_pass.get()
            new = new_pass.get()
            confirm = confirm_pass.get()
            
            if new != confirm:
                messagebox.showerror("Error", "New passwords do not match")
                return
            
            if not self.cm.verify_password(old):
                messagebox.showerror("Error", "Current password is incorrect")
                return
            
            if self.cm.change_password(old, new):
                # Re-encrypt shares with new key
                old_key = self.cm.get_derived_key(old)
                new_key = self.cm.get_derived_key(new)
                self.config.reencrypt_shares(old_key, new_key)
                
                self.master_key = new_key
                messagebox.showinfo("Success", "Password changed successfully")
                dialog.destroy()
            else:
                messagebox.showerror("Error", "Failed to change password")
        
        ttk.Button(dialog, text="OK", command=on_submit).pack(pady=10)
    
    def _show_restore_dialog(self):
        """Show restore dialog."""
        messagebox.showinfo("Restore", "Restore dialog placeholder")
    
    def _on_close(self):
        """Handle window close."""
        if self.scheduler:
            self.scheduler.stop()
        self.root.destroy()
    
    def run(self):
        """Run the application."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()
