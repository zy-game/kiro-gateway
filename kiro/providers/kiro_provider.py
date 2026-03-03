# -*- coding: utf-8 -*-
"""
Kiro provider for Kiro Gateway.

Wraps existing Kiro API logic into BaseProvider interface.
This is a placeholder that delegates to the existing implementation.
"""

from typing import AsyncIterator, Dict, List, Any, Optional

from loguru import logger

from kiro.core.auth import Account
from kiro.providers.base import BaseProvider


class KiroProvider(BaseProvider):
    """
    Provider for Kiro (Amazon Q Developer) API.
    
    This is a wrapper around the existing Kiro implementation.
    The actual logic remains in the route handlers for now.
    """
    
    def __init__(self):
        """Initialize Kiro provider."""
        super().__init__("kiro")
    
    def get_supported_models(self) -> List[str]:
        """
        Get list of supported Kiro models.
        
        Note: This returns a basic list. The actual model list
        is dynamically fetched from Kiro API and cached in ModelInfoCache.
        
        Returns:
            List of common model IDs
        """
        return [
            "auto",
            "claude-sonnet-4",
            "claude-haiku-4.5",
            "claude-sonnet-4.5",
            "claude-opus-4.5",
            "claude-3.7-sonnet",
        ]
    
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
        Send chat request to Kiro API.
        
        Note: This is a placeholder. The actual Kiro logic is still
        in the route handlers. This method should not be called directly.
        
        To integrate Kiro provider properly, we would need to refactor
        the existing route logic into this method. For now, we keep
        the existing implementation unchanged.
        
        Args:
            account: Account with Kiro credentials
            model: Model name
            messages: Chat messages
            stream: Whether to stream
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            tools: Tool definitions
            **kwargs: Additional parameters
        
        Yields:
            bytes: SSE chunks in OpenAI format
        
        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "KiroProvider.chat() is not implemented. "
            "Kiro requests are handled by existing route logic."
        )
