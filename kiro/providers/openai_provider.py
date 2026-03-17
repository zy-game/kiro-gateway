# -*- coding: utf-8 -*-
"""
OpenAI provider for Kiro Gateway.

Implements BaseProvider interface for OpenAI API.
"""

from typing import AsyncIterator, Dict, List, Any, Optional

from loguru import logger

from kiro.core.auth import Account
from kiro.providers.base import BaseProvider


class OpenAIProvider(BaseProvider):
    """
    Provider for OpenAI API.
    
    Supports GPT-4, GPT-3.5-turbo, and other OpenAI models.
    This is a skeleton implementation with placeholder methods.
    """
    
    BASE_URL = "https://api.openai.com/v1"
    
    SUPPORTED_MODELS = [
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4-turbo-preview",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
        "o1-preview",
        "o1-mini"
    ]
    
    def __init__(self):
        """Initialize OpenAI provider."""
        super().__init__("openai")
    
    def get_supported_models(self, db_manager=None) -> List[str]:
        """
        Get list of supported OpenAI models.
        
        Priority:
        1. If db_manager provided, query from database
        2. Otherwise, return default hardcoded list
        
        Args:
            db_manager: Optional AccountManager instance for database queries
        
        Returns:
            List of model IDs
        """
        if db_manager:
            try:
                models = db_manager.get_models_by_provider("openai")
                if models:
                    return models
            except Exception as e:
                logger.warning(f"Failed to get models from database: {e}, using defaults")
        
        # Fallback to hardcoded list
        return self.SUPPORTED_MODELS.copy()
    
    async def chat_openai(
        self,
        account: Account,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        shared_client: Optional[Any] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """
        Send chat request to OpenAI API and stream response in OpenAI format.
        
        Args:
            account: Account with OpenAI API key in config.api_key
            model: Model name (e.g., "gpt-4")
            messages: Chat messages in OpenAI format
            stream: Whether to stream response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tools: Tool definitions in OpenAI format
            shared_client: Optional shared HTTP client
            **kwargs: Additional parameters
        
        Yields:
            bytes: SSE chunks in OpenAI format
        
        Raises:
            NotImplementedError: This is a skeleton implementation
        """
        raise NotImplementedError("chat_openai not yet implemented")
        # Make this an async generator by using yield (unreachable but satisfies type checker)
        yield b""  # pragma: no cover
    
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
        shared_client: Optional[Any] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """
        Send chat request to OpenAI API and stream response in Anthropic format.
        
        This method converts between formats:
        1. Anthropic messages to OpenAI messages (if needed)
        2. Call OpenAI API
        3. Convert OpenAI response to Anthropic SSE format
        
        Args:
            account: Account with OpenAI API key in config.api_key
            model: Model name (e.g., "gpt-4")
            messages: Chat messages in Anthropic format
            stream: Whether to stream response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            system: System prompt (Anthropic-specific)
            tools: Tool definitions in Anthropic format
            shared_client: Optional shared HTTP client
            **kwargs: Additional parameters
        
        Yields:
            bytes: SSE chunks in Anthropic format
        
        Raises:
            NotImplementedError: This is a skeleton implementation
        """
        raise NotImplementedError("chat_anthropic not yet implemented")
        # Make this an async generator by using yield (unreachable but satisfies type checker)
        yield b""  # pragma: no cover
