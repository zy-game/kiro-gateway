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
        "glm-4.7-flash",
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
    
    def get_supported_models(self, db_manager=None) -> List[str]:
        """
        Get list of supported GLM models.
        
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
                models = db_manager.get_models_by_provider("glm")
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
            # Use shared client if provided, otherwise create a new one
            if shared_client:
                # Use shared client (no context manager needed, it's managed by app lifespan)
                async with shared_client.stream("POST", url, json=glm_data, headers=headers) as resp:
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
            else:
                # Create new client for backward compatibility
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
        Send chat request to GLM API and stream response in Anthropic format.
        
        This method converts between formats:
        1. Anthropic messages to OpenAI messages (if needed)
        2. Call chat_openai() to get OpenAI SSE
        3. Convert OpenAI SSE to Anthropic SSE
        
        Args:
            account: Account with GLM API key in config.api_key
            model: Model name (e.g., "glm-4-flash")
            messages: Chat messages in Anthropic format
            stream: Whether to stream response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            system: System prompt (Anthropic-specific)
            tools: Tool definitions in Anthropic format
            **kwargs: Additional parameters
        
        Yields:
            bytes: SSE chunks in Anthropic format
        
        Raises:
            ValueError: If account config is invalid
            Exception: If API call fails
        """
        import json
        import time
        
        # Convert Anthropic messages to OpenAI format
        openai_messages = []
        
        # Add system message if provided
        if system:
            # Handle both string and list of content blocks
            if isinstance(system, str):
                openai_messages.append({"role": "system", "content": system})
            elif isinstance(system, list):
                # Extract text from content blocks
                system_text = ""
                for block in system:
                    if isinstance(block, dict) and block.get("type") == "text":
                        system_text += block.get("text", "")
                    elif hasattr(block, "type") and block.type == "text":
                        system_text += block.text
                if system_text:
                    openai_messages.append({"role": "system", "content": system_text})
            else:
                # Single content block object
                if hasattr(system, "text"):
                    openai_messages.append({"role": "system", "content": system.text})
                else:
                    openai_messages.append({"role": "system", "content": str(system)})
        
        # Convert Anthropic messages to OpenAI format
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
            else:
                # Pydantic model
                role = msg.role
                content = msg.content
            
            # Extract text content
            if isinstance(content, list):
                text_content = ""
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_content += block.get("text", "")
                    elif hasattr(block, "type") and block.type == "text":
                        text_content += block.text
                openai_messages.append({"role": role, "content": text_content})
            else:
                openai_messages.append({"role": role, "content": str(content)})
        
        # Call chat_openai() to get OpenAI SSE
        if stream:
            # Streaming mode: convert OpenAI SSE to Anthropic SSE
            message_id = f"msg_{int(time.time() * 1000)}"
            content_started = False
            final_usage = {"input_tokens": 0, "output_tokens": 0}
            
            async for chunk in self.chat_openai(
                account=account,
                model=model,
                messages=openai_messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                shared_client=shared_client,
                **kwargs
            ):
                # Parse OpenAI SSE chunk
                chunk_str = chunk.decode('utf-8')
                if not chunk_str.startswith('data: '):
                    continue
                
                data_str = chunk_str[6:].strip()
                if not data_str or data_str == '[DONE]':
                    continue
                
                try:
                    data = json.loads(data_str)
                    delta = data.get('choices', [{}])[0].get('delta', {})
                    content = delta.get('content', '')
                    
                    # Extract usage if present
                    if 'usage' in data:
                        usage = data['usage']
                        final_usage['input_tokens'] = usage.get('prompt_tokens', 0)
                        final_usage['output_tokens'] = usage.get('completion_tokens', 0)
                    
                    if content:
                        # Send message_start on first content
                        if not content_started:
                            yield f'event: message_start\ndata: {json.dumps({"type": "message_start", "message": {"id": message_id, "type": "message", "role": "assistant", "content": [], "model": model}})}\n\n'.encode('utf-8')
                            yield f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})}\n\n'.encode('utf-8')
                            content_started = True
                        
                        # Send content_block_delta
                        yield f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": content}})}\n\n'.encode('utf-8')
                
                except json.JSONDecodeError:
                    pass
            
            # Send closing events
            if content_started:
                yield f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": 0})}\n\n'.encode('utf-8')
            
            # Send message_delta with usage
            yield f'event: message_delta\ndata: {json.dumps({"type": "message_delta", "delta": {{"stop_reason": "end_turn"}}, "usage": final_usage})}\n\n'.encode('utf-8')
            
            yield f'event: message_stop\ndata: {json.dumps({"type": "message_stop"})}\n\n'.encode('utf-8')
        
        else:
            # Non-streaming mode: convert OpenAI response to Anthropic format
            chunks = []
            async for chunk in self.chat_openai(
                account=account,
                model=model,
                messages=openai_messages,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                shared_client=shared_client,
                **kwargs
            ):
                chunks.append(chunk)
            
            response_data = json.loads(b"".join(chunks).decode("utf-8"))
            
            # Convert OpenAI response to Anthropic format
            content_text = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            anthropic_response = {
                "id": f"msg_{int(time.time() * 1000)}",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": content_text}],
                "model": model,
                "stop_reason": "end_turn",
                "usage": response_data.get('usage', {})
            }
            
            yield json.dumps(anthropic_response).encode('utf-8')