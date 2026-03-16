# -*- coding: utf-8 -*-
"""
Unit tests for Database API key management methods.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from kiro.core.database import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db') as f:
        db_path = f.name
    
    # Initialize database with api_keys table
    with Database(db_path) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                key        TEXT    NOT NULL UNIQUE,
                name       TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            )
        """, commit=True)
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestApiKeyMethods:
    """Test suite for API key management methods."""
    
    def test_create_api_key(self, temp_db):
        """Test creating a new API key."""
        with Database(temp_db) as db:
            key_id = db.create_api_key(
                name="Test Key",
                key="test-key-placeholder",
                created_at="2026-03-16T10:00:00Z"
            )
            
            assert key_id > 0
            
            # Verify the key was created
            api_key = db.get_api_key(key_id)
            assert api_key is not None
            assert api_key["name"] == "Test Key"
            assert api_key["key"] == "test-key-placeholder"
            assert api_key["created_at"] == "2026-03-16T10:00:00Z"
    
    def test_create_api_key_auto_timestamp(self, temp_db):
        """Test creating an API key with automatic timestamp."""
        with Database(temp_db) as db:
            before = datetime.now(timezone.utc).isoformat()
            key_id = db.create_api_key(
                name="Auto Timestamp Key",
                key="auto-timestamp-placeholder"
            )
            after = datetime.now(timezone.utc).isoformat()
            
            api_key = db.get_api_key(key_id)
            assert api_key is not None
            assert before <= api_key["created_at"] <= after
    
    def test_get_api_key(self, temp_db):
        """Test fetching an API key by ID."""
        with Database(temp_db) as db:
            # Create a key
            key_id = db.create_api_key(
                name="Get Test Key",
                key="get-test-placeholder",
                created_at="2026-03-16T11:00:00Z"
            )
            
            # Fetch it
            api_key = db.get_api_key(key_id)
            assert api_key is not None
            assert api_key["id"] == key_id
            assert api_key["name"] == "Get Test Key"
            assert api_key["key"] == "get-test-placeholder"
    
    def test_get_api_key_not_found(self, temp_db):
        """Test fetching a non-existent API key."""
        with Database(temp_db) as db:
            api_key = db.get_api_key(99999)
            assert api_key is None
    
    def test_list_api_keys(self, temp_db):
        """Test listing all API keys."""
        with Database(temp_db) as db:
            # Create multiple keys
            key_id1 = db.create_api_key("Key 1", "key-one-placeholder", "2026-03-16T10:00:00Z")
            key_id2 = db.create_api_key("Key 2", "key-two-placeholder", "2026-03-16T11:00:00Z")
            key_id3 = db.create_api_key("Key 3", "key-three-placeholder", "2026-03-16T12:00:00Z")
            
            # List all keys
            api_keys = db.list_api_keys()
            assert len(api_keys) == 3
            
            # Verify order (DESC by ID)
            assert api_keys[0]["id"] == key_id3
            assert api_keys[1]["id"] == key_id2
            assert api_keys[2]["id"] == key_id1
    
    def test_list_api_keys_empty(self, temp_db):
        """Test listing API keys when none exist."""
        with Database(temp_db) as db:
            api_keys = db.list_api_keys()
            assert api_keys == []
    
    def test_delete_api_key(self, temp_db):
        """Test deleting an API key."""
        with Database(temp_db) as db:
            # Create a key
            key_id = db.create_api_key("Delete Test", "delete-test-placeholder")
            
            # Verify it exists
            assert db.get_api_key(key_id) is not None
            
            # Delete it
            deleted = db.delete_api_key(key_id)
            assert deleted == 1
            
            # Verify it's gone
            assert db.get_api_key(key_id) is None
    
    def test_delete_api_key_not_found(self, temp_db):
        """Test deleting a non-existent API key."""
        with Database(temp_db) as db:
            deleted = db.delete_api_key(99999)
            assert deleted == 0
    
    def test_verify_api_key_valid(self, temp_db):
        """Test verifying a valid API key."""
        with Database(temp_db) as db:
            # Create a key
            db.create_api_key("Verify Test", "verify-test-placeholder")
            
            # Verify it
            assert db.verify_api_key("verify-test-placeholder") is True
    
    def test_verify_api_key_invalid(self, temp_db):
        """Test verifying an invalid API key."""
        with Database(temp_db) as db:
            assert db.verify_api_key("nonexistent-key") is False
    
    def test_verify_api_key_empty_string(self, temp_db):
        """Test verifying an empty API key string."""
        with Database(temp_db) as db:
            assert db.verify_api_key("") is False
    
    def test_create_duplicate_key(self, temp_db):
        """Test that creating a duplicate key raises an error."""
        with Database(temp_db) as db:
            db.create_api_key("Original", "duplicate-test-placeholder")
            
            # Attempt to create duplicate should raise IntegrityError
            with pytest.raises(sqlite3.IntegrityError):
                db.create_api_key("Duplicate", "duplicate-test-placeholder")
    
    def test_api_key_crud_workflow(self, temp_db):
        """Test complete CRUD workflow for API keys."""
        with Database(temp_db) as db:
            # Create
            key_id = db.create_api_key("Workflow Key", "workflow-test-placeholder")
            assert key_id > 0
            
            # Read
            api_key = db.get_api_key(key_id)
            assert api_key["name"] == "Workflow Key"
            
            # List
            all_keys = db.list_api_keys()
            assert len(all_keys) == 1
            assert all_keys[0]["id"] == key_id
            
            # Verify
            assert db.verify_api_key("workflow-test-placeholder") is True
            
            # Delete
            deleted = db.delete_api_key(key_id)
            assert deleted == 1
            
            # Verify deletion
            assert db.get_api_key(key_id) is None
            assert db.verify_api_key("workflow-test-placeholder") is False
            assert len(db.list_api_keys()) == 0
    
    def test_multiple_keys_different_names(self, temp_db):
        """Test creating multiple keys with different names but same pattern."""
        with Database(temp_db) as db:
            key_id1 = db.create_api_key("Production", "prod-key-placeholder")
            key_id2 = db.create_api_key("Development", "dev-key-placeholder")
            key_id3 = db.create_api_key("Testing", "test-key-placeholder")
            
            # All should be created successfully
            assert key_id1 > 0
            assert key_id2 > 0
            assert key_id3 > 0
            
            # All should be verifiable
            assert db.verify_api_key("prod-key-placeholder") is True
            assert db.verify_api_key("dev-key-placeholder") is True
            assert db.verify_api_key("test-key-placeholder") is True
            
            # List should contain all three
            all_keys = db.list_api_keys()
            assert len(all_keys) == 3
