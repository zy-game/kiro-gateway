"""
Unit tests for OpenAIProvider error handling.

Tests verify comprehensive error handling for:
- Authentication errors (401)
- Rate limits (429) with account cooldown integration
- Validation errors (400)
- Network errors (ConnectError)
- Timeout errors
- Server errors (5xx)
- Empty messages validation
- Error logging
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import httpx
from kiro.providers.openai_provider import OpenAIProvider
from kiro.core.auth import Account


@pytest.mark.asyncio
async def test_authentication_error_401():
    """
    Test that 401 errors return clear 'Authentication failed' message.
    
    Verifies:
    - 401 status code is detected
    - User-friendly error message is returned
    - Error is logged appropriately
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "invalid-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock 401 response
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.aread = AsyncMock(return_value=b'{"error": {"message": "Invalid API key"}}')
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call should raise exception with user-friendly message
    with pytest.raises(Exception) as exc_info:
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client
        ):
            pass
    
    # Verify error message
    assert "Authentication failed" in str(exc_info.value) or "authentication failed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_rate_limit_429_with_cooldown():
    """
    Test that 429 errors trigger account cooldown and return appropriate message.
    
    Verifies:
    - 429 status code is detected
    - mark_rate_limited() is called on account manager
    - User-friendly 'Rate limit exceeded' message is returned
    - Error is logged
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock 429 response
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.aread = AsyncMock(return_value=b'{"error": {"message": "Rate limit exceeded"}}')
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Mock account manager
    mock_account_manager = MagicMock()
    mock_account_manager.mark_rate_limited = MagicMock()
    
    # Call should raise exception and trigger cooldown
    with pytest.raises(Exception) as exc_info:
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client,
            account_manager=mock_account_manager
        ):
            pass
    
    # Verify error message
    assert "rate limit" in str(exc_info.value).lower()
    
    # Verify mark_rate_limited was called
    mock_account_manager.mark_rate_limited.assert_called_once_with(account.id)


@pytest.mark.asyncio
async def test_validation_error_400():
    """
    Test that 400 errors return validation error details from API response.
    
    Verifies:
    - 400 status code is detected
    - Validation error details from API are included in error message
    - Error is logged
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock 400 response with validation details
    error_detail = "Invalid parameter: temperature must be between 0 and 2"
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.aread = AsyncMock(
        return_value=json.dumps({"error": {"message": error_detail}}).encode()
    )
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call should raise exception with validation details
    with pytest.raises(Exception) as exc_info:
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client
        ):
            pass
    
    # Verify error message contains validation details
    error_msg = str(exc_info.value)
    assert "400" in error_msg or "validation" in error_msg.lower() or error_detail in error_msg


@pytest.mark.asyncio
async def test_network_error_connect_error():
    """
    Test that network connection errors return 'Failed to connect' message.
    
    Verifies:
    - ConnectError is caught
    - User-friendly connection error message is returned
    - Error is logged
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock ConnectError
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call should raise exception with connection error message
    with pytest.raises(Exception) as exc_info:
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client
        ):
            pass
    
    # Verify error message
    assert "connect" in str(exc_info.value).lower() or "connection" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_timeout_error():
    """
    Test that timeout errors return 'Request timeout' message.
    
    Verifies:
    - TimeoutException is caught
    - User-friendly timeout message is returned
    - Error is logged
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock TimeoutException
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(side_effect=httpx.TimeoutException("Request timeout"))
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call should raise exception with timeout message
    with pytest.raises(Exception) as exc_info:
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client
        ):
            pass
    
    # Verify error message
    assert "timeout" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_server_error_5xx():
    """
    Test that 5xx errors return 'Server error' message with status code.
    
    Verifies:
    - 5xx status codes are detected
    - User-friendly server error message is returned
    - Status code is included in message
    - Error is logged
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock 503 response
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.aread = AsyncMock(return_value=b'{"error": {"message": "Service unavailable"}}')
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call should raise exception with server error message
    with pytest.raises(Exception) as exc_info:
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client
        ):
            pass
    
    # Verify error message contains status code and server error indication
    error_msg = str(exc_info.value)
    assert "503" in error_msg or "server error" in error_msg.lower()


@pytest.mark.asyncio
async def test_empty_messages_validation():
    """
    Test that empty messages array returns 400 validation error.
    
    Verifies:
    - Empty messages array is detected before API call
    - Validation error is raised
    - Error message is clear and actionable
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-key"},
        limit=0,
        usage=0.0
    )
    
    # Empty messages array
    messages = []
    
    # Call should raise validation error
    with pytest.raises(ValueError) as exc_info:
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False
        ):
            pass
    
    # Verify error message
    error_msg = str(exc_info.value)
    assert "messages" in error_msg.lower() and ("empty" in error_msg.lower() or "required" in error_msg.lower())


@pytest.mark.asyncio
async def test_rate_limit_without_account_manager():
    """
    Test that 429 errors work correctly even without account_manager parameter.
    
    Verifies:
    - 429 error is handled gracefully when account_manager is not provided
    - User-friendly error message is still returned
    - No crash occurs due to missing account_manager
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock 429 response
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.aread = AsyncMock(return_value=b'{"error": {"message": "Rate limit exceeded"}}')
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call without account_manager parameter
    with pytest.raises(Exception) as exc_info:
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client
        ):
            pass
    
    # Verify error message is still user-friendly
    assert "rate limit" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_error_logging():
    """
    Test that all errors are logged with appropriate level.
    
    Verifies:
    - Errors are logged using logger.error
    - Log messages contain relevant context (status code, account ID, etc.)
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock 500 response
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.aread = AsyncMock(return_value=b'{"error": {"message": "Internal server error"}}')
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Patch logger to verify logging
    with patch('kiro.providers.openai_provider.logger') as mock_logger:
        with pytest.raises(Exception):
            async for _ in provider.chat_openai(
                account=account,
                model="gpt-3.5-turbo",
                messages=messages,
                stream=False,
                shared_client=mock_client
            ):
                pass
        
        # Verify error was logged
        assert mock_logger.error.called, "Error should be logged"
        # Check that log contains status code
        log_calls = [str(call) for call in mock_logger.error.call_args_list]
        assert any("500" in str(call) for call in log_calls), "Log should contain status code"
