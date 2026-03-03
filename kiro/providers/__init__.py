# -*- coding: utf-8 -*-
"""
Provider system for Kiro Gateway.

Supports multiple AI providers with unified interface:
- Kiro (Amazon Q Developer)
- GLM (智谱AI)
"""

from kiro.providers.base import BaseProvider
from kiro.providers.kiro_provider import KiroProvider
from kiro.providers.glm_provider import GLMProvider


def get_provider(provider_type: str) -> BaseProvider:
    """
    Get provider instance by type.
    
    Args:
        provider_type: Provider type ("kiro", "glm")
    
    Returns:
        Provider instance
    
    Raises:
        ValueError: If provider type is unknown
    """
    providers = {
        "kiro": KiroProvider,
        "glm": GLMProvider,
    }
    
    provider_class = providers.get(provider_type)
    if not provider_class:
        raise ValueError(f"Unknown provider type: {provider_type}")
    
    return provider_class()


__all__ = [
    "BaseProvider",
    "KiroProvider",
    "GLMProvider",
    "get_provider",
]
