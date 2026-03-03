# -*- coding: utf-8 -*-
"""
Provider router for Kiro Gateway.

Routes requests to appropriate providers based on model name.
"""

from typing import Tuple

from fastapi import HTTPException
from loguru import logger

from kiro.core.auth import Account, AccountManager
from kiro.providers import BaseProvider, get_provider


class ProviderRouter:
    """
    Routes requests to appropriate providers based on model name.
    
    Routing rules:
    - glm-* → GLM provider
    - claude-*, auto → Kiro provider (default)
    
    Also handles account selection for the chosen provider.
    """
    
    def __init__(self, account_manager: AccountManager):
        """
        Initialize router.
        
        Args:
            account_manager: Account manager for retrieving accounts
        """
        self.account_manager = account_manager
        # Cache provider instances
        self._provider_cache = {}
    
    def _get_provider_type(self, model: str) -> str:
        """
        Determine provider type from model name.
        
        Args:
            model: Model name
        
        Returns:
            Provider type ("kiro", "glm")
        """
        # GLM models
        if model.startswith("glm-"):
            return "glm"
        
        # Default to Kiro for all other models
        # (claude-*, auto, etc.)
        return "kiro"
    
    def _get_provider_instance(self, provider_type: str) -> BaseProvider:
        """
        Get or create provider instance.
        
        Args:
            provider_type: Provider type
        
        Returns:
            Provider instance
        """
        if provider_type not in self._provider_cache:
            self._provider_cache[provider_type] = get_provider(provider_type)
        return self._provider_cache[provider_type]
    
    async def route_request(self, model: str) -> Tuple[BaseProvider, Account]:
        """
        Route request to appropriate provider and get account.
        
        Args:
            model: Model name from request
        
        Returns:
            Tuple of (provider, account)
        
        Raises:
            HTTPException: 503 if no account available for provider
        """
        # 1. Determine provider type
        provider_type = self._get_provider_type(model)
        logger.debug(f"Model '{model}' routed to provider '{provider_type}'")
        
        # 2. Get provider instance
        try:
            provider = self._get_provider_instance(provider_type)
        except ValueError as e:
            logger.error(f"Failed to get provider: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Provider '{provider_type}' not available"
            )
        
        # 3. Get account for this provider type
        account = await self.account_manager.get_account_by_type(provider_type)
        if not account:
            logger.warning(f"No available account for provider '{provider_type}'")
            raise HTTPException(
                status_code=503,
                detail=f"No available {provider_type} account. Please add an account in admin panel."
            )
        
        logger.info(
            f"Request routed: model={model}, provider={provider_type}, "
            f"account_id={account.id}"
        )
        
        return provider, account
