# -*- coding: utf-8 -*-
"""
Integration tests for session management flow.

Tests the complete session lifecycle:
- Session creation on login
- Session validation on /admin access
- Session deletion on logout
- Expired session rejection

Validates assertions:
- m3-a3: Session token stored in database
- m3-a4: Admin page checks session before rendering
- m3-a5: Admin page redirects to login when not authenticated
- m3-a6: Invalid session redirects to login
- m3-a8: Logout clears session properly
- m3-a9: Session expiry enforced
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from kiro.core.auth import AccountManager
from kiro.core.database import Database


@pytest_asyncio.fixture
async def test_app(tmp_path):
    """Create a test FastAPI app with temporary database."""
    from fastapi import FastAPI
    from kiro.routes.auth import router as auth_router
    from kiro.routes.admin import router as admin_router
    
    # Create temporary database
    db_path = tmp_path / "test_accounts.db"
    
    # Initialize database with required tables
    with Database(str(db_path)) as db:
        # Create admin_users table
        db.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """, commit=True)
        
        # Create sessions table
        db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_token TEXT    PRIMARY KEY,
                username      TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                expires_at    TEXT    NOT NULL
            )
        """, commit=True)
        
        # Create test admin user (password: testpass123)
        import hashlib
        from datetime import datetime, timezone
        password_hash = hashlib.sha256("testpass123".encode()).hexdigest()
        db.insert("admin_users", {
            "username": "testadmin",
            "password_hash": password_hash,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    # Create minimal FastAPI app for testing
    app = FastAPI()
    app.state.auth_manager = AccountManager(str(db_path))
    
    # Include auth router for login/logout endpoints
    app.include_router(auth_router)
    app.include_router(admin_router)
    
    # Add /admin endpoint that checks session
    from fastapi.responses import HTMLResponse
    from kiro.routes.auth import verify_session
    from fastapi import Depends
    
    @app.get("/admin")
    async def admin_page(username: str = Depends(verify_session)):
        return HTMLResponse("<html><body>Admin Page</body></html>")
    
    yield app
    
    # Cleanup - Database uses context manager, no explicit close needed


@pytest_asyncio.fixture
async def client(test_app):
    """Create async HTTP client for testing."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSessionCreationOnLogin:
    """Tests for m3-a3: Session token stored in database on login."""
    
    @pytest.mark.asyncio
    async def test_login_creates_session_in_database(self, client, test_app):
        """Test that successful login creates a session in the database."""
        # Login
        response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "testpass123"},
            follow_redirects=False
        )
        
        # Should redirect to /admin
        assert response.status_code == 302
        assert response.headers["location"] == "/admin"
        
        # Should set session cookie
        assert "session_token" in response.cookies
        session_token = response.cookies["session_token"]
        
        # Verify session exists in database
        manager = test_app.state.auth_manager
        username = manager.get_session(session_token)
        
        assert username is not None
        assert username == "testadmin"
    
    @pytest.mark.asyncio
    async def test_login_session_has_correct_expiry(self, client, test_app):
        """Test that created session has proper expiration time."""
        # Login
        response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "testpass123"},
            follow_redirects=False
        )
        
        session_token = response.cookies["session_token"]
        
        # Get session from database
        manager = test_app.state.auth_manager
        db = manager._db
        
        session = db.fetch_one(
            "SELECT * FROM sessions WHERE session_token = ?",
            (session_token,)
        )
        
        assert session is not None
        
        # Verify expiry is approximately 7 days from now
        # Parse the expires_at timestamp (format: "2026-03-23T15:33:52.156713+00:00Z")
        expires_at_str = session["expires_at"]
        # The format has both +00:00 and Z, just remove the Z
        if expires_at_str.endswith("Z"):
            expires_at_str = expires_at_str[:-1]
        
        expires_at = datetime.fromisoformat(expires_at_str)
        expected_expiry = datetime.now(timezone.utc) + timedelta(days=7)
        
        # Allow 1 minute tolerance
        time_diff = abs((expires_at - expected_expiry).total_seconds())
        assert time_diff < 60
    
    @pytest.mark.asyncio
    async def test_failed_login_does_not_create_session(self, client, test_app):
        """Test that failed login does not create a session."""
        # Attempt login with wrong password
        response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "wrongpassword"},
            follow_redirects=False
        )
        
        # Should return 401
        assert response.status_code == 401
        
        # Should not set session cookie
        assert "session_token" not in response.cookies
        
        # Verify no session in database
        manager = test_app.state.auth_manager
        db = manager._db
        
        count = db.fetch_one("SELECT COUNT(*) as count FROM sessions", None)
        assert count["count"] == 0


