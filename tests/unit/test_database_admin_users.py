# -*- coding: utf-8 -*-
"""
Unit tests for Database admin user management methods.
"""

import pytest
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from kiro.core.database import Database


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database with admin_users table."""
    db_path = tmp_path / "test_admin_users.db"
    
    # Create database and admin_users table
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE admin_users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    
    return str(db_path)


class TestGetAdminUser:
    """Tests for Database.get_admin_user()"""
    
    def test_get_existing_user(self, temp_db):
        """Should return user row when user exists."""
        # Setup: Insert a test user
        with Database(temp_db) as db:
            user_id = db.create_admin_user(
                username="testuser",
                password_hash="test_hash_value",
                created_at="2026-03-16T10:00:00Z"
            )
        
        # Test: Retrieve the user
        with Database(temp_db) as db:
            user = db.get_admin_user("testuser")
        
        # Verify
        assert user is not None
        assert user["id"] == user_id
        assert user["username"] == "testuser"
        assert user["password_hash"] == "test_hash_value"
        assert user["created_at"] == "2026-03-16T10:00:00Z"
    
    def test_get_nonexistent_user(self, temp_db):
        """Should return None when user doesn't exist."""
        with Database(temp_db) as db:
            user = db.get_admin_user("nonexistent")
        
        assert user is None
    
    def test_get_user_case_sensitive(self, temp_db):
        """Username lookup should be case-sensitive."""
        with Database(temp_db) as db:
            db.create_admin_user("TestUser", "hash123")
            
            # Exact match should work
            user = db.get_admin_user("TestUser")
            assert user is not None
            
            # Different case should not match
            user = db.get_admin_user("testuser")
            assert user is None


class TestListAdminUsers:
    """Tests for Database.list_admin_users()"""
    
    def test_list_empty(self, temp_db):
        """Should return empty list when no users exist."""
        with Database(temp_db) as db:
            users = db.list_admin_users()
        
        assert users == []
    
    def test_list_single_user(self, temp_db):
        """Should return list with one user."""
        with Database(temp_db) as db:
            user_id = db.create_admin_user("admin", "hash123")
            users = db.list_admin_users()
        
        assert len(users) == 1
        assert users[0]["id"] == user_id
        assert users[0]["username"] == "admin"
    
    def test_list_multiple_users(self, temp_db):
        """Should return all users ordered by ID."""
        with Database(temp_db) as db:
            id1 = db.create_admin_user("admin1", "hash1")
            id2 = db.create_admin_user("admin2", "hash2")
            id3 = db.create_admin_user("admin3", "hash3")
            
            users = db.list_admin_users()
        
        assert len(users) == 3
        assert users[0]["id"] == id1
        assert users[1]["id"] == id2
        assert users[2]["id"] == id3
        assert users[0]["username"] == "admin1"
        assert users[1]["username"] == "admin2"
        assert users[2]["username"] == "admin3"
    
    def test_list_ordered_by_id(self, temp_db):
        """Should return users ordered by ID ascending."""
        with Database(temp_db) as db:
            # Create users in specific order
            db.create_admin_user("user_c", "hash3")
            db.create_admin_user("user_a", "hash1")
            db.create_admin_user("user_b", "hash2")
            
            users = db.list_admin_users()
        
        # Should be ordered by ID (insertion order), not username
        assert len(users) == 3
        assert users[0]["username"] == "user_c"
        assert users[1]["username"] == "user_a"
        assert users[2]["username"] == "user_b"


class TestCreateAdminUser:
    """Tests for Database.create_admin_user()"""
    
    def test_create_user_with_all_fields(self, temp_db):
        """Should create user with all fields specified."""
        timestamp = "2026-03-16T12:00:00Z"
        
        with Database(temp_db) as db:
            user_id = db.create_admin_user(
                username="newadmin",
                password_hash="test_hash_value",
                created_at=timestamp
            )
        
        # Verify user was created
        assert user_id > 0
        
        with Database(temp_db) as db:
            user = db.get_admin_user("newadmin")
        
        assert user is not None
        assert user["id"] == user_id
        assert user["username"] == "newadmin"
        assert user["password_hash"] == "test_hash_value"
        assert user["created_at"] == timestamp
    
    def test_create_user_auto_timestamp(self, temp_db):
        """Should auto-generate timestamp if not provided."""
        before = datetime.now(timezone.utc).isoformat()
        
        with Database(temp_db) as db:
            user_id = db.create_admin_user(
                username="autotimeuser",
                password_hash="hash789"
            )
        
        after = datetime.now(timezone.utc).isoformat()
        
        with Database(temp_db) as db:
            user = db.get_admin_user("autotimeuser")
        
        assert user is not None
        assert user["created_at"] >= before
        assert user["created_at"] <= after
    
    def test_create_duplicate_username(self, temp_db):
        """Should raise IntegrityError for duplicate username."""
        with Database(temp_db) as db:
            db.create_admin_user("duplicate", "hash1")
            
            with pytest.raises(sqlite3.IntegrityError):
                db.create_admin_user("duplicate", "hash2")
    
    def test_create_multiple_users(self, temp_db):
        """Should create multiple users successfully."""
        with Database(temp_db) as db:
            id1 = db.create_admin_user("user1", "hash1")
            id2 = db.create_admin_user("user2", "hash2")
            id3 = db.create_admin_user("user3", "hash3")
        
        assert id1 < id2 < id3  # IDs should increment
        
        with Database(temp_db) as db:
            users = db.list_admin_users()
        
        assert len(users) == 3


