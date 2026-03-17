"""
Unit tests for OpenAIProvider.chat_openai method (non-streaming mode).

Tests verify:
- API key extraction from account.config
- base_url configuration (default and custom)
- Request payload construction
- HTTP request handling
- Response format
- Error handling
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from kiro.providers.openai_provider import OpenAIProvider
from kiro.core.auth import Account


@pytest.mark.asyncio
async def test_chat_openai_basic_non_streaming():
    """
    Test basic chat completion in non-streaming mode.
    
    Verifies:
    - API key is extracted from account.config
    - Request is sent to correct endpoint
    - Response is returned as bytes
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-api-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock response
    mock_response_data = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-3.5-turbo",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Hello! How can I help you?"
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aread = AsyncMock(return_value=json.dumps(mock_response_data).encode())
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call chat_openai
    chunks = []
    async for chunk in provider.chat_openai(
        account=account,
        model="gpt-3.5-turbo",
        messages=messages,
        stream=False,
        shared_client=mock_client
    ):
        chunks.append(chunk)
    
    # Verify response
    assert len(chunks) == 1, "Should return single chunk in non-streaming mode"
    response_data = json.loads(chunks[0].decode())
    assert response_data["choices"][0]["message"]["content"] == "Hello! How can I help you?"
    
    # Verify HTTP request was made correctly
    mock_client.stream.assert_called_once()
    call_args = mock_client.stream.call_args
    assert call_args[0][0] == "POST"
    assert call_args[0][1].endswith("/chat/completions")
    assert call_args[1]["headers"]["Authorization"] == "Bearer test-api-key"


@pytest.mark.asyncio
async def test_chat_openai_missing_api_key():
    """
    Test that missing API key raises ValueError.
    
    Verifies error handling when account.config lacks api_key.
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={},  # Missing api_key
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="api_key"):
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False
        ):
            pass


@pytest.mark.asyncio
async def test_chat_openai_custom_base_url():
    """
    Test that custom base_url is used when provided in account.config.
    
    Verifies support for third-party relay services.
    """
    provider = OpenAIProvider()
    
    custom_base_url = "https://api.relay-service.com/v1"
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={
            "api_key": "test-api-key",
            "base_url": custom_base_url
        },
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock response
    mock_response_data = {"choices": [{"message": {"content": "Hi"}}]}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aread = AsyncMock(return_value=json.dumps(mock_response_data).encode())
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call chat_openai
    async for _ in provider.chat_openai(
        account=account,
        model="gpt-3.5-turbo",
        messages=messages,
        stream=False,
        shared_client=mock_client
    ):
        pass
    
    # Verify custom base_url was used
    call_args = mock_client.stream.call_args
    assert call_args[0][1] == f"{custom_base_url}/chat/completions"


@pytest.mark.asyncio
async def test_chat_openai_default_base_url():
    """
    Test that default OpenAI base_url is used when not provided.
    
    Verifies fallback to official API endpoint.
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-api-key"},  # No base_url
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock response
    mock_response_data = {"choices": [{"message": {"content": "Hi"}}]}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aread = AsyncMock(return_value=json.dumps(mock_response_data).encode())
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call chat_openai
    async for _ in provider.chat_openai(
        account=account,
        model="gpt-3.5-turbo",
        messages=messages,
        stream=False,
        shared_client=mock_client
    ):
        pass
    
    # Verify default base_url was used
    call_args = mock_client.stream.call_args
    assert call_args[0][1] == "https://api.openai.com/v1/chat/completions"


@pytest.mark.asyncio
async def test_chat_openai_with_temperature_and_max_tokens():
    """
    Test that temperature and max_tokens parameters are passed correctly.
    
    Verifies parameter handling in request payload.
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-api-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Mock response
    mock_response_data = {"choices": [{"message": {"content": "Hi"}}]}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aread = AsyncMock(return_value=json.dumps(mock_response_data).encode())
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call chat_openai with parameters
    async for _ in provider.chat_openai(
        account=account,
        model="gpt-3.5-turbo",
        messages=messages,
        stream=False,
        temperature=0.7,
        max_tokens=100,
        shared_client=mock_client
    ):
        pass
    
    # Verify parameters were included in request
    call_args = mock_client.stream.call_args
    request_data = call_args[1]["json"]
    assert request_data["temperature"] == 0.7
    assert request_data["max_tokens"] == 100


@pytest.mark.asyncio
async def test_chat_openai_with_system_message():
    """
    Test that system messages are handled correctly.
    
    Verifies multi-turn conversation support.
    """
    provider = OpenAIProvider()
    
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-api-key"},
        limit=0,
        usage=0.0
    )
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"}
    ]
    
    # Mock response
    mock_response_data = {"choices": [{"message": {"content": "Hi"}}]}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aread = AsyncMock(return_value=json.dumps(mock_response_data).encode())
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Call chat_openai
    async for _ in provider.chat_openai(
        account=account,
        model="gpt-3.5-turbo",
        messages=messages,
        stream=False,
        shared_client=mock_client
    ):
        pass
    
    # Verify messages were passed correctly
    call_args = mock_client.stream.call_args
    request_data = call_args[1]["json"]
    assert len(request_data["messages"]) == 2
    assert request_data["messages"][0]["role"] == "system"
    assert request_data["messages"][1]["role"] == "user"


@pytest.mark.asyncio
async def test_chat_openai_http_401_error():
    """
    Test that 401 Unauthorized error is handled with user-friendly message.
    
    Verifies authentication error handling.
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
    
    # Should raise Exception with user-friendly message
    with pytest.raises(Exception, match="authentication failed"):
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client
        ):
            pass


@pytest.mark.asyncio
async def test_chat_openai_http_429_error():
    """
    Test that 429 Rate Limit error is handled with user-friendly message.
    
    Verifies rate limit error handling.
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
    
    # Should raise Exception with user-friendly message
    with pytest.raises(Exception, match="rate limit"):
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client
        ):
            pass


@pytest.mark.asyncio
async def test_chat_openai_http_500_error():
    """
    Test that 5xx server errors are handled with user-friendly message.
    
    Verifies server error handling.
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
    mock_response.aread = AsyncMock(return_value=b'Internal Server Error')
    
    mock_client = MagicMock()
    mock_stream_context = MagicMock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_stream_context)
    
    # Should raise Exception with user-friendly message
    with pytest.raises(Exception, match="server error"):
        async for _ in provider.chat_openai(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False,
            shared_client=mock_client
        ):
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
