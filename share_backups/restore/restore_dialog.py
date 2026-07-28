"""
Restore dialog for share_backups.
Allows restoring files from backup to a specific date.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from typing import List, Dict, Any, Optional
import os
import shutil


class RestoreDialog:
    """Dialog for restoring files from backup."""
    
    def __init__(self, parent, db_manager):
        self.parent = parent
        self.db = db_manager
        self.result_files: List[Dict] = []
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Restore from Backup")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the restore dialog UI."""
        # Date selection
        date_frame = ttk.LabelFrame(self.dialog, text="Select Date", padding=10)
        date_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(date_frame, text="Target Date (YYYY-MM-DD):").pack(anchor=tk.W)
        self.date_entry = ttk.Entry(date_frame)
        self.date_entry.pack(fill=tk.X, pady=5)
        
        # Set min/max dates from available backups
        self._set_date_range()
        
        # Share selection
        share_frame = ttk.LabelFrame(self.dialog, text="Select Shares", padding=10)
        share_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.share_vars = {}
        shares = self._get_available_shares()
        
        all_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            share_frame, 
            text="All Shares",
            variable=all_var,
            command=lambda: self._toggle_all_shares(all_var)
        ).pack(anchor=tk.W)
        
        for share in shares:
            var = tk.BooleanVar(value=True)
            self.share_vars[share] = var
            cb = ttk.Checkbutton(share_frame, text=share, variable=var)
            cb.pack(anchor=tk.W)
        
        # Destination path
        dest_frame = ttk.LabelFrame(self.dialog, text="Destination", padding=10)
        dest_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(dest_frame, text="Restore Target (required):").pack(anchor=tk.W)
        
        dest_path_frame = ttk.Frame(dest_frame)
        dest_path_frame.pack(fill=tk.X, pady=5)
        
        self.dest_entry = ttk.Entry(dest_path_frame)
        self.dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(
            dest_path_frame,
            text="Browse...",
            command=self._browse_destination
        ).pack(side=tk.RIGHT, padx=5)
        
        # Warning
        warning_label = ttk.Label(
            dest_frame,
            text="⚠️ Files with same names will be overwritten!",
            foreground="red"
        )
        warning_label.pack(anchor=tk.W, pady=5)
        
        # Preview button
        ttk.Button(
            self.dialog,
            text="Preview Files",
            command=self._preview_restore
        ).pack(pady=10)
        
        # Preview list
        preview_frame = ttk.LabelFrame(self.dialog, text="Files to Restore", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollable listbox
        list_frame = ttk.Frame(preview_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.file_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)
        
        # Action buttons
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.restore_btn = ttk.Button(
            btn_frame,
            text="Restore",
            command=self._do_restore,
            state=tk.DISABLED
        )
        self.restore_btn.pack(side=tk.RIGHT)
        
        ttk.Button(
            btn_frame,
            text="Cancel",
            command=self.dialog.destroy
        ).pack(side=tk.RIGHT, padx=5)
    
    def _set_date_range(self):
        """Set min/max dates based on available backups."""
        # Get date range from backup_log
        # Placeholder - would query database
        now = datetime.now()
        self.date_entry.insert(0, now.strftime("%Y-%m-%d"))
    
    def _get_available_shares(self) -> List[str]:
        """Get list of shares with backups."""
        # Query backuped_files for distinct share_nic values
        # Placeholder
        return ["share1", "share2"]
    
    def _toggle_all_shares(self, all_var: tk.BooleanVar):
        """Toggle all share checkboxes."""
        state = all_var.get()
        for var in self.share_vars.values():
            var.set(state)
    
    def _browse_destination(self):
        """Open folder browser for destination."""
        path = filedialog.askdirectory(parent=self.parent)
        if path:
            self.dest_entry.delete(0, tk.END)
            self.dest_entry.insert(0, path)
    
    def _preview_restore(self):
        """Preview files that will be restored."""
        target_date = self.date_entry.get()
        
        try:
            # Validate date format
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Invalid date format. Use YYYY-MM-DD")
            return
        
        # Clear current list
        self.file_listbox.delete(0, tk.END)
        
        # Find last full backup before target date
        full_backup = self.db.get_full_backup_before_date(target_date)
        if not full_backup:
            messagebox.showwarning("Warning", "No full backup found before selected date")
            return
        
        files_to_restore = []
        
        # Get files from full backup
        full_files = self.db.get_files_for_backup(full_backup['backup_id'])
        files_to_restore.extend(full_files)
        
        # Get incremental backups between full and target
        incrementals = self.db.get_incremental_backups_between(
            full_backup['backup_id'], 
            f"{target_date} 23:59:59"
        )
        
        # Apply incrementals (newer versions replace older)
        file_map = {(f['share_nic'], f['file_path']): f for f in full_files}
        
        for inc_backup in incrementals:
            inc_files = self.db.get_files_for_backup(inc_backup['backup_id'])
            for f in inc_files:
                key = (f['share_nic'], f['file_path'])
                file_map[key] = f  # Replace with newer version
        
        # Handle deletions
        deleted = self.db.get_deleted_files_before_date(f"{target_date} 23:59:59")
        for d in deleted:
            key = (d['share_nic'], d['file_path'])
            if key in file_map:
                del file_map[key]  # Remove if deleted and not re-created
        
        # Filter by selected shares
        selected_shares = [s for s, v in self.share_vars.items() if v.get()]
        
        # Display in listbox
        count = 0
        for key, file_info in sorted(file_map.items()):
            if file_info['share_nic'] in selected_shares:
                display = f"{file_info['share_nic']}/{file_info['file_path']} ({file_info['file_size']} bytes)"
                self.file_listbox.insert(tk.END, display)
                files_to_restore.append(file_info)
                count += 1
        
        self.result_files = files_to_restore
        
        if count == 0:
            self.file_listbox.insert(tk.END, "(No files to restore)")
            self.restore_btn.config(state=tk.DISABLED)
        else:
            self.restore_btn.config(state=tk.NORMAL)
    
    def _do_restore(self):
        """Execute the restore operation."""
        dest_path = self.dest_entry.get().strip()
        
        if not dest_path:
            messagebox.showerror("Error", "Please select a destination folder")
            return
        
        if not os.path.exists(dest_path):
            try:
                os.makedirs(dest_path)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot create destination: {e}")
                return
        
        # Confirm overwrite
        result = messagebox.askyesno(
            "Confirm Restore",
            f"Restore {len(self.result_files)} files to:\n{dest_path}\n\n"
            "Existing files with same names will be overwritten.\n\nContinue?"
        )
        
        if not result:
            return
        
        # Perform restore
        restored_count = 0
        errors = []
        
        for file_info in self.result_files:
            try:
                # Build source path from backup structure
                # Format: <target_backup_path>/<backup_id>_main/<share_nic>/<file_path>
                # This is simplified - real impl would track actual backup locations
                
                source_path = self._get_file_backup_path(file_info)
                dest_file = os.path.join(dest_path, file_info['share_nic'], file_info['file_path'])
                
                # Create directory
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                
                # Copy file
                if os.path.exists(source_path):
                    shutil.copy2(source_path, dest_file)
                    restored_count += 1
                else:
                    errors.append(f"Source not found: {file_info['file_path']}")
                    
            except Exception as e:
                errors.append(f"{file_info['file_path']}: {e}")
        
        # Report results
        if errors:
            messagebox.showwarning(
                "Restore Complete with Errors",
                f"Restored: {restored_count} files\nErrors: {len(errors)}\n\n"
                "First few errors:\n" + "\n".join(errors[:5])
            )
        else:
            messagebox.showinfo(
                "Restore Complete",
                f"Successfully restored {restored_count} files to:\n{dest_path}"
            )
        
        self.dialog.destroy()
    
    def _get_file_backup_path(self, file_info: Dict) -> str:
        """Get actual backup path for a file."""
        # This would need to find the correct backup folder
        # Simplified placeholder
        return f"/backups/{file_info['backup_id']}_main/{file_info['share_nic']}/{file_info['file_path']}"
