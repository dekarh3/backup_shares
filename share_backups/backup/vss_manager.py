"""
VSS (Volume Shadow Copy Service) manager for share_backups.
Handles creation and deletion of shadow copies for SMB shares.
Windows-only functionality using ctypes.
"""

import ctypes
from ctypes import wintypes
from typing import Optional, Dict, List
import re


class VSSManager:
    """Manages VSS shadow copies for backup operations."""
    
    # VSS constants
    VSS_E_OBJECT_ALREADY_EXISTS = 0x80042305
    
    def __init__(self):
        self._shadow_copies: Dict[str, str] = {}  # source_path -> shadow_path
        self._vss_client = None
    
    def create_shadow_copy(self, source_path: str) -> Optional[str]:
        """
        Create a shadow copy of the volume containing source_path.
        
        Args:
            source_path: UNC path or local path to create shadow of
            
        Returns:
            Shadow copy path if successful, None otherwise
        """
        # Note: Full VSS implementation requires Windows COM interop
        # This is a simplified version - in production would use pywin32
        
        try:
            # For SMB shares, we need to handle them differently
            # VSS works on local volumes, so for remote shares we may need
            # to use the share's built-in shadow copy access
            
            if source_path.startswith('\\\\'):
                # UNC path - try to access via shadow copy endpoint
                # Format: \\server\share\path -> \\server\share~snapshot_name\path
                shadow_path = self._get_unc_shadow_path(source_path)
                if shadow_path:
                    self._shadow_copies[source_path] = shadow_path
                    return shadow_path
            
            # For local paths, would use VSS COM API
            # This requires pywin32 or similar
            print(f"VSS: Would create shadow for {source_path}")
            return source_path  # Fallback to original path
            
        except Exception as e:
            print(f"VSS error creating shadow for {source_path}: {e}")
            return None
    
    def _get_unc_shadow_path(self, unc_path: str) -> Optional[str]:
        """
        Get shadow copy path for UNC share.
        Tries to enumerate available shadow copies on the remote server.
        """
        # Extract server and share name
        match = re.match(r'\\\\([^\\]+)\\([^\\]+)(.*)', unc_path)
        if not match:
            return None
        
        server, share, rest = match.groups()
        
        # Try to access shadow copies via the "Shadow Copies" tab mechanism
        # This typically requires querying the server's WMI or using specific APIs
        # For now, return the original path with a note
        
        # In production, would use:
        # - WMI query: SELECT * FROM Win32_ShadowCopy WHERE ClientAccessible = TRUE
        # - Or query \\server\share for available snapshots via FSCTL
        
        print(f"VSS: Checking shadow copies on {server} for share {share}")
        
        # Placeholder - actual implementation needs pywin32/WMI
        return None
    
    def delete_shadow_copy(self, source_path: str) -> bool:
        """
        Delete a previously created shadow copy.
        
        Args:
            source_path: Original source path
            
        Returns:
            True if deleted successfully
        """
        if source_path not in self._shadow_copies:
            return True  # Nothing to delete
        
        try:
            shadow_path = self._shadow_copies[source_path]
            
            # For VSS, we'd call IVssAsync::Cancel or delete the shadow copy
            # For this implementation, just remove from tracking
            
            del self._shadow_copies[source_path]
            print(f"VSS: Released shadow copy for {source_path}")
            return True
            
        except Exception as e:
            print(f"VSS error deleting shadow for {source_path}: {e}")
            return False
    
    def delete_all_shadow_copies(self) -> bool:
        """Delete all tracked shadow copies."""
        success = True
        for source_path in list(self._shadow_copies.keys()):
            if not self.delete_shadow_copy(source_path):
                success = False
        return success
    
    def get_shadow_path(self, source_path: str) -> str:
        """Get shadow copy path for a source, or original if no shadow."""
        return self._shadow_copies.get(source_path, source_path)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup on context exit."""
        self.delete_all_shadow_copies()


def check_admin_privileges() -> bool:
    """
    Check if running with administrator privileges.
    Required for VSS operations and ACL preservation.
    """
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        # Non-Windows or error checking
        return False


def run_as_admin():
    """
    Re-launch current script with admin privileges.
    Uses UAC elevation on Windows.
    """
    import sys
    import os
    
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            " ".join([f'"{arg}"' for arg in sys.argv]),
            os.getcwd(),
            1  # SW_SHOWNORMAL
        )
    except Exception as e:
        print(f"Failed to elevate: {e}")
        sys.exit(1)
