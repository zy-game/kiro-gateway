"""
Unit tests for OpenAIProvider skeleton.

Tests verify:
- Provider instantiation
- Inheritance from BaseProvider
- get_supported_models method
- Method signatures for chat_openai and chat_anthropic
"""

import pytest
from kiro.providers.openai_provider import OpenAIProvider
from kiro.providers.base import BaseProvider
from kiro.core.auth import Account


def test_provider_instantiation():
    """
    Verify OpenAIProvider can be instantiated without parameters.
    
    Following GLM pattern, __init__ should accept no parameters
    and initialize the provider with name "openai".
    """
    provider = OpenAIProvider()
    
    # Verify provider is created
    assert provider is not None, "Provider should be instantiated"
    
    # Verify provider name is set correctly
    assert provider.name == "openai", f"Expected name='openai', got '{provider.name}'"


def test_inherits_from_base_provider():
    """
    Verify OpenAIProvider inherits from BaseProvider.
    
    This ensures the provider follows the standard interface.
    """
    provider = OpenAIProvider()
    
    # Verify inheritance
    assert isinstance(provider, BaseProvider), \
        "OpenAIProvider should inherit from BaseProvider"


def test_get_supported_models():
    """
    Verify get_supported_models returns list of OpenAI model names.
    
    Should return a list containing common OpenAI models like:
    - gpt-4
    - gpt-4-turbo
    - gpt-3.5-turbo
    - gpt-4o
    """
    provider = OpenAIProvider()
    
    # Get supported models
    models = provider.get_supported_models()
    
    # Verify it returns a list
    assert isinstance(models, list), \
        f"Expected list, got {type(models)}"
    
    # Verify list is not empty
    assert len(models) > 0, "Should return at least one model"
    
    # Verify all items are strings
    assert all(isinstance(m, str) for m in models), \
        "All model names should be strings"
    
    # Verify some common OpenAI models are included
    assert "gpt-4" in models or any("gpt-4" in m for m in models), \
        "Should include gpt-4 or gpt-4 variant"
    assert "gpt-3.5-turbo" in models or any("gpt-3.5" in m for m in models), \
        "Should include gpt-3.5-turbo or variant"


def test_get_supported_models_with_db_manager():
    """
    Verify get_supported_models accepts optional db_manager parameter.
    
    Following GLM pattern, should accept db_manager but can return
    default list if db_manager is None or query fails.
    """
    provider = OpenAIProvider()
    
    # Should work with None
    models_without_db = provider.get_supported_models(db_manager=None)
    assert isinstance(models_without_db, list), "Should return list even without db_manager"
    
    # Should work with db_manager parameter (even if None)
    models_with_none = provider.get_supported_models(None)
    assert isinstance(models_with_none, list), "Should return list with None db_manager"


def test_chat_openai_method_exists():
    """
    Verify chat_openai method exists with correct signature.
    
    Method should be async and accept:
    - account: Account
    - model: str
    - messages: List[Dict[str, Any]]
    - stream: bool = True
    - temperature: Optional[float] = None
    - max_tokens: Optional[int] = None
    - tools: Optional[List[Dict[str, Any]]] = None
    - **kwargs
    
    For skeleton, it can raise NotImplementedError.
    """
    provider = OpenAIProvider()
    
    # Verify method exists
    assert hasattr(provider, 'chat_openai'), \
        "OpenAIProvider should have chat_openai method"
    
    # Verify it's callable
    assert callable(provider.chat_openai), \
        "chat_openai should be callable"
    
    # Verify it's an async method (coroutine function)
    import inspect
    assert inspect.iscoroutinefunction(provider.chat_openai) or \
           inspect.isasyncgenfunction(provider.chat_openai), \
        "chat_openai should be async"


def test_chat_anthropic_method_exists():
    """
    Verify chat_anthropic method exists with correct signature.
    
    Method should be async and accept:
    - account: Account
    - model: str
    - messages: List[Dict[str, Any]]
    - stream: bool = True
    - temperature: Optional[float] = None
    - max_tokens: Optional[int] = None
    - system: Optional[str] = None
    - tools: Optional[List[Dict[str, Any]]] = None
    - **kwargs
    
    For skeleton, it can raise NotImplementedError.
    """
    provider = OpenAIProvider()
    
    # Verify method exists
    assert hasattr(provider, 'chat_anthropic'), \
        "OpenAIProvider should have chat_anthropic method"
    
    # Verify it's callable
    assert callable(provider.chat_anthropic), \
        "chat_anthropic should be callable"
    
    # Verify it's an async method (coroutine function)
    import inspect
    assert inspect.iscoroutinefunction(provider.chat_anthropic) or \
           inspect.isasyncgenfunction(provider.chat_anthropic), \
        "chat_anthropic should be async"


@pytest.mark.asyncio
async def test_chat_openai_implemented():
    """
    Verify chat_openai is implemented and no longer raises NotImplementedError.
    
    The method is now fully implemented. Detailed tests are in test_openai_chat_basic.py.
    This test just verifies the method exists and is callable.
    """
    provider = OpenAIProvider()
    
    # Verify method exists and is callable
    assert hasattr(provider, 'chat_openai')
    assert callable(provider.chat_openai)
    
    # Note: Detailed implementation tests with mocks are in test_openai_chat_basic.py
    # to avoid making real HTTP requests in this basic structure test.


@pytest.mark.asyncio
async def test_chat_anthropic_raises_not_implemented():
    """
    Verify chat_anthropic raises NotImplementedError for skeleton.
    
    Since this is just the skeleton, the method should raise
    NotImplementedError when called.
    """
    provider = OpenAIProvider()
    
    # Create a mock account
    account = Account(
        id=1,
        type="openai",
        priority=0,
        config={"api_key": "test-key"},
        limit=0,
        usage=0.0
    )
    
    # Verify it raises NotImplementedError
    with pytest.raises(NotImplementedError):
        async for _ in provider.chat_anthropic(
            account=account,
            model="gpt-4",
            messages=[{"role": "user", "content": "test"}]
        ):
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
