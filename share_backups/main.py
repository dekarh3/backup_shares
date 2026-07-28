"""
Main entry point for share_backups.
Handles admin check, single instance enforcement, and application startup.
"""

import sys
import os
import ctypes
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_admin_privileges() -> bool:
    """Check if running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        # On non-Windows or error, assume OK for testing
        return True


def run_as_admin():
    """Re-launch current script with admin privileges using UAC."""
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            " ".join([f'"{arg}"' for arg in sys.argv]),
            os.getcwd(),
            1  # SW_SHOWNORMAL
        )
        return True
    except Exception as e:
        print(f"Failed to elevate privileges: {e}")
        return False


def check_single_instance(mutex_name: str = "ShareBackupsMutex") -> bool:
    """
    Check if another instance is already running.
    Uses Windows named mutex.
    
    Returns True if this is the only instance.
    """
    try:
        import ctypes.wintypes
        
        # Try to create/open mutex
        kernel32 = ctypes.windll.kernel32
        CreateMutexW = kernel32.CreateMutexW
        GetLastError = kernel32.GetLastError
        CloseHandle = kernel32.CloseHandle
        
        ERROR_ALREADY_EXISTS = 183
        
        mutex = CreateMutexW(None, True, mutex_name)
        
        if GetLastError() == ERROR_ALREADY_EXISTS:
            # Another instance exists
            CloseHandle(mutex)
            return False
        
        # Store mutex handle for later cleanup
        check_single_instance._mutex = mutex
        return True
        
    except Exception:
        # On error or non-Windows, allow running
        return True


def release_mutex():
    """Release the single-instance mutex."""
    try:
        mutex = getattr(check_single_instance, '_mutex', None)
        if mutex:
            ctypes.windll.kernel32.CloseHandle(mutex)
    except Exception:
        pass


def show_admin_error():
    """Show error dialog about admin privileges requirement."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        messagebox.showerror(
            "Administrator Privileges Required",
            "Для корректного сохранения прав доступа (ACL) "
            "программа должна быть запущена от имени Администратора."
        )
        
        root.destroy()
    except Exception:
        print("ERROR: Program must be run as Administrator for ACL preservation.")


def main():
    """Main entry point."""
    # Check admin privileges
    if not check_admin_privileges():
        # Ask user if they want to elevate
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()
            
            result = messagebox.askyesno(
                "Elevate Privileges",
                "Программа должна быть запущена от имени Администратора.\n"
                "Запустить с повышенными привилегиями?"
            )
            
            if result:
                if run_as_admin():
                    sys.exit(0)
            
            root.destroy()
        except Exception:
            pass
        
        show_admin_error()
        sys.exit(1)
    
    # Check single instance
    if not check_single_instance():
        print("Another instance of ShareBackups is already running.")
        sys.exit(1)
    
    try:
        # Import and run the main application
        from share_backups.ui.main_window import MainWindow
        
        app = MainWindow()
        app.run()
        
    except ImportError as e:
        print(f"Import error: {e}")
        print("Make sure all dependencies are installed:")
        print("  pip install croniter pycryptodome pystray")
        sys.exit(1)
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        release_mutex()


if __name__ == '__main__':
    main()
