"""
Unit tests for OpenAIProvider.chat_anthropic method (non-streaming mode).

Tests verify:
- Anthropic to OpenAI format conversion
- System prompt handling
- Content blocks conversion
- Response format conversion (OpenAI to Anthropic)
- Non-streaming mode only (stream=false)
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from kiro.providers.openai_provider import OpenAIProvider
from kiro.core.auth import Account


@pytest.mark.asyncio
async def test_chat_anthropic_basic_non_streaming():
    """
    Test basic chat_anthropic in non-streaming mode.
    
    Verifies:
    - Anthropic messages are converted to OpenAI format
    - chat_openai is called internally
    - OpenAI response is converted to Anthropic format
    - Returns complete JSON response
    
    Fulfills: VAL-MSG-003
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
    
    # Anthropic format messages
    messages = [
        {"role": "user", "content": "Hello"}
    ]
    
    # Mock OpenAI response
    mock_openai_response = {
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
    
    # Mock chat_openai to return OpenAI response
    async def mock_chat_openai(*args, **kwargs):
        yield json.dumps(mock_openai_response).encode()
    
    with patch.object(provider, 'chat_openai', side_effect=mock_chat_openai):
        chunks = []
        async for chunk in provider.chat_anthropic(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False
        ):
            chunks.append(chunk)
    
    # Verify response
    assert len(chunks) == 1, "Should return single chunk in non-streaming mode"
    response_data = json.loads(chunks[0].decode())
    
    # Verify Anthropic format
    assert "id" in response_data
    assert "type" in response_data
    assert response_data["type"] == "message"
    assert "role" in response_data
    assert response_data["role"] == "assistant"
    assert "content" in response_data
    assert isinstance(response_data["content"], list)
    assert len(response_data["content"]) > 0
    assert response_data["content"][0]["type"] == "text"
    assert response_data["content"][0]["text"] == "Hello! How can I help you?"
    assert "usage" in response_data
    assert response_data["usage"]["input_tokens"] == 10
    assert response_data["usage"]["output_tokens"] == 20


@pytest.mark.asyncio
async def test_chat_anthropic_with_system_prompt():
    """
    Test chat_anthropic with system prompt.
    
    Verifies:
    - System prompt is converted to OpenAI system message
    - System prompt is prepended to messages array
    
    Fulfills: VAL-MSG-001 (partial - non-streaming part)
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
    
    # Anthropic format with system prompt
    system = "You are a helpful assistant."
    messages = [
        {"role": "user", "content": "Hello"}
    ]
    
    # Mock OpenAI response
    mock_openai_response = {
        "id": "chatcmpl-123",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Hi there!"
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20}
    }
    
    # Capture the arguments passed to chat_openai
    captured_args = {}
    
    async def mock_chat_openai(*args, **kwargs):
        captured_args.update(kwargs)
        yield json.dumps(mock_openai_response).encode()
    
    with patch.object(provider, 'chat_openai', side_effect=mock_chat_openai):
        async for _ in provider.chat_anthropic(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            system=system,
            stream=False
        ):
            pass
    
    # Verify system prompt was converted to OpenAI format
    converted_messages = captured_args.get("messages", [])
    assert len(converted_messages) == 2
    assert converted_messages[0]["role"] == "system"
    assert converted_messages[0]["content"] == system
    assert converted_messages[1]["role"] == "user"


@pytest.mark.asyncio
async def test_chat_anthropic_with_content_blocks():
    """
    Test chat_anthropic with content blocks.
    
    Verifies:
    - Content blocks (array format) are converted to string
    - Multiple content blocks are concatenated
    
    Fulfills: VAL-MSG-004
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
    
    # Anthropic format with content blocks
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": " world"}
            ]
        }
    ]
    
    # Mock OpenAI response
    mock_openai_response = {
        "id": "chatcmpl-123",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Hi!"
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    }
    
    # Capture the arguments passed to chat_openai
    captured_args = {}
    
    async def mock_chat_openai(*args, **kwargs):
        captured_args.update(kwargs)
        yield json.dumps(mock_openai_response).encode()
    
    with patch.object(provider, 'chat_openai', side_effect=mock_chat_openai):
        async for _ in provider.chat_anthropic(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False
        ):
            pass
    
    # Verify content blocks were converted to string
    converted_messages = captured_args.get("messages", [])
    assert len(converted_messages) == 1
    assert converted_messages[0]["role"] == "user"
    assert converted_messages[0]["content"] == "Hello world"


