# -*- coding: utf-8 -*-
"""
Unit tests for Database session management methods.

Tests:
- create_session()
- get_session()
- delete_session()
- cleanup_expired_sessions()
"""

import pytest
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kiro.core.database import Database


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_sessions.db"
    
    # Initialize database with sessions table
    with Database(str(db_path)) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_token TEXT    PRIMARY KEY,
                username      TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                expires_at    TEXT    NOT NULL
            )
        """, commit=True)
    
    yield str(db_path)


class TestCreateSession:
    """Tests for create_session() method."""
    
    def test_create_session_basic(self, temp_db):
        """Test creating a basic session."""
        with Database(temp_db) as db:
            token = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            result = db.create_session(
                username="testuser",
                token=token,
                expires_at=expires_at
            )
            
            assert result == token
            
            # Verify session was created
            session = db.get_session(token)
            assert session is not None
            assert session["session_token"] == token
            assert session["username"] == "testuser"
            assert session["expires_at"] == expires_at
            assert session["created_at"] is not None
    
    def test_create_session_with_different_usernames(self, temp_db):
        """Test creating sessions for different users."""
        with Database(temp_db) as db:
            token1 = str(uuid.uuid4())
            token2 = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            db.create_session("user1", token1, expires_at)
            db.create_session("user2", token2, expires_at)
            
            session1 = db.get_session(token1)
            session2 = db.get_session(token2)
            
            assert session1["username"] == "user1"
            assert session2["username"] == "user2"
    
    def test_create_session_duplicate_token_fails(self, temp_db):
        """Test that creating a session with duplicate token fails."""
        with Database(temp_db) as db:
            token = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            db.create_session("user1", token, expires_at)
            
            # Attempting to create another session with same token should fail
            with pytest.raises(sqlite3.IntegrityError):
                db.create_session("user2", token, expires_at)
    
    def test_create_session_sets_created_at(self, temp_db):
        """Test that created_at timestamp is automatically set."""
        with Database(temp_db) as db:
            token = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            before = datetime.now(timezone.utc)
            db.create_session("testuser", token, expires_at)
            after = datetime.now(timezone.utc)
            
            session = db.get_session(token)
            created_at = datetime.fromisoformat(session["created_at"])
            
            # created_at should be between before and after
            assert before <= created_at <= after


class TestGetSession:
    """Tests for get_session() method."""
    
    def test_get_session_exists(self, temp_db):
        """Test getting an existing session."""
        with Database(temp_db) as db:
            token = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            db.create_session("testuser", token, expires_at)
            
            session = db.get_session(token)
            
            assert session is not None
            assert session["session_token"] == token
            assert session["username"] == "testuser"
            assert session["expires_at"] == expires_at
    
    def test_get_session_not_exists(self, temp_db):
        """Test getting a non-existent session returns None."""
        with Database(temp_db) as db:
            session = db.get_session("nonexistent-token")
            
            assert session is None
    
    def test_get_session_returns_all_fields(self, temp_db):
        """Test that get_session returns all session fields."""
        with Database(temp_db) as db:
            token = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            db.create_session("testuser", token, expires_at)
            
            session = db.get_session(token)
            
            # Check all expected fields are present
            assert "session_token" in session.keys()
            assert "username" in session.keys()
            assert "created_at" in session.keys()
            assert "expires_at" in session.keys()


class TestDeleteSession:
    """Tests for delete_session() method."""
    
    def test_delete_session_exists(self, temp_db):
        """Test deleting an existing session."""
        with Database(temp_db) as db:
            token = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            db.create_session("testuser", token, expires_at)
            
            # Verify session exists
            assert db.get_session(token) is not None
            
            # Delete session
            deleted = db.delete_session(token)
            
            assert deleted == 1
            
            # Verify session no longer exists
            assert db.get_session(token) is None
    
    def test_delete_session_not_exists(self, temp_db):
        """Test deleting a non-existent session returns 0."""
        with Database(temp_db) as db:
            deleted = db.delete_session("nonexistent-token")
            
            assert deleted == 0
    
    def test_delete_session_does_not_affect_others(self, temp_db):
        """Test that deleting one session doesn't affect others."""
        with Database(temp_db) as db:
            token1 = str(uuid.uuid4())
            token2 = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            db.create_session("user1", token1, expires_at)
            db.create_session("user2", token2, expires_at)
            
            # Delete first session
            db.delete_session(token1)
            
            # Second session should still exist
            assert db.get_session(token1) is None
            assert db.get_session(token2) is not None


