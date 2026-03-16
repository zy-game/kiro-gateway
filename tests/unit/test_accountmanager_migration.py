"""
Tests to verify AccountManager migration to Database class.

This test suite verifies that AccountManager correctly uses the Database
abstraction layer instead of direct sqlite3 calls, while maintaining
backward compatibility with existing functionality.
"""

import json
import tempfile
from pathlib import Path

import pytest

from kiro.core.auth import AccountManager, Account


class TestAccountManagerMigration:
    """Test AccountManager uses Database class correctly."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup - force garbage collection to release database connections
        import gc
        gc.collect()
        # Attempt cleanup with error handling for Windows file locking
        try:
            Path(db_path).unlink(missing_ok=True)
        except PermissionError:
            pass  # Ignore if file is still locked on Windows

    @pytest.fixture
    def manager(self, temp_db):
        """Create an AccountManager instance."""
        mgr = AccountManager(temp_db)
        yield mgr
        # No explicit cleanup needed - Database uses context managers internally

    def test_manager_initializes_with_database(self, manager):
        """Test that AccountManager initializes with Database instance."""
        assert hasattr(manager, "_db")
        assert manager._db is not None
        # Verify _connect method no longer exists
        assert not hasattr(manager, "_connect") or callable(getattr(manager, "_connect", None)) is False

    def test_create_and_get_account(self, manager):
        """Test creating and retrieving an account."""
        config = {"accessToken": "test_token", "region": "us-east-1"}
        account = manager.create_account(
            type="kiro",
            priority=10,
            config=config,
            limit=1000
        )
        
        assert account.id is not None
        assert account.type == "kiro"
        assert account.priority == 10
        assert account.config == config
        assert account.limit == 1000
        assert account.usage == 0.0
        
        # Retrieve the account
        retrieved = manager.get_account(account.id)
        assert retrieved.id == account.id
        assert retrieved.type == account.type
        assert retrieved.config == account.config

    def test_list_accounts(self, manager):
        """Test listing accounts."""
        # Create multiple accounts
        manager.create_account(type="kiro", priority=10, config={}, limit=100)
        manager.create_account(type="kiro", priority=20, config={}, limit=200)
        manager.create_account(type="glm", priority=5, config={}, limit=50)
        
        # List all accounts
        accounts = manager.list_accounts()
        assert len(accounts) == 3
        # Should be sorted by priority DESC
        assert accounts[0].priority == 20
        assert accounts[1].priority == 10
        assert accounts[2].priority == 5

    def test_update_account(self, manager):
        """Test updating an account."""
        account = manager.create_account(type="kiro", priority=10, config={}, limit=100)
        
        # Update priority and usage
        updated = manager.update_account(account.id, priority=20, usage=50.0)
        assert updated.priority == 20
        assert updated.usage == 50.0
        assert updated.limit == 100  # Unchanged

    def test_delete_account(self, manager):
        """Test deleting an account."""
        account = manager.create_account(type="kiro", priority=10, config={}, limit=100)
        
        # Delete the account
        manager.delete_account(account.id)
        
        # Verify it's gone
        with pytest.raises(KeyError):
            manager.get_account(account.id)

    def test_increment_usage(self, manager):
        """Test atomically incrementing usage."""
        account = manager.create_account(type="kiro", priority=10, config={}, limit=100)
        
        # Increment usage
        manager.increment_usage(account.id, 10.5)
        
        # Verify
        updated = manager.get_account(account.id)
        assert updated.usage == 10.5
        
        # Increment again
        manager.increment_usage(account.id, 5.0)
        updated = manager.get_account(account.id)
        assert updated.usage == 15.5

    def test_generate_and_verify_api_key(self, manager):
        """Test API key generation and verification."""
        api_key = manager.generate_api_key(name="Test Key")
        
        assert api_key.id is not None
        assert api_key.key.startswith("sk-")
        assert api_key.name == "Test Key"
        
        # Verify the key
        assert manager.verify_api_key(api_key.key) is True
        assert manager.verify_api_key("invalid_key") is False

    def test_list_api_keys(self, manager):
        """Test listing API keys."""
        key1 = manager.generate_api_key(name="Key 1")
        key2 = manager.generate_api_key(name="Key 2")
        
        keys = manager.list_api_keys()
        assert len(keys) == 2
        # Should be ordered by id DESC
        assert keys[0].id == key2.id
        assert keys[1].id == key1.id

    def test_delete_api_key(self, manager):
        """Test deleting an API key."""
        api_key = manager.generate_api_key(name="Test Key")
        
        # Delete the key
        manager.delete_api_key(api_key.id)
        
        # Verify it's gone
        with pytest.raises(KeyError):
            manager.get_api_key(api_key.id)
        
        assert manager.verify_api_key(api_key.key) is False

    def test_create_and_verify_admin_user(self, manager):
        """Test admin user creation and verification."""
        admin = manager.create_admin_user(username="admin", password="password123")
        
        assert admin.id is not None
        assert admin.username == "admin"
        assert admin.password_hash is not None
        
        # Verify credentials
        verified = manager.verify_admin_user("admin", "password123")
        assert verified is not None
        assert verified.username == "admin"
        
        # Wrong password
        assert manager.verify_admin_user("admin", "wrong") is None

    def test_list_admin_users(self, manager):
        """Test listing admin users."""
        manager.create_admin_user(username="admin1", password="pass1")
        manager.create_admin_user(username="admin2", password="pass2")
        
        users = manager.list_admin_users()
        assert len(users) == 2
        assert users[0].username == "admin1"
        assert users[1].username == "admin2"

    def test_delete_admin_user(self, manager):
        """Test deleting an admin user."""
        admin = manager.create_admin_user(username="admin", password="password123")
        
        # Delete the user
        manager.delete_admin_user(admin.id)
        
        # Verify it's gone
        assert manager.verify_admin_user("admin", "password123") is None

    def test_log_request(self, manager):
        """Test logging a request."""
        # Create an account and API key first
        account = manager.create_account(type="kiro", priority=10, config={}, limit=100)
        api_key = manager.generate_api_key(name="Test Key")
        
        # Log a request
        log_id = manager.log_request(
            api_key_id=api_key.id,
            account_id=account.id,
            model="claude-sonnet-4",
            input_tokens=100,
            output_tokens=200,
            status="success",
            channel="openai",
            duration_ms=1500
        )
        
        assert log_id is not None

    def test_list_request_logs(self, manager):
        """Test listing request logs."""
        # Create an account and API key
        account = manager.create_account(type="kiro", priority=10, config={}, limit=100)
        api_key = manager.generate_api_key(name="Test Key")
        
        # Log some requests
        manager.log_request(
            api_key_id=api_key.id,
            account_id=account.id,
            model="claude-sonnet-4",
            input_tokens=100,
            output_tokens=200,
            status="success",
            channel="openai"
        )
        manager.log_request(
            api_key_id=api_key.id,
            account_id=account.id,
            model="claude-opus-4",
            input_tokens=150,
            output_tokens=250,
            status="success",
            channel="openai"
        )
        
        # List logs
        logs, total = manager.list_request_logs(limit=10, offset=0)
        assert len(logs) == 2
        assert total == 2
        assert logs[0]["model"] in ["claude-sonnet-4", "claude-opus-4"]

    def test_create_and_get_session(self, manager):
        """Test session creation and retrieval."""
        # Create admin user first
        manager.create_admin_user(username="admin", password="password123")
        
        # Create session
        token = "test_session_token_placeholder"
        manager.create_session(username="admin", session_token=token, expires_in_days=7)
        
        # Get session
        username = manager.get_session(token)
        assert username == "admin"

    def test_delete_session(self, manager):
        """Test session deletion."""
        manager.create_admin_user(username="admin", password="password123")
        token = "test_session_token_placeholder_2"
        manager.create_session(username="admin", session_token=token, expires_in_days=7)
        
        # Delete session
        manager.delete_session(token)
        
        # Verify it's gone
        assert manager.get_session(token) is None

    def test_create_and_list_models(self, manager):
        """Test model creation and listing."""
        model = manager.create_model(
            provider_type="kiro",
            model_id="claude-sonnet-4",
            display_name="Claude Sonnet 4",
            enabled=True,
            priority=10
        )
        
        assert model["id"] is not None
        assert model["provider_type"] == "kiro"
        assert model["model_id"] == "claude-sonnet-4"
        
        # List models
        models = manager.list_models(provider_type="kiro")
        assert len(models) == 1
        assert models[0]["model_id"] == "claude-sonnet-4"

    def test_update_model(self, manager):
        """Test updating a model."""
        model = manager.create_model(
            provider_type="kiro",
            model_id="claude-sonnet-4",
            display_name="Claude Sonnet 4",
            enabled=True,
            priority=10
        )
        
        # Update priority
        updated = manager.update_model(model["id"], priority=20, enabled=False)
        assert updated["priority"] == 20
        assert updated["enabled"] is False

    def test_delete_model(self, manager):
        """Test deleting a model."""
        model = manager.create_model(
            provider_type="kiro",
            model_id="claude-sonnet-4",
            display_name="Claude Sonnet 4",
            enabled=True,
            priority=10
        )
        
        # Delete the model
        manager.delete_model(model["id"])
        
        # Verify it's gone
        with pytest.raises(KeyError):
            manager.get_model(model["id"])

    def test_no_direct_sqlite3_usage(self, manager):
        """Verify that AccountManager doesn't use sqlite3 directly."""
        import inspect
        
        # Get the source code of AccountManager
        source = inspect.getsource(AccountManager)
        
        # Check that sqlite3.connect is not in the source
        assert "sqlite3.connect" not in source, "AccountManager should not use sqlite3.connect directly"
        
        # Check that it uses self._db instead
        assert "self._db" in source, "AccountManager should use self._db (Database instance)"