@pytest.mark.asyncio
async def test_chat_anthropic_with_string_content():
    """
    Test chat_anthropic with string content (not blocks).
    
    Verifies:
    - String content is passed through as-is
    - No conversion needed for simple string content
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
    
    # Anthropic format with string content
    messages = [
        {"role": "user", "content": "Simple string message"}
    ]
    
    # Mock OpenAI response
    mock_openai_response = {
        "id": "chatcmpl-123",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Response"
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    }
    
    # Capture the arguments passed to chat_openai
    captured_args = {}
    
    async def mock_chat_openai(*args, **kwargs):
        captured_args.update(kwargs)
        yield json.dumps(mock_openai_response).encode()
    
    with patch.object(provider, 'chat_openai', side_effect=mock_chat_openai):
        async for _ in provider.chat_anthropic(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False
        ):
            pass
    
    # Verify string content was passed through
    converted_messages = captured_args.get("messages", [])
    assert len(converted_messages) == 1
    assert converted_messages[0]["content"] == "Simple string message"


@pytest.mark.asyncio
async def test_chat_anthropic_response_format():
    """
    Test that response is in correct Anthropic format.
    
    Verifies:
    - Response has required Anthropic fields
    - Content is array of content blocks
    - Usage information is included
    - Stop reason is included
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
    
    messages = [{"role": "user", "content": "Test"}]
    
    # Mock OpenAI response
    mock_openai_response = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-3.5-turbo",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Test response"
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 10,
            "total_tokens": 15
        }
    }
    
    async def mock_chat_openai(*args, **kwargs):
        yield json.dumps(mock_openai_response).encode()
    
    with patch.object(provider, 'chat_openai', side_effect=mock_chat_openai):
        chunks = []
        async for chunk in provider.chat_anthropic(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False
        ):
            chunks.append(chunk)
    
    response_data = json.loads(chunks[0].decode())
    
    # Verify Anthropic response format
    assert response_data["id"] == "chatcmpl-123"
    assert response_data["type"] == "message"
    assert response_data["role"] == "assistant"
    assert response_data["model"] == "gpt-3.5-turbo"
    assert response_data["stop_reason"] == "stop"
    
    # Verify content array
    assert isinstance(response_data["content"], list)
    assert len(response_data["content"]) == 1
    assert response_data["content"][0]["type"] == "text"
    assert response_data["content"][0]["text"] == "Test response"
    
    # Verify usage
    assert response_data["usage"]["input_tokens"] == 5
    assert response_data["usage"]["output_tokens"] == 10


@pytest.mark.asyncio
async def test_chat_anthropic_multi_turn_conversation():
    """
    Test chat_anthropic with multi-turn conversation.
    
    Verifies:
    - Multiple messages are converted correctly
    - Message order is preserved
    - Both user and assistant messages are handled
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
    
    # Multi-turn conversation
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"}
    ]
    
    # Mock OpenAI response
    mock_openai_response = {
        "id": "chatcmpl-123",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "I'm doing well!"
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
    }
    
    # Capture the arguments passed to chat_openai
    captured_args = {}
    
    async def mock_chat_openai(*args, **kwargs):
        captured_args.update(kwargs)
        yield json.dumps(mock_openai_response).encode()
    
    with patch.object(provider, 'chat_openai', side_effect=mock_chat_openai):
        async for _ in provider.chat_anthropic(
            account=account,
            model="gpt-3.5-turbo",
            messages=messages,
            stream=False
        ):
            pass
    
    # Verify all messages were converted
    converted_messages = captured_args.get("messages", [])
    assert len(converted_messages) == 3
    assert converted_messages[0]["role"] == "user"
    assert converted_messages[1]["role"] == "assistant"
    assert converted_messages[2]["role"] == "user"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