class TestCleanupExpiredSessions:
    """Tests for cleanup_expired_sessions() method."""
    
    def test_cleanup_expired_sessions_removes_expired(self, temp_db):
        """Test that cleanup removes expired sessions."""
        with Database(temp_db) as db:
            # Create an expired session (expired 1 hour ago)
            token_expired = str(uuid.uuid4())
            expires_at_expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            db.create_session("expired_user", token_expired, expires_at_expired)
            
            # Create a valid session (expires in 24 hours)
            token_valid = str(uuid.uuid4())
            expires_at_valid = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            db.create_session("valid_user", token_valid, expires_at_valid)
            
            # Run cleanup
            deleted = db.cleanup_expired_sessions()
            
            assert deleted == 1
            
            # Verify expired session is gone
            assert db.get_session(token_expired) is None
            
            # Verify valid session still exists
            assert db.get_session(token_valid) is not None
    
    def test_cleanup_expired_sessions_no_expired(self, temp_db):
        """Test cleanup when there are no expired sessions."""
        with Database(temp_db) as db:
            # Create only valid sessions
            token1 = str(uuid.uuid4())
            token2 = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            db.create_session("user1", token1, expires_at)
            db.create_session("user2", token2, expires_at)
            
            # Run cleanup
            deleted = db.cleanup_expired_sessions()
            
            assert deleted == 0
            
            # Verify both sessions still exist
            assert db.get_session(token1) is not None
            assert db.get_session(token2) is not None
    
    def test_cleanup_expired_sessions_multiple_expired(self, temp_db):
        """Test cleanup removes multiple expired sessions."""
        with Database(temp_db) as db:
            # Create multiple expired sessions
            expires_at_expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            
            token1 = str(uuid.uuid4())
            token2 = str(uuid.uuid4())
            token3 = str(uuid.uuid4())
            
            db.create_session("user1", token1, expires_at_expired)
            db.create_session("user2", token2, expires_at_expired)
            db.create_session("user3", token3, expires_at_expired)
            
            # Run cleanup
            deleted = db.cleanup_expired_sessions()
            
            assert deleted == 3
            
            # Verify all expired sessions are gone
            assert db.get_session(token1) is None
            assert db.get_session(token2) is None
            assert db.get_session(token3) is None
    
    def test_cleanup_expired_sessions_empty_table(self, temp_db):
        """Test cleanup on empty sessions table."""
        with Database(temp_db) as db:
            deleted = db.cleanup_expired_sessions()
            
            assert deleted == 0
    
    def test_cleanup_expired_sessions_boundary_case(self, temp_db):
        """Test cleanup with sessions expiring at exact current time."""
        with Database(temp_db) as db:
            # Create a session that expires right now
            token = str(uuid.uuid4())
            expires_at = datetime.now(timezone.utc).isoformat()
            db.create_session("boundary_user", token, expires_at)
            
            # Wait a tiny bit to ensure current time is past expires_at
            import time
            time.sleep(0.01)
            
            # Run cleanup
            deleted = db.cleanup_expired_sessions()
            
            # Session should be deleted (expires_at < now)
            assert deleted == 1
            assert db.get_session(token) is None


class TestSessionIntegration:
    """Integration tests for session management workflow."""
    
    def test_full_session_lifecycle(self, temp_db):
        """Test complete session lifecycle: create, get, delete."""
        with Database(temp_db) as db:
            # Create session
            token = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            created_token = db.create_session("testuser", token, expires_at)
            assert created_token == token
            
            # Get session
            session = db.get_session(token)
            assert session is not None
            assert session["username"] == "testuser"
            
            # Delete session
            deleted = db.delete_session(token)
            assert deleted == 1
            
            # Verify deletion
            assert db.get_session(token) is None
    
    def test_multiple_users_multiple_sessions(self, temp_db):
        """Test managing sessions for multiple users."""
        with Database(temp_db) as db:
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            # Create sessions for multiple users
            tokens = {}
            for i in range(5):
                username = f"user{i}"
                token = str(uuid.uuid4())
                db.create_session(username, token, expires_at)
                tokens[username] = token
            
            # Verify all sessions exist
            for username, token in tokens.items():
                session = db.get_session(token)
                assert session is not None
                assert session["username"] == username
            
            # Delete some sessions
            db.delete_session(tokens["user1"])
            db.delete_session(tokens["user3"])
            
            # Verify correct sessions were deleted
            assert db.get_session(tokens["user0"]) is not None
            assert db.get_session(tokens["user1"]) is None
            assert db.get_session(tokens["user2"]) is not None
            assert db.get_session(tokens["user3"]) is None
            assert db.get_session(tokens["user4"]) is not None
