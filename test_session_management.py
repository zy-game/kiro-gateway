"""
Test session management API endpoints for validation contract assertions.

Tests:
- m3-a1: Login endpoint sets session cookie
- m3-a2: Login endpoint returns success response
- m3-a3: Session token stored in database
- m3-a8: Logout clears session properly
- m3-a9: Session expiry enforced
"""

import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

# Fix encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Disable proxy for localhost connections
BASE_URL = "http://127.0.0.1:8000"
DB_PATH = r"E:\kiro-gateway\data\accounts.db"
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin123"


def test_m3_a1_login_sets_cookie():
    """m3-a1: Login endpoint sets session cookie."""
    print("\n=== Testing m3-a1: Login endpoint sets session cookie ===")
    
    # Disable proxy for localhost
    client = httpx.Client(follow_redirects=False, timeout=10.0, proxy=None)
    
    response = client.post(
        f"{BASE_URL}/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print(f"Cookies: {response.cookies}")
    
    # Check for Set-Cookie header
    assert "set-cookie" in response.headers, "No Set-Cookie header in response"
    
    # Check for session_token cookie
    assert "session_token" in response.cookies, "No session_token cookie set"
    
    session_token = response.cookies.get("session_token")
    print(f"[PASS] Session token set: {session_token[:16]}...")
    
    client.close()
    return session_token


def test_m3_a2_login_returns_success():
    """m3-a2: Login endpoint returns success response."""
    print("\n=== Testing m3-a2: Login endpoint returns success response ===")
    
    client = httpx.Client(follow_redirects=False, timeout=10.0, proxy=None)
    
    response = client.post(
        f"{BASE_URL}/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    
    print(f"Status: {response.status_code}")
    
    # Should return 302 redirect (successful login)
    assert response.status_code == 302, f"Expected 302, got {response.status_code}"
    
    # Should redirect to /admin
    assert response.headers.get("location") == "/admin", "Should redirect to /admin"
    
    print(f"[PASS] Login returns 302 redirect to /admin")
    
    client.close()


def test_m3_a3_session_stored_in_database():
    """m3-a3: Session token stored in database."""
    print("\n=== Testing m3-a3: Session token stored in database ===")
    
    # First, login to create a session
    client = httpx.Client(follow_redirects=False, timeout=10.0, proxy=None)
    
    response = client.post(
        f"{BASE_URL}/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    
    session_token = response.cookies.get("session_token")
    print(f"Session token: {session_token[:16]}...")
    
    # Now check database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM sessions WHERE session_token = ?",
        (session_token,)
    )
    
    row = cursor.fetchone()
    
    assert row is not None, "Session not found in database"
    
    print(f"Database record:")
    print(f"  username: {row['username']}")
    print(f"  created_at: {row['created_at']}")
    print(f"  expires_at: {row['expires_at']}")
    
    assert row["username"] == TEST_USERNAME, f"Username mismatch: {row['username']}"
    
    # Check expiry is in the future
    expires_at_str = row["expires_at"]
    # Remove trailing Z if present
    if expires_at_str.endswith("Z"):
        expires_at_str = expires_at_str[:-1]
    # Parse as UTC
    expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    
    assert expires_at > now, "Session already expired"
    
    print(f"[PASS] Session stored in database with correct username and future expiry")
    
    conn.close()
    client.close()
    
    return session_token


def test_m3_a8_logout_clears_session():
    """m3-a8: Logout clears session properly."""
    print("\n=== Testing m3-a8: Logout clears session properly ===")
    
    # First, login to create a session
    client = httpx.Client(follow_redirects=False, timeout=10.0, proxy=None)
    
    response = client.post(
        f"{BASE_URL}/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    
    session_token = response.cookies.get("session_token")
    print(f"Created session: {session_token[:16]}...")
    
    # Verify session exists in database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE session_token = ?", (session_token,))
    count_before = cursor.fetchone()[0]
    print(f"Sessions in DB before logout: {count_before}")
    assert count_before == 1, "Session should exist before logout"
    
    # Now logout
    response = client.post(
        f"{BASE_URL}/auth/logout",
        cookies={"session_token": session_token}
    )
    
    print(f"Logout status: {response.status_code}")
    print(f"Logout response: {response.json()}")
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    # Verify session removed from database
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE session_token = ?", (session_token,))
    count_after = cursor.fetchone()[0]
    print(f"Sessions in DB after logout: {count_after}")
    
    assert count_after == 0, "Session should be removed from database"
    
    print(f"[PASS] Logout cleared session from database")
    
    # Verify subsequent /admin access requires login
    response = client.get(
        f"{BASE_URL}/admin",
        cookies={"session_token": session_token},
        follow_redirects=False
    )
    
    print(f"Admin access after logout: {response.status_code}")
    
    # Should return login page (not admin interface)
    assert response.status_code == 200, "Should return 200"
    assert "Login" in response.text, "Should show login page"
    assert "Admin Dashboard" not in response.text, "Should not show admin dashboard"
    
    print(f"[PASS] Admin access after logout requires re-login")
    
    conn.close()
    client.close()


def test_m3_a9_session_expiry_enforced():
    """m3-a9: Session expiry enforced."""
    print("\n=== Testing m3-a9: Session expiry enforced ===")
    
    # Create a session with very short expiry by directly inserting into database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Generate a test session token
    import secrets
    test_token = secrets.token_hex(32)
    
    # Create session that expires in 1 second
    created_at = datetime.now(timezone.utc).isoformat() + "Z"
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat() + "Z"
    
    cursor.execute(
        "INSERT INTO sessions (session_token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (test_token, TEST_USERNAME, created_at, expires_at)
    )
    conn.commit()
    
    print(f"Created test session: {test_token[:16]}...")
    print(f"Expires at: {expires_at}")
    
    # Verify session works initially
    client = httpx.Client(follow_redirects=False, timeout=10.0, proxy=None)
    
    response = client.get(
        f"{BASE_URL}/admin",
        cookies={"session_token": test_token}
    )
    
    print(f"Admin access before expiry: {response.status_code}")
    
    # Should work (either 200 with admin page or 302 redirect)
    assert response.status_code in [200, 302], f"Expected 200 or 302, got {response.status_code}"
    
    # Wait for session to expire
    print("Waiting 2 seconds for session to expire...")
    time.sleep(2)
    
    # Try to access admin with expired session
    response = client.get(
        f"{BASE_URL}/admin",
        cookies={"session_token": test_token},
        follow_redirects=False
    )
    
    print(f"Admin access after expiry: {response.status_code}")
    print(f"Response length: {len(response.text)}")
    
    # Should return login page (expired session rejected)
    assert response.status_code == 200, "Should return 200"
    assert "Login" in response.text, "Should show login page"
    assert "Admin Dashboard" not in response.text, "Should not show admin dashboard"
    
    print(f"[PASS] Expired session rejected, redirects to login")
    
    # Clean up test session
    cursor.execute("DELETE FROM sessions WHERE session_token = ?", (test_token,))
    conn.commit()
    
    conn.close()
    client.close()


if __name__ == "__main__":
    print("=" * 70)
    print("Session Management API Tests")
    print("=" * 70)
    
    try:
        test_m3_a1_login_sets_cookie()
        test_m3_a2_login_returns_success()
        test_m3_a3_session_stored_in_database()
        test_m3_a8_logout_clears_session()
        test_m3_a9_session_expiry_enforced()
        
        print("\n" + "=" * 70)
        print("ALL TESTS PASSED")
        print("=" * 70)
        
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\nERROR: {e}")
        raise
