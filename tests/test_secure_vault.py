"""
Unit Tests for Secure Vault Module

Tests encryption, decryption, key storage, migration, and thread safety.
"""

import os
import pytest
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

from modules.secure_vault import SecureVault, get_secure_vault, init_vault_with_env_migration
import modules.secure_vault as secure_vault_module


class TestSecureVault:
    """Test suite for SecureVault class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Generate test master key
        self.test_key = SecureVault.generate_master_key()
        # Create temporary vault file
        self.temp_dir = tempfile.mkdtemp()
        self.vault_path = Path(self.temp_dir) / "test_vault.enc"
        
    def teardown_method(self):
        """Clean up test files"""
        if self.vault_path.exists():
            self.vault_path.unlink()
        Path(self.temp_dir).rmdir()
    
    def test_generate_master_key(self):
        """Test master key generation"""
        key1 = SecureVault.generate_master_key()
        key2 = SecureVault.generate_master_key()
        
        # Keys should be different
        assert key1 != key2
        
        # Keys should be valid Fernet format (44 bytes base64)
        assert len(key1) == 44
        assert isinstance(key1, str)
    
    def test_vault_initialization(self):
        """Test vault initialization"""
        vault = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        assert vault is not None
        assert vault._vault_path == self.vault_path
        assert len(vault._cache) == 0
    
    def test_vault_requires_master_key(self):
        """Test that vault fails without master key"""
        with pytest.raises(ValueError, match="Master key not found"):
            SecureVault(vault_path=self.vault_path, master_key=None)
    
    def test_set_and_get(self):
        """Test basic set and get operations"""
        vault = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        # Set a value
        vault.set("TEST_KEY", "test_value")
        
        # Get the value
        retrieved = vault.get("TEST_KEY")
        assert retrieved == "test_value"
    
    def test_get_nonexistent_key(self):
        """Test getting a non-existent key"""
        vault = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        # Should return None
        assert vault.get("NONEXISTENT") is None
        
        # Should return default
        assert vault.get("NONEXISTENT", "default") == "default"
    
    def test_delete_key(self):
        """Test deleting a key"""
        vault = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        vault.set("DELETE_ME", "value")
        assert vault.get("DELETE_ME") == "value"
        
        deleted = vault.delete("DELETE_ME")
        assert deleted is True
        assert vault.get("DELETE_ME") is None
    
    def test_delete_nonexistent_key(self):
        """Test deleting non-existent key returns False"""
        vault = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        deleted = vault.delete("NONEXISTENT")
        assert deleted is False
    
    def test_list_keys(self):
        """Test listing all keys"""
        vault = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        vault.set("KEY1", "value1")
        vault.set("KEY2", "value2")
        vault.set("KEY3", "value3")
        
        keys = vault.list_keys()
        assert len(keys) == 3
        assert "KEY1" in keys
        assert "KEY2" in keys
        assert "KEY3" in keys
    
    def test_persistence(self):
        """Test that values persist across vault instances"""
        # Create vault and store value
        vault1 = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        vault1.set("PERSIST_KEY", "persist_value")
        
        # Create new vault instance with same key and path
        vault2 = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        # Should load the persisted value
        assert vault2.get("PERSIST_KEY") == "persist_value"
    
    def test_wrong_master_key_fails(self):
        """Test that wrong master key cannot decrypt vault"""
        # Create vault with one key
        vault1 = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        vault1.set("SECRET", "value")
        
        # Try to load with different key
        different_key = SecureVault.generate_master_key()
        
        with pytest.raises(ValueError, match="Invalid master key"):
            SecureVault(vault_path=self.vault_path, master_key=different_key)
    
    def test_migrate_from_env(self):
        """Test migrating keys from environment variables"""
        vault = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        # Mock environment variables
        with patch.dict(os.environ, {
            "TEST_API_KEY_1": "key1_value",
            "TEST_API_KEY_2": "key2_value",
            "TEST_API_KEY_3": "key3_value",
        }):
            migrated = vault.migrate_from_env([
                "TEST_API_KEY_1",
                "TEST_API_KEY_2",
                "TEST_API_KEY_3",
                "NONEXISTENT_KEY"
            ])
            
            # Should migrate 3 keys (4th doesn't exist)
            assert migrated == 3
            
            # Verify keys were stored
            assert vault.get("TEST_API_KEY_1") == "key1_value"
            assert vault.get("TEST_API_KEY_2") == "key2_value"
            assert vault.get("TEST_API_KEY_3") == "key3_value"
            assert vault.get("NONEXISTENT_KEY") is None
    
    def test_clear_all(self):
        """Test clearing all keys"""
        vault = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        vault.set("KEY1", "value1")
        vault.set("KEY2", "value2")
        
        assert len(vault.list_keys()) == 2
        
        vault.clear_all()
        
        assert len(vault.list_keys()) == 0
    
    def test_thread_safety(self):
        """Test concurrent access to vault"""
        vault = SecureVault(vault_path=self.vault_path, master_key=self.test_key)
        
        errors = []
        
        def set_key(key_name, value):
            try:
                vault.set(key_name, value)
            except Exception as e:
                errors.append(e)
        
        def get_key(key_name):
            try:
                vault.get(key_name)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads writing and reading
        threads = []
        for i in range(10):
            t1 = threading.Thread(target=set_key, args=(f"KEY_{i}", f"value_{i}"))
            t2 = threading.Thread(target=get_key, args=(f"KEY_{i}",))
            threads.extend([t1, t2])
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Should have no errors
        assert len(errors) == 0
        
        # All keys should be present
        assert len(vault.list_keys()) == 10


class TestSecureVaultSingleton:
    """Test singleton behavior of get_secure_vault()"""

    def setup_method(self):
        with secure_vault_module._vault_lock:
            secure_vault_module._vault_instance = None

    def teardown_method(self):
        with secure_vault_module._vault_lock:
            secure_vault_module._vault_instance = None
    
    def test_singleton_returns_same_instance(self):
        """Test that get_secure_vault() returns same instance"""
        test_key = SecureVault.generate_master_key()

        with tempfile.TemporaryDirectory() as temp_dir:
            vault_path = Path(temp_dir) / "singleton_vault.enc"
            with patch.dict(
                os.environ,
                {
                    "LADA_MASTER_KEY": test_key,
                    "LADA_SECURE_VAULT_PATH": str(vault_path),
                },
            ):
                vault1 = get_secure_vault()
                vault2 = get_secure_vault()

                assert vault1 is vault2
    
    def test_singleton_thread_safety(self):
        """Test singleton creation is thread-safe"""
        test_key = SecureVault.generate_master_key()
        instances = []
        
        def get_instance():
            vault = get_secure_vault()
            instances.append(id(vault))
        
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_path = Path(temp_dir) / "singleton_thread_vault.enc"
            with patch.dict(
                os.environ,
                {
                    "LADA_MASTER_KEY": test_key,
                    "LADA_SECURE_VAULT_PATH": str(vault_path),
                },
            ):
                threads = [threading.Thread(target=get_instance) for _ in range(10)]
                
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                
                # All instances should have same ID
                assert len(set(instances)) == 1


class TestVaultMigration:
    """Test init_vault_with_env_migration()"""

    def setup_method(self):
        with secure_vault_module._vault_lock:
            secure_vault_module._vault_instance = None

    def teardown_method(self):
        with secure_vault_module._vault_lock:
            secure_vault_module._vault_instance = None
    
    def test_migration_with_default_keys(self):
        """Test migration with default key list"""
        test_key = SecureVault.generate_master_key()

        with tempfile.TemporaryDirectory() as temp_dir:
            vault_path = Path(temp_dir) / "migration_default_vault.enc"
            with patch.dict(os.environ, {
                "LADA_MASTER_KEY": test_key,
                "LADA_SECURE_VAULT_PATH": str(vault_path),
                "OPENAI_API_KEY": "sk-test123",
                "ANTHROPIC_API_KEY": "ant-test456",
                "GEMINI_API_KEY": "gem-test789"
            }):
                vault = init_vault_with_env_migration()
                
                assert vault.get("OPENAI_API_KEY") == "sk-test123"
                assert vault.get("ANTHROPIC_API_KEY") == "ant-test456"
                assert vault.get("GEMINI_API_KEY") == "gem-test789"
    
    def test_migration_with_custom_keys(self):
        """Test migration with custom key list"""
        test_key = SecureVault.generate_master_key()

        with tempfile.TemporaryDirectory() as temp_dir:
            vault_path = Path(temp_dir) / "migration_custom_vault.enc"
            with patch.dict(os.environ, {
                "LADA_MASTER_KEY": test_key,
                "LADA_SECURE_VAULT_PATH": str(vault_path),
                "CUSTOM_KEY_1": "value1",
                "CUSTOM_KEY_2": "value2"
            }):
                vault = init_vault_with_env_migration(key_names=["CUSTOM_KEY_1", "CUSTOM_KEY_2"])
                
                assert vault.get("CUSTOM_KEY_1") == "value1"
                assert vault.get("CUSTOM_KEY_2") == "value2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
