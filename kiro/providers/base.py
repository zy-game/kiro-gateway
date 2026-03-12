# -*- coding: utf-8 -*-
"""
Base provider interface for Kiro Gateway.

All providers must implement this interface to ensure consistent behavior.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Any, Optional

from kiro.core.auth import Account


class BaseProvider(ABC):
    """
    Abstract base class for AI providers.
    
    All providers must implement:
    - chat_openai(): Send chat request and return OpenAI-compatible SSE stream
    - chat_anthropic(): Send chat request and return Anthropic-compatible SSE stream
    - get_supported_models(): Return list of supported model names
    
    Providers handle:
    - API authentication
    - Request format conversion
    - Response format conversion to OpenAI/Anthropic SSE
    - Error handling
    """
    
    def __init__(self, name: str):
        """
        Initialize provider.
        
        Args:
            name: Provider name (e.g., "kiro", "glm")
        """
        self.name = name
    
    @abstractmethod
    async def chat_openai(
        self,
        account: Account,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """
        Send chat request and stream response in OpenAI format.
        
        This method must:
        1. Extract credentials from account.config
        2. Convert request to provider's format
        3. Call provider's API
        4. Convert response to OpenAI SSE format
        5. Handle errors gracefully
        
        Args:
            account: Account with credentials in config field
            model: Model name
            messages: Chat messages in OpenAI format
            stream: Whether to stream response
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            tools: Tool definitions in OpenAI format
            **kwargs: Additional provider-specific parameters
        
        Yields:
            bytes: SSE chunks in OpenAI format (b"data: {...}\\n\\n")
        
        Raises:
            ValueError: If account config is invalid
            Exception: If API call fails
        """
        pass
    
    @abstractmethod
    async def chat_anthropic(
        self,
        account: Account,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """
        Send chat request and stream response in Anthropic format.
        
        This method must:
        1. Extract credentials from account.config
        2. Convert request to provider's format
        3. Call provider's API
        4. Convert response to Anthropic SSE format
        5. Handle errors gracefully
        
        Args:
            account: Account with credentials in config field
            model: Model name
            messages: Chat messages in Anthropic format
            stream: Whether to stream response
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            system: System prompt (Anthropic-specific)
            tools: Tool definitions in Anthropic format
            **kwargs: Additional provider-specific parameters
        
        Yields:
            bytes: SSE chunks in Anthropic format (b"event: ...\\ndata: {...}\\n\\n")
        
        Raises:
            ValueError: If account config is invalid
            Exception: If API call fails
        """
        pass
    
    # Backward compatibility: chat() is an alias for chat_openai()
    async def chat(
        self,
        account: Account,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """
        Send chat request and stream response in OpenAI format.
        
        This is an alias for chat_openai() for backward compatibility.
        
        Args:
            account: Account with credentials in config field
            model: Model name
            messages: Chat messages in OpenAI format
            stream: Whether to stream response
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            tools: Tool definitions in OpenAI format
            **kwargs: Additional provider-specific parameters
        
        Yields:
            bytes: SSE chunks in OpenAI format (b"data: {...}\\n\\n")
        """
        async for chunk in self.chat_openai(
            account=account,
            model=model,
            messages=messages,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            **kwargs
        ):
            yield chunk
    
    @abstractmethod
    def get_supported_models(self, db_manager: Optional[Any] = None) -> List[str]:
        """
        Get list of supported model names.
        
        Priority:
        1. If db_manager provided, query from database
        2. Otherwise, return default hardcoded list
        
        Args:
            db_manager: Optional AccountManager instance for database queries
        
        Returns:
            List of model IDs (e.g., ["glm-4-flash", "glm-4-plus"])
        """
        pass
    
    def supports_model(self, model: str, db_manager: Optional[Any] = None) -> bool:
        """
        Check if this provider supports the given model.
        
        Default implementation checks exact match and prefix match.
        Override if custom logic is needed.
        
        Args:
            model: Model name to check
            db_manager: Optional AccountManager instance for database queries
        
        Returns:
            True if model is supported
        """
        supported = self.get_supported_models(db_manager)
        if model in supported:
            return True
        # Check prefix match (e.g., "glm-4-flash-20240101" matches "glm-4-flash")
        return any(model.startswith(m) for m in supported)
