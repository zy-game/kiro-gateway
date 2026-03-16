# -*- coding: utf-8 -*-
"""
Unit tests for Database account management methods.

Tests the account CRUD operations and usage tracking methods
added to the Database class.
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from kiro.core.database import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db') as f:
        db_path = f.name
    
    # Initialize database with accounts table
    with Database(db_path) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL DEFAULT 'kiro',
                priority INTEGER NOT NULL DEFAULT 0,
                config TEXT NOT NULL,
                limit_ INTEGER NOT NULL DEFAULT 0,
                usage REAL NOT NULL DEFAULT 0,
                email TEXT,
                expires_at TEXT,
                next_reset_at INTEGER
            )
        """)
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestAccountMethods:
    """Test account management methods."""
    
    def test_create_account_basic(self, temp_db):
        """Test creating a basic account."""
        with Database(temp_db) as db:
            config = json.dumps({"accessToken": "test_token"})
            account_id = db.create_account(
                account_type="kiro",
                config=config,
                priority=10,
                limit=1000
            )
            
            assert account_id > 0
            
            # Verify account was created
            account = db.get_account(account_id)
            assert account is not None
            assert account["type"] == "kiro"
            assert account["priority"] == 10
            assert account["limit_"] == 1000
            assert account["usage"] == 0.0
            assert account["config"] == config
    
    def test_create_account_with_optional_fields(self, temp_db):
        """Test creating an account with optional fields."""
        with Database(temp_db) as db:
            config = json.dumps({"accessToken": "test_token"})
            account_id = db.create_account(
                account_type="kiro",
                config=config,
                priority=5,
                limit=500,
                usage=10.5,
                email="test@example.com",
                expires_at="2026-12-31T23:59:59Z",
                next_reset_at=1735689599
            )
            
            account = db.get_account(account_id)
            assert account["email"] == "test@example.com"
            assert account["expires_at"] == "2026-12-31T23:59:59Z"
            assert account["next_reset_at"] == 1735689599
            assert account["usage"] == 10.5
    
    def test_get_account_not_found(self, temp_db):
        """Test getting a non-existent account returns None."""
        with Database(temp_db) as db:
            account = db.get_account(999)
            assert account is None
    
    def test_list_accounts_empty(self, temp_db):
        """Test listing accounts when database is empty."""
        with Database(temp_db) as db:
            accounts = db.list_accounts()
            assert accounts == []
    
    def test_list_accounts_sorted_by_priority(self, temp_db):
        """Test that accounts are sorted by priority DESC."""
        with Database(temp_db) as db:
            config = json.dumps({})
            
            # Create accounts with different priorities
            id1 = db.create_account("kiro", config, priority=5, limit=100)
            id2 = db.create_account("kiro", config, priority=20, limit=100)
            id3 = db.create_account("kiro", config, priority=10, limit=100)
            
            accounts = db.list_accounts()
            assert len(accounts) == 3
            assert accounts[0]["id"] == id2  # priority 20
            assert accounts[1]["id"] == id3  # priority 10
            assert accounts[2]["id"] == id1  # priority 5
    
    def test_list_accounts_filter_by_type(self, temp_db):
        """Test filtering accounts by type."""
        with Database(temp_db) as db:
            config = json.dumps({})
            
            db.create_account("kiro", config, priority=10)
            db.create_account("glm", config, priority=5)
            db.create_account("kiro", config, priority=15)
            
            kiro_accounts = db.list_accounts(account_type="kiro")
            assert len(kiro_accounts) == 2
            assert all(acc["type"] == "kiro" for acc in kiro_accounts)
            
            glm_accounts = db.list_accounts(account_type="glm")
            assert len(glm_accounts) == 1
            assert glm_accounts[0]["type"] == "glm"
    
    def test_list_accounts_enabled_only(self, temp_db):
        """Test filtering accounts by enabled status (usage < limit)."""
        with Database(temp_db) as db:
            config = json.dumps({})
            
            # Create accounts with different usage/limit ratios
            id1 = db.create_account("kiro", config, limit=100, usage=50.0)  # Available
            id2 = db.create_account("kiro", config, limit=100, usage=99.0)  # At limit
            id3 = db.create_account("kiro", config, limit=0, usage=1000.0)  # Unlimited
            id4 = db.create_account("kiro", config, limit=100, usage=100.0)  # Exceeded
            
            enabled = db.list_accounts(enabled_only=True)
            enabled_ids = [acc["id"] for acc in enabled]
            
            assert id1 in enabled_ids  # usage < limit
            assert id2 in enabled_ids  # usage < limit (99 < 100)
            assert id3 in enabled_ids  # unlimited (limit = 0)
            assert id4 not in enabled_ids  # usage >= limit
    
    def test_update_account_single_field(self, temp_db):
        """Test updating a single account field."""
        with Database(temp_db) as db:
            config = json.dumps({"key": "value"})
            account_id = db.create_account("kiro", config, priority=10)
            
            rows_updated = db.update_account(account_id, priority=20)
            assert rows_updated == 1
            
            account = db.get_account(account_id)
            assert account["priority"] == 20
    
    def test_update_account_multiple_fields(self, temp_db):
        """Test updating multiple account fields."""
        with Database(temp_db) as db:
            config = json.dumps({"key": "value"})
            account_id = db.create_account("kiro", config, priority=10, limit=100)
            
            new_config = json.dumps({"key": "new_value"})
            rows_updated = db.update_account(
                account_id,
                priority=15,
                config=new_config,
                usage=50.0,
                email="updated@example.com"
            )
            assert rows_updated == 1
            
            account = db.get_account(account_id)
            assert account["priority"] == 15
            assert account["config"] == new_config
            assert account["usage"] == 50.0
            assert account["email"] == "updated@example.com"
    
    def test_update_account_no_fields(self, temp_db):
        """Test updating account with no valid fields returns 0."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config)
            
            rows_updated = db.update_account(account_id)
            assert rows_updated == 0
    
    def test_update_account_nonexistent(self, temp_db):
        """Test updating a non-existent account."""
        with Database(temp_db) as db:
            rows_updated = db.update_account(999, priority=10)
            assert rows_updated == 0
    
    def test_delete_account(self, temp_db):
        """Test deleting an account."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config)
            
            rows_deleted = db.delete_account(account_id)
            assert rows_deleted == 1
            
            # Verify account is gone
            account = db.get_account(account_id)
            assert account is None
    
    def test_delete_account_nonexistent(self, temp_db):
        """Test deleting a non-existent account returns 0."""
        with Database(temp_db) as db:
            rows_deleted = db.delete_account(999)
            assert rows_deleted == 0
    
    def test_increment_usage(self, temp_db):
        """Test incrementing account usage."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config, usage=10.0)
            
            db.increment_usage(account_id, 5.5)
            
            account = db.get_account(account_id)
            assert account["usage"] == 15.5
    
    def test_increment_usage_multiple_times(self, temp_db):
        """Test incrementing usage multiple times."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config, usage=0.0)
            
            db.increment_usage(account_id, 10.0)
            db.increment_usage(account_id, 20.0)
            db.increment_usage(account_id, 5.5)
            
            account = db.get_account(account_id)
            assert account["usage"] == 35.5
    
    def test_increment_usage_negative(self, temp_db):
        """Test incrementing usage with negative value (decrement)."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config, usage=100.0)
            
            db.increment_usage(account_id, -25.0)
            
            account = db.get_account(account_id)
            assert account["usage"] == 75.0
    
    def test_refresh_usage(self, temp_db):
        """Test refreshing (resetting) account usage."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config, usage=100.0)
            
            rows_updated = db.refresh_usage(account_id, 0.0)
            assert rows_updated == 1
            
            account = db.get_account(account_id)
            assert account["usage"] == 0.0
    
    def test_refresh_usage_to_nonzero(self, temp_db):
        """Test refreshing usage to a non-zero value."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config, usage=100.0)
            
            db.refresh_usage(account_id, 50.0)
            
            account = db.get_account(account_id)
            assert account["usage"] == 50.0


class TestAccountConcurrency:
    """Test concurrent operations on accounts."""
    
    def test_increment_usage_atomic(self, temp_db):
        """Test that increment_usage is atomic (SQL-level atomicity)."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config, usage=0.0)
            
            # Simulate concurrent increments
            # In a real concurrent scenario, these would happen in parallel
            # Here we just verify the SQL operation is correct
            for i in range(10):
                db.increment_usage(account_id, 1.0)
            
            account = db.get_account(account_id)
            assert account["usage"] == 10.0


