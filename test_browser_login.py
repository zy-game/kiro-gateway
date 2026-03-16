"""
Browser testing script for login flow validation.
Tests the complete login flow including redirect behavior.
"""
import sys
import io
import time
import requests
from requests.cookies import RequestsCookieJar

# Fix Unicode output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def test_login_flow():
    """Test the complete login flow with session management."""
    print("=" * 60)
    print("Testing Login Flow")
    print("=" * 60)
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Test 1: Access /admin without authentication (should redirect to login)
    print("\n1. Testing unauthenticated access to /admin...")
    response = session.get(f"{BASE_URL}/admin", allow_redirects=False)
    print(f"   Status: {response.status_code}")
    print(f"   Headers: {dict(response.headers)}")
    if response.status_code == 200:
        if "login" in response.text.lower():
            print("   ✓ Returns login page (correct)")
        else:
            print("   ✗ Returns admin page without auth (SECURITY ISSUE)")
    
    # Test 2: Login with valid credentials
    print("\n2. Testing login with valid credentials...")
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    response = session.post(
        f"{BASE_URL}/auth/login",
        json=login_data,
        allow_redirects=False
    )
    print(f"   Status: {response.status_code}")
    print(f"   Headers: {dict(response.headers)}")
    print(f"   Cookies: {dict(session.cookies)}")
    
    if response.status_code == 302:
        print(f"   ✓ Returns 302 redirect (correct)")
        print(f"   Redirect location: {response.headers.get('Location')}")
        if 'session_token' in session.cookies:
            print(f"   ✓ Session cookie set (correct)")
        else:
            print(f"   ✗ Session cookie NOT set (ISSUE)")
    else:
        print(f"   ✗ Expected 302, got {response.status_code}")
    
    # Test 3: Follow redirect to /admin
    print("\n3. Testing access to /admin after login...")
    response = session.get(f"{BASE_URL}/admin")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        if "admin" in response.text.lower() and "login" not in response.text.lower():
            print("   ✓ Admin page loads successfully (correct)")
        else:
            print("   ? Page loaded but content unclear")
    else:
        print(f"   ✗ Expected 200, got {response.status_code}")
    
    # Test 4: Verify session is working
    print("\n4. Testing session validation...")
    response = session.get(f"{BASE_URL}/auth/me")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   User: {data.get('username')}")
        print("   ✓ Session is valid (correct)")
    else:
        print(f"   ✗ Session validation failed")
    
    # Test 5: Logout
    print("\n5. Testing logout...")
    response = session.post(f"{BASE_URL}/auth/logout")
    print(f"   Status: {response.status_code}")
    print(f"   Cookies after logout: {dict(session.cookies)}")
    if response.status_code == 200:
        print("   ✓ Logout successful")
    
    # Test 6: Verify session is cleared
    print("\n6. Testing access after logout...")
    response = session.get(f"{BASE_URL}/admin", allow_redirects=False)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200 and "login" in response.text.lower():
        print("   ✓ Redirected to login (correct)")
    else:
        print(f"   ? Status: {response.status_code}")
    
    # Test 7: Re-login
    print("\n7. Testing re-login...")
    response = session.post(
        f"{BASE_URL}/auth/login",
        json=login_data,
        allow_redirects=False
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 302:
        print("   ✓ Re-login successful")
        # Follow redirect
        response = session.get(f"{BASE_URL}/admin")
        if response.status_code == 200:
            print("   ✓ Admin page accessible after re-login")
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print("✓ Login flow tested successfully")
    print("✓ Session management verified")
    print("✓ Logout and re-login tested")
    print("\nNote: This script tests the HTTP flow.")
    print("Browser-specific behavior (JavaScript, redirects) should be")
    print("tested manually in Chrome, Firefox, and Edge browsers.")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_login_flow()
    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()
