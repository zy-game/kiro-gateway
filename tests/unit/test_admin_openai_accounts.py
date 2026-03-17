# -*- coding: utf-8 -*-
"""
Unit tests for OpenAI account management via admin API.

Tests account validation, creation, update, and deletion for OpenAI accounts.
"""

import gc
import tempfile
import pytest
from pathlib import Path
from kiro.core.auth import AccountManager


class TestOpenAIAccountValidation:
    """Test OpenAI account config validation."""

    def test_create_openai_account_with_api_key(self):
        """Test creating OpenAI account with valid api_key."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
            
            account = manager.create_account(
                type="openai",
                priority=0,
                config={"api_key": "test_api_key_placeholder"},
                limit=0
            )
            
            assert account.id is not None
            assert account.type == "openai"
            assert account.config["api_key"] == "test_api_key_placeholder"
            assert account.priority == 0
            assert account.limit == 0
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_create_openai_account_with_api_key_and_base_url(self):
        """Test creating OpenAI account with api_key and custom base_url."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
            
            account = manager.create_account(
                type="openai",
                priority=1,
                config={
                    "api_key": "test_relay_api_key",
                    "base_url": "https://api.relay-service.com/v1"
                },
                limit=100
            )
            
            assert account.id is not None
            assert account.type == "openai"
            assert account.config["api_key"] == "test_relay_api_key"
            assert account.config["base_url"] == "https://api.relay-service.com/v1"
            assert account.priority == 1
            assert account.limit == 100
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_create_openai_account_without_api_key(self):
        """Test creating OpenAI account without api_key should fail."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            with pytest.raises(ValueError, match="api_key.*required"):
                manager.create_account(
                    type="openai",
                    priority=0,
                    config={},  # Missing api_key
                    limit=0
                )
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_create_openai_account_with_empty_api_key(self):
        """Test creating OpenAI account with empty api_key should fail."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            with pytest.raises(ValueError, match="api_key.*required"):
                manager.create_account(
                    type="openai",
                    priority=0,
                    config={"api_key": ""},  # Empty api_key
                    limit=0
                )
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_create_openai_account_with_none_api_key(self):
        """Test creating OpenAI account with None api_key should fail."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            with pytest.raises(ValueError, match="api_key.*required"):
                manager.create_account(
                    type="openai",
                    priority=0,
                    config={"api_key": None},  # None api_key
                    limit=0
                )
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_update_openai_account_config(self):
        """Test updating OpenAI account config with valid api_key."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            # Create account
            account = manager.create_account(
                type="openai",
                priority=0,
                config={"api_key": "sk-old"},
                limit=0
            )
            
            # Update config
            updated = manager.update_account(
                account.id,
                config={"api_key": "sk-new", "base_url": "https://new-url.com/v1"}
            )
            
            assert updated.config["api_key"] == "sk-new"
            assert updated.config["base_url"] == "https://new-url.com/v1"
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_update_openai_account_remove_api_key(self):
        """Test updating OpenAI account to remove api_key should fail."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            # Create account
            account = manager.create_account(
                type="openai",
                priority=0,
                config={"api_key": "sk-test"},
                limit=0
            )
            
            # Try to update config without api_key
            with pytest.raises(ValueError, match="api_key.*required"):
                manager.update_account(
                    account.id,
                    config={}  # Missing api_key
                )
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_update_openai_account_priority(self):
        """Test updating OpenAI account priority without changing config."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            # Create account
            account = manager.create_account(
                type="openai",
                priority=0,
                config={"api_key": "sk-test"},
                limit=0
            )
            
            # Update priority only
            updated = manager.update_account(account.id, priority=5)
            
            assert updated.priority == 5
            assert updated.config["api_key"] == "sk-test"
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_create_non_openai_account_without_validation(self):
        """Test creating non-OpenAI account doesn't trigger OpenAI validation."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            # Create kiro account without api_key (should work)
            account = manager.create_account(
                type="kiro",
                priority=0,
                config={"accessToken": "token123"},
                limit=0
            )
            
            assert account.type == "kiro"
            assert "api_key" not in account.config
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)


class TestOpenAIAccountCRUD:
    """Test CRUD operations for OpenAI accounts."""

    def test_list_openai_accounts(self):
        """Test listing accounts includes OpenAI accounts."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            # Create multiple accounts
            manager.create_account(type="kiro", config={"accessToken": "t1"})
            manager.create_account(type="openai", config={"api_key": "sk-1"})
            manager.create_account(type="glm", config={"api_key": "glm-1"})
            manager.create_account(type="openai", config={"api_key": "sk-2"})
            
            accounts = manager.list_accounts()
            
            openai_accounts = [a for a in accounts if a.type == "openai"]
            assert len(openai_accounts) == 2
            assert all(a.config.get("api_key") for a in openai_accounts)
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_get_openai_account(self):
        """Test getting a specific OpenAI account by ID."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            created = manager.create_account(
                type="openai",
                config={"api_key": "sk-test", "base_url": "https://custom.com/v1"}
            )
            
            retrieved = manager.get_account(created.id)
            
            assert retrieved.id == created.id
            assert retrieved.type == "openai"
            assert retrieved.config["api_key"] == "sk-test"
            assert retrieved.config["base_url"] == "https://custom.com/v1"
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_delete_openai_account(self):
        """Test deleting an OpenAI account."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            account = manager.create_account(
                type="openai",
                config={"api_key": "sk-test"}
            )
            
            # Delete account
            manager.delete_account(account.id)
            
            # Verify it's deleted
            with pytest.raises(KeyError):
                manager.get_account(account.id)
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)

    def test_multiple_openai_accounts_with_different_priorities(self):
        """Test creating multiple OpenAI accounts with different priorities."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            manager = AccountManager(db_path)
        
            acc1 = manager.create_account(
                type="openai",
                priority=10,
                config={"api_key": "sk-high"}
            )
            acc2 = manager.create_account(
                type="openai",
                priority=5,
                config={"api_key": "sk-medium"}
            )
            acc3 = manager.create_account(
                type="openai",
                priority=1,
                config={"api_key": "sk-low"}
            )
            
            accounts = manager.list_accounts()
            openai_accounts = [a for a in accounts if a.type == "openai"]
            
            # Should be sorted by priority DESC
            assert len(openai_accounts) == 3
            assert openai_accounts[0].priority >= openai_accounts[1].priority
            assert openai_accounts[1].priority >= openai_accounts[2].priority
        finally:
            del manager  # Release database connection
            gc.collect()  # Force garbage collection to release file handles
            Path(db_path).unlink(missing_ok=True)