class TestAccountTransactions:
    """Test account operations within transactions."""
    
    def test_create_account_in_transaction(self, temp_db):
        """Test creating account within a transaction."""
        with Database(temp_db) as db:
            with db.transaction():
                config = json.dumps({})
                account_id = db.create_account("kiro", config, priority=10)
                
                # Verify within transaction
                account = db.get_account(account_id)
                assert account is not None
            
            # Verify after transaction commit
            account = db.get_account(account_id)
            assert account is not None
            assert account["priority"] == 10
    
    def test_transaction_rollback_on_error(self, temp_db):
        """Test that account creation is rolled back on error."""
        with Database(temp_db) as db:
            config = json.dumps({})
            
            try:
                with db.transaction():
                    account_id = db.create_account("kiro", config, priority=10)
                    # Force an error
                    raise ValueError("Test error")
            except ValueError:
                pass
            
            # Verify account was not created (rolled back)
            accounts = db.list_accounts()
            assert len(accounts) == 0
    
    def test_multiple_operations_in_transaction(self, temp_db):
        """Test multiple account operations in a single transaction."""
        with Database(temp_db) as db:
            config = json.dumps({})
            
            with db.transaction():
                id1 = db.create_account("kiro", config, priority=10)
                id2 = db.create_account("glm", config, priority=5)
                db.update_account(id1, usage=50.0)
                db.increment_usage(id2, 25.0)
            
            # Verify all operations committed
            acc1 = db.get_account(id1)
            acc2 = db.get_account(id2)
            assert acc1["usage"] == 50.0
            assert acc2["usage"] == 25.0
