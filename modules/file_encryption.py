"""
LADA v10.0 - File Encryption Module
Secure file encryption and decryption using Fernet (AES-128-CBC)

Features:
- Encrypt/decrypt individual files
- Encrypt/decrypt entire folders
- Password-based key derivation (PBKDF2)
- Secure key storage and management
- Encrypted file verification
- Progress tracking for large files
- Integration with memory for key hints
"""

import os
import base64
import hashlib
import logging
import shutil
import secrets
from typing import Optional, List, Tuple, Callable
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import cryptography
try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.backends import default_backend
    CRYPTO_OK = True
except ImportError:
    Fernet = None
    InvalidToken = Exception
    CRYPTO_OK = False
    logger.warning("cryptography not installed. Install with: pip install cryptography")


@dataclass
class EncryptionResult:
    """Result from encryption/decryption operation"""
    success: bool
    input_path: str
    output_path: Optional[str]
    message: str
    original_size: int = 0
    encrypted_size: int = 0
    timestamp: str = ""


class FileEncryption:
    """
    Secure file encryption using Fernet (AES-128-CBC with HMAC).
    Supports password-based encryption and key file management.
    """
    
    # File extension for encrypted files
    ENCRYPTED_EXT = ".lada_encrypted"
    
    # Marker bytes to identify encrypted files
    MAGIC_HEADER = b"LADA_ENC_V1\x00"
    
    # Salt length for PBKDF2
    SALT_LENGTH = 16
    
    # Iterations for PBKDF2 (higher = more secure but slower)
    PBKDF2_ITERATIONS = 480000  # OWASP recommendation
    
    def __init__(self, key_directory: Optional[str] = None):
        """
        Initialize file encryption system.
        
        Args:
            key_directory: Directory to store key files (default: ~/.lada/keys/)
        """
        if not CRYPTO_OK:
            logger.error("cryptography library not available!")
            
        self.key_dir = Path(key_directory) if key_directory else Path.home() / ".lada" / "keys"
        self.key_dir.mkdir(parents=True, exist_ok=True)
        
        # Current encryption key (set via password or key file)
        self._current_key: Optional[bytes] = None
        self._current_fernet = None  # Fernet instance
    
    def generate_key(self) -> bytes:
        """Generate a new random encryption key"""
        return Fernet.generate_key()
    
    def derive_key_from_password(
        self,
        password: str,
        salt: Optional[bytes] = None
    ) -> Tuple[bytes, bytes]:
        """
        Derive encryption key from password using PBKDF2.
        
        Args:
            password: User password
            salt: Optional salt (generated if not provided)
            
        Returns:
            Tuple of (derived_key, salt)
        """
        if not CRYPTO_OK:
            raise RuntimeError("cryptography library not installed")
        
        if salt is None:
            salt = secrets.token_bytes(self.SALT_LENGTH)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt
    
    def set_password(self, password: str, salt: Optional[bytes] = None) -> bytes:
        """
        Set encryption password for current session.
        
        Args:
            password: Encryption password
            salt: Optional salt (generated if not provided)
            
        Returns:
            Salt used for key derivation
        """
        if salt is None:
            salt = secrets.token_bytes(self.SALT_LENGTH)
        
        key, salt = self.derive_key_from_password(password, salt)
        self._current_key = key
        self._current_fernet = Fernet(key)
        
        return salt
    
    def set_key(self, key: bytes):
        """Set encryption key directly"""
        self._current_key = key
        self._current_fernet = Fernet(key)
    
    def save_key_file(self, name: str, key: bytes, password: Optional[str] = None):
        """
        Save encryption key to file.
        
        Args:
            name: Key identifier
            key: The encryption key
            password: Optional password to protect the key file
        """
        key_path = self.key_dir / f"{name}.key"
        
        if password:
            # Encrypt the key with password
            protect_key, salt = self.derive_key_from_password(password)
            fernet = Fernet(protect_key)
            protected = salt + fernet.encrypt(key)
            key_path.write_bytes(protected)
        else:
            key_path.write_bytes(key)
        
        # Set restrictive permissions on Unix
        try:
            os.chmod(key_path, 0o600)
        except Exception as e:
            pass
        
        logger.info(f"Key saved to {key_path}")
    
    def load_key_file(self, name: str, password: Optional[str] = None) -> bytes:
        """
        Load encryption key from file.
        
        Args:
            name: Key identifier
            password: Password if key file is protected
            
        Returns:
            The encryption key
        """
        key_path = self.key_dir / f"{name}.key"
        
        if not key_path.exists():
            raise FileNotFoundError(f"Key file not found: {key_path}")
        
        data = key_path.read_bytes()
        
        if password:
            # First 16 bytes are salt
            salt = data[:self.SALT_LENGTH]
            encrypted_key = data[self.SALT_LENGTH:]
            
            protect_key, _ = self.derive_key_from_password(password, salt)
            fernet = Fernet(protect_key)
            
            try:
                key = fernet.decrypt(encrypted_key)
            except InvalidToken:
                raise ValueError("Invalid password for key file")
        else:
            key = data
        
        return key
    
    def encrypt_file(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        password: Optional[str] = None,
        delete_original: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> EncryptionResult:
        """
        Encrypt a file.
        
        Args:
            input_path: Path to file to encrypt
            output_path: Path for encrypted file (default: input + .lada_encrypted)
            password: Optional password (uses current key if not provided)
            delete_original: Whether to securely delete original after encryption
            progress_callback: Optional callback(bytes_processed, total_bytes)
            
        Returns:
            EncryptionResult with operation details
        """
        if not CRYPTO_OK:
            return EncryptionResult(
                success=False,
                input_path=input_path,
                output_path=None,
                message="cryptography library not installed"
            )
        
        input_file = Path(input_path)
        
        if not input_file.exists():
            return EncryptionResult(
                success=False,
                input_path=input_path,
                output_path=None,
                message=f"File not found: {input_path}"
            )
        
        if input_file.suffix == self.ENCRYPTED_EXT:
            return EncryptionResult(
                success=False,
                input_path=input_path,
                output_path=None,
                message="File is already encrypted"
            )
        
        # Set up encryption
        if password:
            salt = self.set_password(password)
        elif self._current_fernet is None:
            return EncryptionResult(
                success=False,
                input_path=input_path,
                output_path=None,
                message="No password or key set"
            )
        else:
            salt = secrets.token_bytes(self.SALT_LENGTH)
        
        # Determine output path
        if output_path is None:
            output_file = input_file.with_suffix(input_file.suffix + self.ENCRYPTED_EXT)
        else:
            output_file = Path(output_path)
        
        try:
            # Read original file
            original_size = input_file.stat().st_size
            data = input_file.read_bytes()
            
            if progress_callback:
                progress_callback(original_size // 2, original_size)
            
            # Encrypt
            encrypted_data = self._current_fernet.encrypt(data)
            
            # Write encrypted file with header
            with open(output_file, 'wb') as f:
                f.write(self.MAGIC_HEADER)  # Magic header
                f.write(salt)                # Salt for key derivation
                f.write(input_file.suffix.encode().ljust(32, b'\x00'))  # Original extension
                f.write(encrypted_data)      # Encrypted content
            
            if progress_callback:
                progress_callback(original_size, original_size)
            
            encrypted_size = output_file.stat().st_size
            
            # Securely delete original if requested
            if delete_original:
                self._secure_delete(input_file)
            
            return EncryptionResult(
                success=True,
                input_path=str(input_path),
                output_path=str(output_file),
                message=f"Successfully encrypted to {output_file.name}",
                original_size=original_size,
                encrypted_size=encrypted_size,
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return EncryptionResult(
                success=False,
                input_path=input_path,
                output_path=None,
                message=f"Encryption failed: {str(e)}"
            )
    
    def decrypt_file(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        password: Optional[str] = None,
        delete_encrypted: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> EncryptionResult:
        """
        Decrypt a file.
        
        Args:
            input_path: Path to encrypted file
            output_path: Path for decrypted file (default: restore original name)
            password: Password used for encryption
            delete_encrypted: Whether to delete encrypted file after decryption
            progress_callback: Optional callback(bytes_processed, total_bytes)
            
        Returns:
            EncryptionResult with operation details
        """
        if not CRYPTO_OK:
            return EncryptionResult(
                success=False,
                input_path=input_path,
                output_path=None,
                message="cryptography library not installed"
            )
        
        input_file = Path(input_path)
        
        if not input_file.exists():
            return EncryptionResult(
                success=False,
                input_path=input_path,
                output_path=None,
                message=f"File not found: {input_path}"
            )
        
        try:
            # Read encrypted file
            encrypted_size = input_file.stat().st_size
            
            with open(input_file, 'rb') as f:
                # Check magic header
                header = f.read(len(self.MAGIC_HEADER))
                if header != self.MAGIC_HEADER:
                    return EncryptionResult(
                        success=False,
                        input_path=input_path,
                        output_path=None,
                        message="Not a valid LADA encrypted file"
                    )
                
                # Read salt and original extension
                salt = f.read(self.SALT_LENGTH)
                orig_ext = f.read(32).rstrip(b'\x00').decode()
                encrypted_data = f.read()
            
            if progress_callback:
                progress_callback(encrypted_size // 2, encrypted_size)
            
            # Set up decryption with stored salt
            if password:
                self.set_password(password, salt)
            elif self._current_fernet is None:
                return EncryptionResult(
                    success=False,
                    input_path=input_path,
                    output_path=None,
                    message="No password or key set"
                )
            
            # Decrypt
            try:
                decrypted_data = self._current_fernet.decrypt(encrypted_data)
            except InvalidToken:
                return EncryptionResult(
                    success=False,
                    input_path=input_path,
                    output_path=None,
                    message="Decryption failed: Invalid password or corrupted file"
                )
            
            # Determine output path
            if output_path is None:
                # Remove .lada_encrypted and restore original extension
                base_name = input_file.stem
                if base_name.endswith(orig_ext):
                    output_file = input_file.parent / base_name
                else:
                    output_file = input_file.parent / (base_name + orig_ext)
            else:
                output_file = Path(output_path)
            
            # Write decrypted file
            output_file.write_bytes(decrypted_data)
            
            if progress_callback:
                progress_callback(encrypted_size, encrypted_size)
            
            original_size = output_file.stat().st_size
            
            # Delete encrypted file if requested
            if delete_encrypted:
                input_file.unlink()
            
            return EncryptionResult(
                success=True,
                input_path=str(input_path),
                output_path=str(output_file),
                message=f"Successfully decrypted to {output_file.name}",
                original_size=original_size,
                encrypted_size=encrypted_size,
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return EncryptionResult(
                success=False,
                input_path=input_path,
                output_path=None,
                message=f"Decryption failed: {str(e)}"
            )
    
    def encrypt_folder(
        self,
        folder_path: str,
        password: str,
        recursive: bool = True,
        delete_originals: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[EncryptionResult]:
        """
        Encrypt all files in a folder.
        
        Args:
            folder_path: Path to folder
            password: Encryption password
            recursive: Whether to process subfolders
            delete_originals: Whether to delete original files
            progress_callback: Optional callback(filename, file_num, total_files)
            
        Returns:
            List of EncryptionResult for each file
        """
        folder = Path(folder_path)
        
        if not folder.is_dir():
            return [EncryptionResult(
                success=False,
                input_path=folder_path,
                output_path=None,
                message="Not a valid directory"
            )]
        
        # Get all files
        if recursive:
            files = [f for f in folder.rglob('*') if f.is_file() and f.suffix != self.ENCRYPTED_EXT]
        else:
            files = [f for f in folder.iterdir() if f.is_file() and f.suffix != self.ENCRYPTED_EXT]
        
        # Set password once for all files
        self.set_password(password)
        
        results = []
        total = len(files)
        
        for i, file_path in enumerate(files):
            if progress_callback:
                progress_callback(file_path.name, i + 1, total)
            
            result = self.encrypt_file(
                str(file_path),
                password=None,  # Already set
                delete_original=delete_originals
            )
            results.append(result)
        
        return results
    
    def decrypt_folder(
        self,
        folder_path: str,
        password: str,
        recursive: bool = True,
        delete_encrypted: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[EncryptionResult]:
        """
        Decrypt all encrypted files in a folder.
        
        Args:
            folder_path: Path to folder
            password: Decryption password
            recursive: Whether to process subfolders
            delete_encrypted: Whether to delete encrypted files after
            progress_callback: Optional callback(filename, file_num, total_files)
            
        Returns:
            List of EncryptionResult for each file
        """
        folder = Path(folder_path)
        
        if not folder.is_dir():
            return [EncryptionResult(
                success=False,
                input_path=folder_path,
                output_path=None,
                message="Not a valid directory"
            )]
        
        # Get all encrypted files
        pattern = f'*{self.ENCRYPTED_EXT}'
        if recursive:
            files = list(folder.rglob(pattern))
        else:
            files = list(folder.glob(pattern))
        
        results = []
        total = len(files)
        
        for i, file_path in enumerate(files):
            if progress_callback:
                progress_callback(file_path.name, i + 1, total)
            
            result = self.decrypt_file(
                str(file_path),
                password=password,
                delete_encrypted=delete_encrypted
            )
            results.append(result)
        
        return results
    
    def is_encrypted(self, file_path: str) -> bool:
        """Check if a file is LADA encrypted"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(len(self.MAGIC_HEADER))
                return header == self.MAGIC_HEADER
        except Exception as e:
            return False
    
    def _secure_delete(self, file_path: Path, passes: int = 3):
        """
        Securely delete a file by overwriting with random data.
        
        Args:
            file_path: Path to file
            passes: Number of overwrite passes
        """
        try:
            size = file_path.stat().st_size
            
            with open(file_path, 'r+b') as f:
                for _ in range(passes):
                    f.seek(0)
                    f.write(secrets.token_bytes(size))
                    f.flush()
                    os.fsync(f.fileno())
            
            file_path.unlink()
            logger.info(f"Securely deleted: {file_path}")
            
        except Exception as e:
            logger.warning(f"Secure delete failed, using normal delete: {e}")
            file_path.unlink()
    
    def get_file_info(self, file_path: str) -> dict:
        """Get information about an encrypted file"""
        if not self.is_encrypted(file_path):
            return {'encrypted': False}
        
        try:
            with open(file_path, 'rb') as f:
                f.read(len(self.MAGIC_HEADER))  # Skip header
                f.read(self.SALT_LENGTH)  # Skip salt
                orig_ext = f.read(32).rstrip(b'\x00').decode()
            
            file_stat = Path(file_path).stat()
            
            return {
                'encrypted': True,
                'original_extension': orig_ext,
                'encrypted_size': file_stat.st_size,
                'modified_time': datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            }
        except Exception as e:
            return {'encrypted': True, 'error': str(e)}


# ============================================================
# QUICK ENCRYPT/DECRYPT FUNCTIONS
# ============================================================

def quick_encrypt(file_path: str, password: str) -> EncryptionResult:
    """Quick function to encrypt a file"""
    enc = FileEncryption()
    return enc.encrypt_file(file_path, password=password)

def quick_decrypt(file_path: str, password: str) -> EncryptionResult:
    """Quick function to decrypt a file"""
    enc = FileEncryption()
    return enc.decrypt_file(file_path, password=password)


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    import tempfile
    
    logging.basicConfig(level=logging.INFO)
    
    print("🔐 File Encryption Test")
    print("=" * 50)
    
    if not CRYPTO_OK:
        print("❌ cryptography library not installed!")
        print("   Install with: pip install cryptography")
        exit(1)
    
    enc = FileEncryption()
    
    # Create a test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("This is a secret message for LADA encryption test!\n")
        f.write("It contains sensitive information.\n")
        test_file = f.name
    
    print(f"\n📄 Created test file: {test_file}")
    
    # Encrypt
    password = "my_secure_password_123"
    print(f"\n🔒 Encrypting with password...")
    result = enc.encrypt_file(test_file, password=password)
    print(f"   Success: {result.success}")
    print(f"   Output: {result.output_path}")
    print(f"   Message: {result.message}")
    
    if result.success:
        # Check if encrypted
        encrypted_path = result.output_path
        print(f"\n🔍 Checking encrypted file...")
        print(f"   Is encrypted: {enc.is_encrypted(encrypted_path)}")
        print(f"   File info: {enc.get_file_info(encrypted_path)}")
        
        # Decrypt
        print(f"\n🔓 Decrypting...")
        dec_result = enc.decrypt_file(encrypted_path, password=password)
        print(f"   Success: {dec_result.success}")
        print(f"   Output: {dec_result.output_path}")
        print(f"   Message: {dec_result.message}")
        
        if dec_result.success:
            # Read decrypted content
            with open(dec_result.output_path) as f:
                content = f.read()
            print(f"\n📖 Decrypted content:\n{content}")
            
            # Cleanup
            os.unlink(dec_result.output_path)
            os.unlink(encrypted_path)
    
    # Cleanup original if still exists
    if os.path.exists(test_file):
        os.unlink(test_file)
    
    print("\n✅ File Encryption test complete!")
