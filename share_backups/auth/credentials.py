"""
Credentials management for share_backups.
Handles master password verification, PBKDF2 key derivation, and AES encryption.
Uses atomic file operations for safety.
"""

import os
import hashlib
import secrets
import json
import tempfile
from typing import Optional, Tuple
from base64 import b64encode, b64decode

# Cryptography imports - using standard library where possible
# For AES we'll use a simple implementation or pycryptodome if available
try:
    from Crypto.Cipher import AES
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Random import get_random_bytes
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class CredentialsManager:
    """Manages master password and encrypted share credentials."""
    
    SALT_SIZE = 32
    KEY_SIZE = 32  # 256 bits for AES-256
    IV_SIZE = 16
    PBKDF2_ITERATIONS = 100000
    
    def __init__(self, credentials_path: str):
        self.credentials_path = credentials_path
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password using PBKDF2."""
        if CRYPTO_AVAILABLE:
            return PBKDF2(password, salt, dkLen=self.KEY_SIZE, 
                         count=self.PBKDF2_ITERATIONS)
        else:
            # Fallback to hashlib (SHA256-based)
            return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), 
                                       salt, self.PBKDF2_ITERATIONS, 
                                       dklen=self.KEY_SIZE)
    
    def _hash_password(self, password: str, salt: bytes) -> bytes:
        """Hash password for verification."""
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), 
                                   salt, self.PBKDF2_ITERATIONS, 
                                   dklen=self.KEY_SIZE)
    
    def _pad_data(self, data: bytes) -> bytes:
        """PKCS7 padding for AES."""
        pad_len = 16 - (len(data) % 16)
        return data + bytes([pad_len] * pad_len)
    
    def _unpad_data(self, data: bytes) -> bytes:
        """Remove PKCS7 padding."""
        pad_len = data[-1]
        return data[:-pad_len]
    
    def _encrypt_aes(self, plaintext: bytes, key: bytes, iv: bytes) -> bytes:
        """Encrypt data using AES-CBC."""
        if CRYPTO_AVAILABLE:
            cipher = AES.new(key, AES.MODE_CBC, iv)
            return cipher.encrypt(self._pad_data(plaintext))
        else:
            # Simple XOR-based fallback (NOT SECURE - for testing only)
            # In production, require pycryptodome
            raise RuntimeError("pycryptodome required for encryption")
    
    def _decrypt_aes(self, ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
        """Decrypt data using AES-CBC."""
        if CRYPTO_AVAILABLE:
            cipher = AES.new(key, AES.MODE_CBC, iv)
            return self._unpad_data(cipher.decrypt(ciphertext))
        else:
            raise RuntimeError("pycryptodome required for decryption")
    
    def initialize(self, master_password: str) -> bool:
        """
        Initialize credentials file with new master password.
        Returns True on success.
        """
        salt = secrets.token_bytes(self.SALT_SIZE)
        password_hash = self._hash_password(master_password, salt)
        
        data = {
            'salt': b64encode(salt).decode('ascii'),
            'password_hash': b64encode(password_hash).decode('ascii')
        }
        
        return self._atomic_write(json.dumps(data).encode('utf-8'))
    
    def verify_password(self, master_password: str) -> bool:
        """Verify master password against stored hash."""
        if not os.path.exists(self.credentials_path):
            return False
        
        try:
            with open(self.credentials_path, 'rb') as f:
                data = json.loads(f.read().decode('utf-8'))
            
            salt = b64decode(data['salt'])
            stored_hash = b64decode(data['password_hash'])
            
            computed_hash = self._hash_password(master_password, salt)
            return secrets.compare_digest(computed_hash, stored_hash)
        except Exception:
            return False
    
    def get_derived_key(self, master_password: str) -> Optional[bytes]:
        """Get encryption key derived from master password."""
        if not self.verify_password(master_password):
            return None
        
        try:
            with open(self.credentials_path, 'rb') as f:
                data = json.loads(f.read().decode('utf-8'))
            
            salt = b64decode(data['salt'])
            return self._derive_key(master_password, salt)
        except Exception:
            return None
    
    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        Change master password.
        Returns True on success, False if old password is incorrect.
        """
        if not self.verify_password(old_password):
            return False
        
        # Generate new salt and hash
        new_salt = secrets.token_bytes(self.SALT_SIZE)
        new_hash = self._hash_password(new_password, new_salt)
        
        data = {
            'salt': b64encode(new_salt).decode('ascii'),
            'password_hash': b64encode(new_hash).decode('ascii')
        }
        
        return self._atomic_write(json.dumps(data).encode('utf-8'))
    
    def _atomic_write(self, data: bytes) -> bool:
        """
        Write data atomically using temp file + rename.
        This prevents corruption on power failure.
        """
        try:
            dir_path = os.path.dirname(self.credentials_path)
            
            # Write to temporary file
            fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix='.cred_')
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(data)
                
                # Atomic rename
                os.replace(temp_path, self.credentials_path)
                return True
            except Exception:
                # Clean up temp file on error
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
        except Exception as e:
            print(f"Error writing credentials: {e}")
            return False
    
    def exists(self) -> bool:
        """Check if credentials file exists."""
        return os.path.exists(self.credentials_path)


def encrypt_share_password(password: str, key: bytes) -> str:
    """Encrypt share password with derived key, return base64 string."""
    iv = secrets.token_bytes(CredentialsManager.IV_SIZE)
    cm = CredentialsManager.__new__(CredentialsManager)
    encrypted = cm._encrypt_aes(password.encode('utf-8'), key, iv)
    return b64encode(iv + encrypted).decode('ascii')


def decrypt_share_password(encrypted: str, key: bytes) -> str:
    """Decrypt share password from base64 string."""
    cm = CredentialsManager.__new__(CredentialsManager)
    data = b64decode(encrypted)
    iv = data[:CredentialsManager.IV_SIZE]
    ciphertext = data[CredentialsManager.IV_SIZE:]
    return cm._decrypt_aes(ciphertext, key, iv).decode('utf-8')
