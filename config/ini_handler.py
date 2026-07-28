"""
INI configuration handler for share_backups.
Handles reading/writing .ini file with encrypted share passwords.
Uses atomic file operations for safety.
"""

import os
import json
import tempfile
import configparser
from typing import List, Dict, Any, Optional
from base64 import b64encode, b64decode

try:
    from share_backups.auth.credentials import (
        encrypt_share_password, 
        decrypt_share_password,
        CredentialsManager
    )
except ImportError:
    from auth.credentials import (
        encrypt_share_password, 
        decrypt_share_password,
        CredentialsManager
    )


class ConfigHandler:
    """Handles .ini configuration file with encrypted credentials."""
    
    ENCRYPTION_MARKER = 'ENC:'  # Marker for encrypted values
    
    def __init__(self, ini_path: str):
        self.ini_path = ini_path
        self.config = configparser.ConfigParser()
        self._shares_cache: List[Dict[str, Any]] = []
        self._cron_profiles_cache: List[Dict[str, Any]] = []
        self._target_path: str = ''
    
    def load(self, master_key: Optional[bytes] = None) -> bool:
        """
        Load configuration from .ini file.
        If master_key is provided, decrypt share passwords.
        Returns True on success.
        """
        if not os.path.exists(self.ini_path):
            return False
        
        try:
            self.config.read(self.ini_path, encoding='utf-8')
            
            # Parse shares
            self._shares_cache = []
            if self.config.has_section('shares'):
                shares_json = self.config.get('shares', 'list', fallback='[]')
                share_ids = json.loads(shares_json)
                
                for share_id in share_ids:
                    section = f'share:{share_id}'
                    if self.config.has_section(section):
                        share_data = {
                            'id': share_id,
                            'share_nic': self.config.get(section, 'share_nic', fallback=''),
                            'share_name': self.config.get(section, 'share_name', fallback=''),
                            'login': self.config.get(section, 'login', fallback=''),
                            'password_encrypted': self.config.get(section, 'password', fallback=''),
                            'password': None,  # Decrypted if key provided
                            'mt_threads': self.config.getint(section, 'mt_threads', fallback=8)
                        }
                        
                        # Decrypt password if key provided
                        if master_key and share_data['password_encrypted']:
                            try:
                                enc_str = share_data['password_encrypted']
                                if enc_str.startswith(self.ENCRYPTION_MARKER):
                                    enc_str = enc_str[len(self.ENCRYPTION_MARKER):]
                                share_data['password'] = decrypt_share_password(
                                    enc_str, master_key)
                            except Exception:
                                share_data['password'] = None
                        
                        self._shares_cache.append(share_data)
            
            # Parse cron profiles
            self._cron_profiles_cache = []
            if self.config.has_section('cron_profiles'):
                profiles_json = self.config.get('cron_profiles', 'list', fallback='[]')
                profile_ids = json.loads(profiles_json)
                
                for profile_id in profile_ids:
                    section = f'cron:{profile_id}'
                    if self.config.has_section(section):
                        profile_data = {
                            'cron_id': int(profile_id),
                            'backup_type': self.config.get(section, 'backup_type', fallback='incremental'),
                            'cron_request': self.config.get(section, 'cron_request', fallback='0 2 * * *')
                        }
                        self._cron_profiles_cache.append(profile_data)
            
            # Parse target path
            if self.config.has_section('general'):
                self._target_path = self.config.get('general', 'target_backup_path', fallback='')
            
            return True
        except Exception as e:
            print(f"Error loading config: {e}")
            return False
    
    def save(self, master_key: bytes) -> bool:
        """
        Save configuration to .ini file atomically.
        Encrypts share passwords with master_key.
        Returns True on success.
        """
        try:
            new_config = configparser.ConfigParser()
            
            # General section
            new_config.add_section('general')
            new_config.set('general', 'target_backup_path', self._target_path)
            
            # Shares section
            new_config.add_section('shares')
            share_ids = [s['id'] for s in self._shares_cache]
            new_config.set('shares', 'list', json.dumps(share_ids))
            
            for share in self._shares_cache:
                section = f"share:{share['id']}"
                new_config.add_section(section)
                new_config.set(section, 'share_nic', share['share_nic'])
                new_config.set(section, 'share_name', share['share_name'])
                new_config.set(section, 'login', share['login'])
                
                # Encrypt password
                if share.get('password'):
                    encrypted = encrypt_share_password(share['password'], master_key)
                    new_config.set(section, 'password', f'{self.ENCRYPTION_MARKER}{encrypted}')
                elif share.get('password_encrypted'):
                    # Keep existing encrypted password
                    new_config.set(section, 'password', share['password_encrypted'])
                
                new_config.set(section, 'mt_threads', str(share['mt_threads']))
            
            # Cron profiles section
            new_config.add_section('cron_profiles')
            profile_ids = [str(p['cron_id']) for p in self._cron_profiles_cache]
            new_config.set('cron_profiles', 'list', json.dumps(profile_ids))
            
            for profile in self._cron_profiles_cache:
                section = f"cron:{profile['cron_id']}"
                new_config.add_section(section)
                new_config.set(section, 'backup_type', profile['backup_type'])
                new_config.set(section, 'cron_request', profile['cron_request'])
            
            # Atomic write
            return self._atomic_write_config(new_config)
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def _atomic_write_config(self, config: configparser.ConfigParser) -> bool:
        """Write config atomically using temp file + rename."""
        try:
            dir_path = os.path.dirname(self.ini_path)
            
            # Write to temporary file
            fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix='.config_', suffix='.ini')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    config.write(f)
                
                # Atomic rename
                os.replace(temp_path, self.ini_path)
                return True
            except Exception:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
        except Exception as e:
            print(f"Error writing config: {e}")
            return False
    
    def reencrypt_shares(self, old_key: bytes, new_key: bytes) -> bool:
        """
        Re-encrypt all share passwords with new key.
        Used when changing master password.
        """
        try:
            for share in self._shares_cache:
                if share.get('password'):
                    # Already decrypted, just re-encrypt with new key
                    pass  # Will be encrypted on save
                elif share.get('password_encrypted'):
                    # Need to decrypt with old key first
                    enc_str = share['password_encrypted']
                    if enc_str.startswith(self.ENCRYPTION_MARKER):
                        enc_str = enc_str[len(self.ENCRYPTION_MARKER):]
                    share['password'] = decrypt_share_password(enc_str, old_key)
            
            return self.save(new_key)
        except Exception as e:
            print(f"Error re-encrypting shares: {e}")
            return False
    
    # ==================== Getters ====================
    
    def get_shares(self) -> List[Dict[str, Any]]:
        """Get list of configured shares."""
        return self._shares_cache.copy()
    
    def get_cron_profiles(self) -> List[Dict[str, Any]]:
        """Get list of cron profiles."""
        return self._cron_profiles_cache.copy()
    
    def get_target_path(self) -> str:
        """Get target backup path."""
        return self._target_path
    
    # ==================== Setters ====================
    
    def set_target_path(self, path: str):
        """Set target backup path."""
        self._target_path = path
    
    def add_share(self, share_nic: str, share_name: str, login: str, 
                  password: str, mt_threads: int = 8) -> int:
        """Add new share configuration."""
        share_id = len(self._shares_cache) + 1
        self._shares_cache.append({
            'id': share_id,
            'share_nic': share_nic,
            'share_name': share_name,
            'login': login,
            'password': password,
            'password_encrypted': '',
            'mt_threads': mt_threads
        })
        return share_id
    
    def update_share(self, share_id: int, **kwargs) -> bool:
        """Update share configuration."""
        for share in self._shares_cache:
            if share['id'] == share_id:
                share.update(kwargs)
                return True
        return False
    
    def remove_share(self, share_id: int) -> bool:
        """Remove share configuration."""
        for i, share in enumerate(self._shares_cache):
            if share['id'] == share_id:
                self._shares_cache.pop(i)
                return True
        return False
    
    def add_cron_profile(self, backup_type: str, cron_request: str) -> int:
        """Add new cron profile."""
        cron_id = len(self._cron_profiles_cache) + 1
        self._cron_profiles_cache.append({
            'cron_id': cron_id,
            'backup_type': backup_type,
            'cron_request': cron_request
        })
        return cron_id
    
    def update_cron_profile(self, cron_id: int, **kwargs) -> bool:
        """Update cron profile."""
        for profile in self._cron_profiles_cache:
            if profile['cron_id'] == cron_id:
                profile.update(kwargs)
                return True
        return False
    
    def remove_cron_profile(self, cron_id: int) -> bool:
        """Remove cron profile."""
        for i, profile in enumerate(self._cron_profiles_cache):
            if profile['cron_id'] == cron_id:
                self._cron_profiles_cache.pop(i)
                return True
        return False
    
    def clear_share_credentials(self):
        """Clear all share passwords (used when resetting master password)."""
        for share in self._shares_cache:
            share['password'] = ''
            share['password_encrypted'] = ''
