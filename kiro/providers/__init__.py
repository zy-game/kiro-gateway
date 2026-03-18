# -*- coding: utf-8 -*-
"""
Provider system for Kiro Gateway.

Supports multiple AI providers with unified interface:
- Kiro (Amazon Q Developer)
- GLM (智谱AI)
"""

from typing import Optional

from kiro.providers.base import BaseProvider
from kiro.providers.kiro_provider import KiroProvider
from kiro.providers.glm_provider import GLMProvider
from kiro.providers.openai_provider import OpenAIProvider


def get_provider(provider_type: str, auth_manager=None, model_cache=None) -> BaseProvider:
    """
    Get provider instance by type.
    
    Args:
        provider_type: Provider type ("kiro", "glm", "openai")
        auth_manager: Account manager (required for Kiro provider)
        model_cache: Model info cache (required for Kiro provider)
    
    Returns:
        Provider instance
    
    Raises:
        ValueError: If provider type is unknown or required dependencies missing
    """
    if provider_type == "kiro":
        if not auth_manager or not model_cache:
            raise ValueError("KiroProvider requires auth_manager and model_cache")
        return KiroProvider(auth_manager, model_cache)
    elif provider_type == "glm":
        return GLMProvider()
    elif provider_type == "openai":
        return OpenAIProvider()
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


__all__ = [
    "BaseProvider",
    "KiroProvider",
    "GLMProvider",
    "OpenAIProvider",
    "get_provider",
]