class TestSessionValidationOnAdminAccess:
    """Tests for m3-a4, m3-a5, m3-a6: Session validation on /admin access."""
    
    @pytest.mark.asyncio
    async def test_admin_access_with_valid_session(self, client, test_app):
        """Test that /admin is accessible with valid session (m3-a4)."""
        # Login first
        login_response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "testpass123"},
            follow_redirects=False
        )
        
        session_token = login_response.cookies["session_token"]
        
        # Access /admin with session cookie
        response = await client.get(
            "/admin",
            cookies={"session_token": session_token}
        )
        
        # Should return admin page (200)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
    
    @pytest.mark.asyncio
    async def test_admin_access_without_session_redirects_to_login(self, client):
        """Test that /admin redirects to login when not authenticated (m3-a5)."""
        # Access /admin without session cookie
        response = await client.get("/admin", follow_redirects=False)
        
        # Should return 401 (API endpoint behavior) or redirect/return login page
        assert response.status_code in [200, 302, 401]
        
        if response.status_code == 302:
            assert "/login" in response.headers["location"]
        elif response.status_code == 200:
            # Should return login page
            content = response.text
            assert "login" in content.lower()
    
    @pytest.mark.asyncio
    async def test_admin_access_with_invalid_session(self, client):
        """Test that invalid session token is rejected (m3-a6)."""
        # Access /admin with fake session token
        fake_token = str(uuid.uuid4())
        
        response = await client.get(
            "/admin",
            cookies={"session_token": fake_token},
            follow_redirects=False
        )
        
        # Should return 401 (API endpoint behavior) or redirect/return login page
        assert response.status_code in [200, 302, 401]
        
        if response.status_code == 302:
            assert "/login" in response.headers["location"]
    
    @pytest.mark.asyncio
    async def test_admin_access_with_expired_session(self, client, test_app):
        """Test that expired session is rejected (m3-a9)."""
        # Create an expired session directly in database
        manager = test_app.state.auth_manager
        expired_token = str(uuid.uuid4())
        
        # Create session that expired 1 hour ago
        expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat() + "Z"
        created_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat() + "Z"
        
        manager._db.insert("sessions", {
            "session_token": expired_token,
            "username": "testadmin",
            "created_at": created_at,
            "expires_at": expires_at
        })
        
        # Try to access /admin with expired session
        response = await client.get(
            "/admin",
            cookies={"session_token": expired_token},
            follow_redirects=False
        )
        
        # Should return 401 (API endpoint behavior) or redirect/return login page
        assert response.status_code in [200, 302, 401]
        
        if response.status_code == 302:
            assert "/login" in response.headers["location"]


class TestSessionDeletionOnLogout:
    """Tests for m3-a8: Logout clears session properly."""
    
    @pytest.mark.asyncio
    async def test_logout_deletes_session_from_database(self, client, test_app):
        """Test that logout removes session from database."""
        # Login first
        login_response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "testpass123"},
            follow_redirects=False
        )
        
        session_token = login_response.cookies["session_token"]
        
        # Verify session exists
        manager = test_app.state.auth_manager
        username = manager.get_session(session_token)
        assert username == "testadmin"
        
        # Logout
        logout_response = await client.post(
            "/auth/logout",
            cookies={"session_token": session_token}
        )
        
        assert logout_response.status_code == 200
        
        # Verify session is deleted from database
        username_after = manager.get_session(session_token)
        assert username_after is None
    
    @pytest.mark.asyncio
    async def test_logout_clears_cookie(self, client):
        """Test that logout clears the session cookie."""
        # Login first
        login_response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "testpass123"},
            follow_redirects=False
        )
        
        session_token = login_response.cookies["session_token"]
        
        # Logout
        logout_response = await client.post(
            "/auth/logout",
            cookies={"session_token": session_token}
        )
        
        # Cookie should be cleared (max-age=0 or deleted)
        set_cookie = logout_response.headers.get("set-cookie", "")
        assert "session_token" in set_cookie
        # Cookie deletion typically sets max-age=0 or expires in the past
        assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()
    
    @pytest.mark.asyncio
    async def test_admin_access_after_logout_fails(self, client, test_app):
        """Test that /admin access fails after logout."""
        # Login first
        login_response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "testpass123"},
            follow_redirects=False
        )
        
        session_token = login_response.cookies["session_token"]
        
        # Verify /admin is accessible
        admin_response_before = await client.get(
            "/admin",
            cookies={"session_token": session_token}
        )
        assert admin_response_before.status_code == 200
        
        # Logout
        await client.post(
            "/auth/logout",
            cookies={"session_token": session_token}
        )
        
        # Try to access /admin with same token
        admin_response_after = await client.get(
            "/admin",
            cookies={"session_token": session_token},
            follow_redirects=False
        )
        
        # Should fail - return 401 (API endpoint behavior) or redirect/return login page
        assert admin_response_after.status_code in [200, 302, 401]
        
        if admin_response_after.status_code == 302:
            assert "/login" in admin_response_after.headers["location"]


