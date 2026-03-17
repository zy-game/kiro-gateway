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
            ValueError: If account config is invalid
            Exception: If API call fails
        """
        import httpx
        
        # 1. Extract API key from account config
        api_key = account.config.get("api_key")
        if not api_key:
            raise ValueError("OpenAI account missing 'api_key' in config")
        
        # 2. Get base_url from config or use default
        base_url = account.config.get("base_url", self.BASE_URL)
        
        # 3. Build request payload
        request_data = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        # Add optional parameters
        if temperature is not None:
            request_data["temperature"] = temperature
        if max_tokens is not None:
            request_data["max_tokens"] = max_tokens
        if tools is not None:
            request_data["tools"] = tools
        
        # Add any additional kwargs
        request_data.update(kwargs)
        
        # 4. Prepare request
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"OpenAI request: model={model}, stream={stream}")
        if tools:
            logger.debug(f"OpenAI request with {len(tools)} tools")
        
        # 5. Call OpenAI API
        has_received_data = False
        
        try:
            # Use shared client if provided, otherwise create a new one
            if shared_client:
                # Use shared client (no context manager needed, it's managed by app lifespan)
                async with shared_client.stream("POST", url, json=request_data, headers=headers) as resp:
                    # Check response status
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        error_msg = error_text.decode("utf-8", errors="ignore")
                        logger.error(f"OpenAI API error ({resp.status_code}): {error_msg}")
                        
                        # Map OpenAI errors to user-friendly messages
                        if resp.status_code == 429:
                            raise Exception("OpenAI rate limit exceeded. Please try again later.")
                        elif resp.status_code == 401:
                            raise Exception("OpenAI authentication failed. Check your API key.")
                        elif resp.status_code >= 500:
                            raise Exception(f"OpenAI server error ({resp.status_code}). Please try again later.")
                        else:
                            raise Exception(f"OpenAI API error ({resp.status_code}): {error_msg}")
                    
                    logger.debug(f"OpenAI API response status: {resp.status_code}")
                    
                    # 6. Stream response
                    if stream:
                        chunk_count = 0
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            
                            has_received_data = True
                            chunk_count += 1
                            
                            # OpenAI returns SSE format: "data: {...}\n\n"
                            # Pass through as-is (already in OpenAI format)
                            yield line.encode("utf-8") + b"\n"
                        
                        if not has_received_data:
                            logger.error("OpenAI stream completed without receiving any data")
                            raise Exception("OpenAI API returned empty response")
                        
                        logger.info(f"OpenAI stream completed: {chunk_count} chunks")
                    else:
                        # Non-streaming mode
                        response_data = await resp.aread()
                        has_received_data = True
                        yield response_data
                        logger.info("OpenAI complete response returned")
            else:
                # Create new client for backward compatibility
                async with httpx.AsyncClient(timeout=300.0) as client:
                    async with client.stream("POST", url, json=request_data, headers=headers) as resp:
                        # Check response status
                        if resp.status_code != 200:
                            error_text = await resp.aread()
                            error_msg = error_text.decode("utf-8", errors="ignore")
                            logger.error(f"OpenAI API error ({resp.status_code}): {error_msg}")
                            
                            # Map OpenAI errors to user-friendly messages
                            if resp.status_code == 429:
                                raise Exception("OpenAI rate limit exceeded. Please try again later.")
                            elif resp.status_code == 401:
                                raise Exception("OpenAI authentication failed. Check your API key.")
                            elif resp.status_code >= 500:
                                raise Exception(f"OpenAI server error ({resp.status_code}). Please try again later.")
                            else:
                                raise Exception(f"OpenAI API error ({resp.status_code}): {error_msg}")
                        
                        logger.debug(f"OpenAI API response status: {resp.status_code}")
                        
                        # 6. Stream response
                        if stream:
                            chunk_count = 0
                            async for line in resp.aiter_lines():
                                if not line:
                                    continue
                                
                                has_received_data = True
                                chunk_count += 1
                                
                                # OpenAI returns SSE format: "data: {...}\n\n"
                                # Pass through as-is (already in OpenAI format)
                                yield line.encode("utf-8") + b"\n"
                            
                            if not has_received_data:
                                logger.error("OpenAI stream completed without receiving any data")
                                raise Exception("OpenAI API returned empty response")
                            
                            logger.info(f"OpenAI stream completed: {chunk_count} chunks")
                        else:
                            # Non-streaming mode
                            response_data = await resp.aread()
                            has_received_data = True
                            yield response_data
                            logger.info("OpenAI complete response returned")
        
        except httpx.TimeoutException:
            logger.error(f"OpenAI request timeout for account {account.id}")
            raise Exception("OpenAI request timeout. Please try again.")
        except httpx.ConnectError as e:
            logger.error(f"OpenAI connection error: {e}")
            raise Exception("Failed to connect to OpenAI API. Check your network connection.")
        except Exception as e:
            # Don't log twice if we already logged above
            if "OpenAI API error" not in str(e) and "OpenAI rate limit" not in str(e):
                logger.error(f"OpenAI request error for account {account.id}: {e}")
            raise
    
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
