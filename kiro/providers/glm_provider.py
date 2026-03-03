# -*- coding: utf-8 -*-
"""
GLM (智谱AI) provider for Kiro Gateway.

Implements BaseProvider interface for GLM API.
"""

import asyncio
from typing import AsyncIterator, Dict, List, Any, Optional

import httpx
from loguru import logger

from kiro.core.auth import Account
from kiro.providers.base import BaseProvider
from kiro.converters.glm import GLMConverter


class GLMProvider(BaseProvider):
    """
    Provider for GLM (智谱AI) API.
    
    Supports GLM-4 series models with streaming and tool calling.
    """
    
    BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    
    SUPPORTED_MODELS = [
        "glm-4-flash",
        "glm-4-plus",
        "glm-4-air",
        "glm-4-airx",
        "glm-4-long",
        "glm-4-flashx",
        "glm-4-0520",
        "glm-4",
        "glm-3-turbo"
    ]
    
    def __init__(self):
        """Initialize GLM provider."""
        super().__init__("glm")
    
    def get_supported_models(self) -> List[str]:
        """
        Get list of supported GLM models.
        
        Returns:
            List of model IDs
        """
        return self.SUPPORTED_MODELS.copy()
    
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
        Send chat request to GLM API and stream response in OpenAI format.
        
        Args:
            account: Account with GLM API key in config.api_key
            model: Model name (e.g., "glm-4-flash")
            messages: Chat messages in OpenAI format
            stream: Whether to stream response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tools: Tool definitions in OpenAI format
            **kwargs: Additional parameters
        
        Yields:
            bytes: SSE chunks in OpenAI format
        
        Raises:
            ValueError: If account config is invalid
            Exception: If API call fails
        """
        # 1. Extract API key from account config
        api_key = account.config.get("api_key")
        if not api_key:
            raise ValueError("GLM account missing 'api_key' in config")
        
        # 2. Convert request to GLM format
        glm_data = GLMConverter.convert_to_glm_format(
            messages=messages,
            model=model,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            **kwargs
        )
        
        # 3. Prepare request
        url = f"{self.BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"GLM request: model={model}, stream={stream}")
        if tools:
            logger.debug(f"GLM request with {len(tools)} tools")
        
        # 4. Call GLM API
        has_received_data = False
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", url, json=glm_data, headers=headers) as resp:
                    # Check response status
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        error_msg = error_text.decode("utf-8", errors="ignore")
                        logger.error(f"GLM API error ({resp.status_code}): {error_msg}")
                        
                        # Map GLM errors to user-friendly messages
                        if resp.status_code == 429:
                            raise Exception("GLM rate limit exceeded. Please try again later.")
                        elif resp.status_code == 401:
                            raise Exception("GLM authentication failed. Check your API key.")
                        elif resp.status_code >= 500:
                            raise Exception(f"GLM server error ({resp.status_code}). Please try again later.")
                        else:
                            raise Exception(f"GLM API error ({resp.status_code}): {error_msg}")
                    
                    logger.debug(f"GLM API response status: {resp.status_code}")
                    
                    # 5. Stream response and convert to OpenAI format
                    if stream:
                        chunk_count = 0
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            
                            has_received_data = True
                            chunk_count += 1
                            
                            # Convert GLM chunk to OpenAI format
                            openai_chunk = GLMConverter.convert_glm_chunk_to_openai(line)
                            if openai_chunk:
                                yield openai_chunk.encode("utf-8")
                        
                        if not has_received_data:
                            logger.error("GLM stream completed without receiving any data")
                            raise Exception("GLM API returned empty response")
                        
                        logger.info(f"GLM stream completed: {chunk_count} chunks")
                    else:
                        # Non-streaming mode
                        response_data = await resp.aread()
                        has_received_data = True
                        yield response_data
                        logger.info("GLM complete response returned")
        
        except httpx.TimeoutException:
            logger.error(f"GLM request timeout for account {account.id}")
            raise Exception("GLM request timeout. Please try again.")
        except httpx.ConnectError as e:
            logger.error(f"GLM connection error: {e}")
            raise Exception("Failed to connect to GLM API. Check your network connection.")
        except Exception as e:
            # Don't log twice if we already logged above
            if "GLM API error" not in str(e) and "GLM rate limit" not in str(e):
                logger.error(f"GLM request error for account {account.id}: {e}")
            raise