class TestUpdateAdminPassword:
    """Tests for Database.update_admin_password()"""
    
    def test_update_existing_user_password(self, temp_db):
        """Should update password for existing user."""
        with Database(temp_db) as db:
            db.create_admin_user("admin", "old_hash")
            
            rows_updated = db.update_admin_password("admin", "new_hash")
        
        assert rows_updated == 1
        
        # Verify password was updated
        with Database(temp_db) as db:
            user = db.get_admin_user("admin")
        
        assert user["password_hash"] == "new_hash"
    
    def test_update_nonexistent_user(self, temp_db):
        """Should return 0 when user doesn't exist."""
        with Database(temp_db) as db:
            rows_updated = db.update_admin_password("nonexistent", "new_hash")
        
        assert rows_updated == 0
    
    def test_update_preserves_other_fields(self, temp_db):
        """Should only update password, not other fields."""
        timestamp = "2026-03-16T10:00:00Z"
        
        with Database(temp_db) as db:
            user_id = db.create_admin_user(
                username="testuser",
                password_hash="old_hash",
                created_at=timestamp
            )
            
            db.update_admin_password("testuser", "new_hash")
            
            user = db.get_admin_user("testuser")
        
        # Verify only password changed
        assert user["id"] == user_id
        assert user["username"] == "testuser"
        assert user["password_hash"] == "new_hash"
        assert user["created_at"] == timestamp
    
    def test_update_multiple_times(self, temp_db):
        """Should allow multiple password updates."""
        with Database(temp_db) as db:
            db.create_admin_user("admin", "hash1")
            
            db.update_admin_password("admin", "hash2")
            user = db.get_admin_user("admin")
            assert user["password_hash"] == "hash2"
            
            db.update_admin_password("admin", "hash3")
            user = db.get_admin_user("admin")
            assert user["password_hash"] == "hash3"


class TestDeleteAdminUser:
    """Tests for Database.delete_admin_user()"""
    
    def test_delete_existing_user(self, temp_db):
        """Should delete existing user and return 1."""
        with Database(temp_db) as db:
            db.create_admin_user("todelete", "hash123")
            
            rows_deleted = db.delete_admin_user("todelete")
        
        assert rows_deleted == 1
        
        # Verify user was deleted
        with Database(temp_db) as db:
            user = db.get_admin_user("todelete")
        
        assert user is None
    
    def test_delete_nonexistent_user(self, temp_db):
        """Should return 0 when user doesn't exist."""
        with Database(temp_db) as db:
            rows_deleted = db.delete_admin_user("nonexistent")
        
        assert rows_deleted == 0
    
    def test_delete_one_of_many(self, temp_db):
        """Should delete only the specified user."""
        with Database(temp_db) as db:
            db.create_admin_user("user1", "hash1")
            db.create_admin_user("user2", "hash2")
            db.create_admin_user("user3", "hash3")
            
            db.delete_admin_user("user2")
            
            users = db.list_admin_users()
        
        assert len(users) == 2
        assert users[0]["username"] == "user1"
        assert users[1]["username"] == "user3"
    
    def test_delete_and_recreate(self, temp_db):
        """Should allow recreating user after deletion."""
        with Database(temp_db) as db:
            id1 = db.create_admin_user("admin", "hash1")
            db.delete_admin_user("admin")
            
            id2 = db.create_admin_user("admin", "hash2")
        
        # New user should have different ID
        assert id2 > id1
        
        with Database(temp_db) as db:
            user = db.get_admin_user("admin")
        
        assert user["id"] == id2
        assert user["password_hash"] == "hash2"


class TestAdminUserIntegration:
    """Integration tests for admin user methods."""
    
    def test_full_crud_cycle(self, temp_db):
        """Test complete CRUD cycle for admin users."""
        with Database(temp_db) as db:
            # Create
            user_id = db.create_admin_user("admin", "initial_hash")
            assert user_id > 0
            
            # Read (get)
            user = db.get_admin_user("admin")
            assert user is not None
            assert user["username"] == "admin"
            
            # Read (list)
            users = db.list_admin_users()
            assert len(users) == 1
            
            # Update
            rows = db.update_admin_password("admin", "updated_hash")
            assert rows == 1
            user = db.get_admin_user("admin")
            assert user["password_hash"] == "updated_hash"
            
            # Delete
            rows = db.delete_admin_user("admin")
            assert rows == 1
            user = db.get_admin_user("admin")
            assert user is None
    
    def test_concurrent_operations(self, temp_db):
        """Test multiple operations in sequence."""
        with Database(temp_db) as db:
            # Create multiple users
            db.create_admin_user("admin1", "hash1")
            db.create_admin_user("admin2", "hash2")
            db.create_admin_user("admin3", "hash3")
            
            # Update one
            db.update_admin_password("admin2", "new_hash2")
            
            # Delete one
            db.delete_admin_user("admin1")
            
            # List remaining
            users = db.list_admin_users()
            assert len(users) == 2
            assert users[0]["username"] == "admin2"
            assert users[0]["password_hash"] == "new_hash2"
            assert users[1]["username"] == "admin3"
    
    def test_context_manager_usage(self, temp_db):
        """Test that context manager properly handles connections."""
        # Create user in one context
        with Database(temp_db) as db:
            db.create_admin_user("test", "hash")
        
        # Read in another context
        with Database(temp_db) as db:
            user = db.get_admin_user("test")
            assert user is not None
        
        # Update in another context
        with Database(temp_db) as db:
            db.update_admin_password("test", "new_hash")
        
        # Verify in another context
        with Database(temp_db) as db:
            user = db.get_admin_user("test")
            assert user["password_hash"] == "new_hash"