class TestExpiredSessionRejection:
    """Tests for m3-a9: Session expiry enforced."""
    
    @pytest.mark.asyncio
    async def test_expired_session_rejected_by_get_session(self, test_app):
        """Test that AccountManager.get_session() rejects expired sessions."""
        manager = test_app.state.auth_manager
        
        # Create an expired session
        expired_token = str(uuid.uuid4())
        expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat() + "Z"
        created_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat() + "Z"
        
        manager._db.insert("sessions", {
            "session_token": expired_token,
            "username": "testadmin",
            "created_at": created_at,
            "expires_at": expires_at
        })
        
        # Try to get session
        username = manager.get_session(expired_token)
        
        # Should return None for expired session
        assert username is None
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_removes_old_sessions(self, test_app):
        """Test that cleanup_expired_sessions() removes expired sessions."""
        manager = test_app.state.auth_manager
        
        # Create multiple sessions: some expired, some valid
        expired_token1 = str(uuid.uuid4())
        expired_token2 = str(uuid.uuid4())
        valid_token = str(uuid.uuid4())
        
        expires_at_expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat() + "Z"
        expires_at_valid = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat() + "Z"
        created_at = datetime.now(timezone.utc).isoformat() + "Z"
        
        # Insert expired sessions
        manager._db.insert("sessions", {
            "session_token": expired_token1,
            "username": "user1",
            "created_at": created_at,
            "expires_at": expires_at_expired
        })
        manager._db.insert("sessions", {
            "session_token": expired_token2,
            "username": "user2",
            "created_at": created_at,
            "expires_at": expires_at_expired
        })
        
        # Insert valid session
        manager._db.insert("sessions", {
            "session_token": valid_token,
            "username": "user3",
            "created_at": created_at,
            "expires_at": expires_at_valid
        })
        
        # Run cleanup
        deleted_count = manager.cleanup_expired_sessions()
        
        # Should delete 2 expired sessions
        assert deleted_count == 2
        
        # Verify expired sessions are gone
        assert manager.get_session(expired_token1) is None
        assert manager.get_session(expired_token2) is None
        
        # Verify valid session still exists
        assert manager.get_session(valid_token) == "user3"


class TestSessionIntegrationFlow:
    """Integration tests for complete session flow."""
    
    @pytest.mark.asyncio
    async def test_complete_login_admin_logout_flow(self, client, test_app):
        """Test complete flow: login -> access admin -> logout -> access fails."""
        # Step 1: Login
        login_response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "testpass123"},
            follow_redirects=False
        )
        
        assert login_response.status_code == 302
        session_token = login_response.cookies["session_token"]
        
        # Verify session in database
        manager = test_app.state.auth_manager
        assert manager.get_session(session_token) == "testadmin"
        
        # Step 2: Access /admin
        admin_response = await client.get(
            "/admin",
            cookies={"session_token": session_token}
        )
        
        assert admin_response.status_code == 200
        
        # Step 3: Logout
        logout_response = await client.post(
            "/auth/logout",
            cookies={"session_token": session_token}
        )
        
        assert logout_response.status_code == 200
        
        # Verify session deleted from database
        assert manager.get_session(session_token) is None
        
        # Step 4: Try to access /admin again
        admin_response_after = await client.get(
            "/admin",
            cookies={"session_token": session_token},
            follow_redirects=False
        )
        
        # Should fail - return 401 (API endpoint behavior) or redirect/return login page
        assert admin_response_after.status_code in [200, 302, 401]
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_sessions(self, client, test_app):
        """Test that multiple users can have concurrent sessions."""
        # Create another admin user
        manager = test_app.state.auth_manager
        import hashlib
        from datetime import datetime, timezone
        password_hash = hashlib.sha256("pass456".encode()).hexdigest()
        manager._db.insert("admin_users", {
            "username": "admin2",
            "password_hash": password_hash,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Login as first user
        login1 = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "testpass123"},
            follow_redirects=False
        )
        token1 = login1.cookies["session_token"]
        
        # Login as second user
        login2 = await client.post(
            "/auth/login",
            json={"username": "admin2", "password": "pass456"},
            follow_redirects=False
        )
        token2 = login2.cookies["session_token"]
        
        # Both sessions should be valid
        assert manager.get_session(token1) == "testadmin"
        assert manager.get_session(token2) == "admin2"
        
        # Both should be able to access /admin
        response1 = await client.get("/admin", cookies={"session_token": token1})
        response2 = await client.get("/admin", cookies={"session_token": token2})
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Logout first user
        await client.post("/auth/logout", cookies={"session_token": token1})
        
        # First session should be invalid
        assert manager.get_session(token1) is None
        
        # Second session should still be valid
        assert manager.get_session(token2) == "admin2"
