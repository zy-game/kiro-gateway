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
        account_manager: Optional[Any] = None,
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
            account_manager: Optional AccountManager for cooldown integration
            **kwargs: Additional parameters
        
        Yields:
            bytes: SSE chunks in OpenAI format
        
        Raises:
            ValueError: If account config is invalid or messages is empty
            Exception: If API call fails
        """
        import httpx
        import json as json_module
        
        # 1. Validate messages array
        if not messages or len(messages) == 0:
            logger.error("OpenAI request failed: messages array is empty")
            raise ValueError("Messages array cannot be empty")
        
        # 2. Extract API key from account config
        api_key = account.config.get("api_key")
        if not api_key:
            raise ValueError("OpenAI account missing 'api_key' in config")
        
        # 3. Get base_url from config or use default
        base_url = account.config.get("base_url", self.BASE_URL)
        
        # 4. Build request payload
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
        
        # 5. Prepare request
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"OpenAI request: model={model}, stream={stream}")
        if tools:
            logger.debug(f"OpenAI request with {len(tools)} tools")
        
        # 6. Call OpenAI API
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
                        
                        # Try to parse error details from response
                        error_detail = error_msg
                        try:
                            error_json = json_module.loads(error_msg)
                            if "error" in error_json and "message" in error_json["error"]:
                                error_detail = error_json["error"]["message"]
                        except:
                            pass  # Use raw error_msg if parsing fails
                        
                        logger.error(f"OpenAI API error ({resp.status_code}): {error_detail}")
                        
                        # Map OpenAI errors to user-friendly messages
                        if resp.status_code == 429:
                            # Trigger account cooldown if account_manager is provided
                            if account_manager:
                                account_manager.mark_rate_limited(account.id)
                                logger.warning(f"Account {account.id} marked as rate-limited")
                            raise Exception("OpenAI rate limit exceeded. Please try again later.")
                        elif resp.status_code == 401:
                            raise Exception("OpenAI authentication failed. Check your API key.")
                        elif resp.status_code == 400:
                            # Include validation error details
                            raise Exception(f"OpenAI validation error: {error_detail}")
                        elif resp.status_code >= 500:
                            raise Exception(f"OpenAI server error ({resp.status_code}). Please try again later.")
                        else:
                            raise Exception(f"OpenAI API error ({resp.status_code}): {error_detail}")
                    
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
                            
                            # Try to parse error details from response
                            error_detail = error_msg
                            try:
                                error_json = json_module.loads(error_msg)
                                if "error" in error_json and "message" in error_json["error"]:
                                    error_detail = error_json["error"]["message"]
                            except:
                                pass  # Use raw error_msg if parsing fails
                            
                            logger.error(f"OpenAI API error ({resp.status_code}): {error_detail}")
                            
                            # Map OpenAI errors to user-friendly messages
                            if resp.status_code == 429:
                                # Trigger account cooldown if account_manager is provided
                                if account_manager:
                                    account_manager.mark_rate_limited(account.id)
                                    logger.warning(f"Account {account.id} marked as rate-limited")
                                raise Exception("OpenAI rate limit exceeded. Please try again later.")
                            elif resp.status_code == 401:
                                raise Exception("OpenAI authentication failed. Check your API key.")
                            elif resp.status_code == 400:
                                # Include validation error details
                                raise Exception(f"OpenAI validation error: {error_detail}")
                            elif resp.status_code >= 500:
                                raise Exception(f"OpenAI server error ({resp.status_code}). Please try again later.")
                            else:
                                raise Exception(f"OpenAI API error ({resp.status_code}): {error_detail}")
                        
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
        account_manager: Optional[Any] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """
        Send chat request to OpenAI API and return response in Anthropic format.
        
        This method converts between formats:
        1. Anthropic messages to OpenAI messages
        2. Call OpenAI API via chat_openai
        3. Convert OpenAI response to Anthropic format
        
        Args:
            account: Account with OpenAI API key in config.api_key
            model: Model name (e.g., "gpt-4")
            messages: Chat messages in Anthropic format
            stream: Whether to stream response (currently only stream=False supported)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            system: System prompt (Anthropic-specific)
            tools: Tool definitions in Anthropic format
            shared_client: Optional shared HTTP client
            account_manager: Optional AccountManager for cooldown integration
            **kwargs: Additional parameters
        
        Yields:
            bytes: Complete JSON response in Anthropic format (non-streaming only)
        
        Raises:
            ValueError: If account config is invalid
            NotImplementedError: If stream=True (streaming not yet implemented)
            Exception: If API call fails
        """
        import json
        
        logger.info(f"OpenAI chat_anthropic request: model={model}, stream={stream}")
        
        # 1. Convert Anthropic format to OpenAI format
        openai_messages = []
        
        # Add system message if provided
        if system:
            openai_messages.append({
                "role": "system",
                "content": system
            })
        
        # Convert Anthropic messages to OpenAI format
        for msg in messages:
            # Support both dict and AnthropicMessage (Pydantic model)
            role = msg.role if hasattr(msg, "role") else msg["role"]
            content = msg.content if hasattr(msg, "content") else msg.get("content", "")
            
            openai_msg = {"role": role}
            
            if isinstance(content, str):
                openai_msg["content"] = content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    # Support both dict and Pydantic content blocks
                    block_type = block.type if hasattr(block, "type") else block.get("type")
                    if block_type == "text":
                        block_text = block.text if hasattr(block, "text") else block.get("text", "")
                        text_parts.append(block_text)
                openai_msg["content"] = "".join(text_parts)
            else:
                openai_msg["content"] = str(content)
            
            openai_messages.append(openai_msg)
        
        logger.debug(f"Converted {len(messages)} Anthropic messages to {len(openai_messages)} OpenAI messages")
        
        if stream:
            # Streaming mode: call OpenAI with streaming, convert to Anthropic SSE
            from kiro.streaming.kiro import format_sse_event, generate_message_id
            
            message_id = generate_message_id()
            
            # Send message_start
            yield format_sse_event("message_start", {
                "type": "message_start",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": model,
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0}
                }
            }).encode("utf-8")
            
            # Send content_block_start
            yield format_sse_event("content_block_start", {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""}
            }).encode("utf-8")
            
            # Stream OpenAI chunks and convert to Anthropic deltas
            finish_reason = "end_turn"
            input_tokens = 0
            output_tokens = 0
            
            async for chunk in self.chat_openai(
                account=account,
                model=model,
                messages=openai_messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                shared_client=shared_client,
                account_manager=account_manager,
                **kwargs
            ):
                line = chunk.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    continue
                
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                
                # Extract usage if present
                if "usage" in data:
                    input_tokens = data["usage"].get("prompt_tokens", input_tokens)
                    output_tokens = data["usage"].get("completion_tokens", output_tokens)
                
                choices = data.get("choices", [])
                if not choices:
                    continue
                
                delta = choices[0].get("delta", {})
                fr = choices[0].get("finish_reason")
                if fr:
                    finish_reason = "end_turn" if fr == "stop" else fr
                
                content = delta.get("content")
                if content:
                    yield format_sse_event("content_block_delta", {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": content}
                    }).encode("utf-8")
            
            # Send content_block_stop
            yield format_sse_event("content_block_stop", {
                "type": "content_block_stop",
                "index": 0
            }).encode("utf-8")
            
            # Send message_delta
            yield format_sse_event("message_delta", {
                "type": "message_delta",
                "delta": {"stop_reason": finish_reason, "stop_sequence": None},
                "usage": {"output_tokens": output_tokens}
            }).encode("utf-8")
            
            # Send message_stop
            yield format_sse_event("message_stop", {
                "type": "message_stop"
            }).encode("utf-8")
            
            logger.info(f"OpenAI→Anthropic stream completed: input={input_tokens}, output={output_tokens}")
        
        else:
            # Non-streaming mode
            openai_response_chunks = []
            async for chunk in self.chat_openai(
                account=account,
                model=model,
                messages=openai_messages,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                shared_client=shared_client,
                account_manager=account_manager,
                **kwargs
            ):
                openai_response_chunks.append(chunk)
            
            openai_response_bytes = b"".join(openai_response_chunks)
            openai_response = json.loads(openai_response_bytes.decode("utf-8"))
            
            logger.debug(f"Received OpenAI response: {openai_response.get('id')}")
            
            choice = openai_response.get("choices", [{}])[0]
            message = choice.get("message", {})
            
            anthropic_response = {
                "id": openai_response.get("id", ""),
                "type": "message",
                "role": message.get("role", "assistant"),
                "model": openai_response.get("model", model),
                "content": [
                    {
                        "type": "text",
                        "text": message.get("content", "")
                    }
                ],
                "stop_reason": choice.get("finish_reason", "end_turn"),
                "usage": {
                    "input_tokens": openai_response.get("usage", {}).get("prompt_tokens", 0),
                    "output_tokens": openai_response.get("usage", {}).get("completion_tokens", 0)
                }
            }
            
            logger.info(f"Converted OpenAI response to Anthropic format")
            yield json.dumps(anthropic_response).encode("utf-8")
