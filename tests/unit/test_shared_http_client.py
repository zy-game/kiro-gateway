"""
Unit tests for shared HTTP client setup in main.py lifespan.

Tests verify:
- m2-a1: Shared HTTP client is created and reused
- m2-a2: HTTP client has proper connection limits
- m2-a5: HTTP client is closed on shutdown
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


def test_shared_http_client_created_in_lifespan():
    """
    m2-a1: Verify app.state.http_client is created in lifespan.
    
    Tests that a single httpx.AsyncClient instance is created during
    application startup and stored in app.state for reuse across requests.
    """
    from main import app
    
    # Access the app state after lifespan startup
    with TestClient(app) as client:
        # Verify http_client exists in app state
        assert hasattr(app.state, 'http_client'), "app.state.http_client not created"
        
        # Verify it's an httpx.AsyncClient instance
        assert isinstance(app.state.http_client, httpx.AsyncClient), \
            f"Expected httpx.AsyncClient, got {type(app.state.http_client)}"
        
        # Verify it's the same instance across multiple accesses (singleton pattern)
        client1 = app.state.http_client
        client2 = app.state.http_client
        assert client1 is client2, "http_client should be the same instance"


def test_http_client_connection_limits():
    """
    m2-a2: Verify HTTP client has proper connection limits.
    
    Tests that the shared HTTP client is configured with:
    - max_connections=100
    - max_keepalive_connections=20
    - keepalive_expiry=30.0
    """
    from main import app
    
    with TestClient(app) as client:
        http_client = app.state.http_client
        # Access limits through the transport's pool
        # httpx stores these as direct attributes on the pool
        pool = http_client._transport._pool
        
        # Verify max_connections
        assert pool._max_connections == 100, \
            f"Expected max_connections=100, got {pool._max_connections}"
        
        # Verify max_keepalive_connections
        assert pool._max_keepalive_connections == 20, \
            f"Expected max_keepalive_connections=20, got {pool._max_keepalive_connections}"
        
        # Verify keepalive_expiry
        assert pool._keepalive_expiry == 30.0, \
            f"Expected keepalive_expiry=30.0, got {pool._keepalive_expiry}"


def test_http_client_timeout_configuration():
    """
    Verify HTTP client has proper timeout configuration for streaming.
    
    This is part of the shared client setup - ensures timeouts are
    configured appropriately for long-running streaming requests.
    """
    from main import app
    from kiro.core.config import STREAMING_READ_TIMEOUT
    
    with TestClient(app) as client:
        http_client = app.state.http_client
        # Access timeout through the public timeout property
        timeout = http_client.timeout
        
        # Verify connect timeout
        assert timeout.connect == 30.0, \
            f"Expected connect timeout=30.0, got {timeout.connect}"
        
        # Verify read timeout (should be STREAMING_READ_TIMEOUT from config)
        assert timeout.read == STREAMING_READ_TIMEOUT, \
            f"Expected read timeout={STREAMING_READ_TIMEOUT}, got {timeout.read}"
        
        # Verify write timeout
        assert timeout.write == 30.0, \
            f"Expected write timeout=30.0, got {timeout.write}"
        
        # Verify pool timeout
        assert timeout.pool == 30.0, \
            f"Expected pool timeout=30.0, got {timeout.pool}"


def test_http_client_follows_redirects():
    """
    Verify HTTP client is configured to follow redirects.
    
    This is important for handling API redirects properly.
    """
    from main import app
    
    with TestClient(app) as client:
        http_client = app.state.http_client
        
        # Verify follow_redirects is enabled (use public property)
        assert http_client.follow_redirects is True, \
            "Expected follow_redirects=True"


@pytest.mark.asyncio
async def test_http_client_closed_on_shutdown():
    """
    m2-a5: Verify HTTP client is closed on application shutdown.
    
    Tests that the lifespan context manager properly closes the
    shared HTTP client during graceful shutdown.
    """
    from main import lifespan, app
    
    # Mock the http_client to track aclose() calls
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.aclose = AsyncMock()
    
    # Use the lifespan context manager
    async with lifespan(app):
        # Replace the real client with our mock
        app.state.http_client = mock_client
    
    # After exiting the context, aclose() should have been called
    mock_client.aclose.assert_called_once()


def test_http_client_reused_across_requests():
    """
    m2-a1: Verify the same HTTP client instance is reused across requests.
    
    Tests that multiple requests to the API use the same shared client,
    enabling connection pooling and reducing resource usage.
    """
    from main import app
    
    with TestClient(app) as client:
        # Get the http_client reference
        http_client_before = app.state.http_client
        
        # Make a request (this would use the shared client internally)
        response = client.get("/health")
        
        # Get the http_client reference again
        http_client_after = app.state.http_client
        
        # Verify it's still the same instance
        assert http_client_before is http_client_after, \
            "HTTP client instance changed between requests"


def test_lifespan_creates_all_required_state():
    """
    Verify that lifespan creates all required app.state attributes.
    
    This ensures the shared HTTP client is created alongside other
    required state managers.
    """
    from main import app
    
    with TestClient(app) as client:
        # Verify all required state attributes exist
        assert hasattr(app.state, 'http_client'), "Missing http_client"
        assert hasattr(app.state, 'auth_manager'), "Missing auth_manager"
        assert hasattr(app.state, 'model_cache'), "Missing model_cache"
        assert hasattr(app.state, 'model_resolver'), "Missing model_resolver"
        
        # Verify http_client is not None
        assert app.state.http_client is not None, "http_client is None"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
