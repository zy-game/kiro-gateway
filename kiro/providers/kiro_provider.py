# -*- coding: utf-8 -*-
"""
Kiro provider for Kiro Gateway.

Implements BaseProvider interface for Kiro (Amazon Q Developer) API.
"""

import json
import time
from typing import AsyncIterator, Dict, List, Any, Optional, Tuple

from loguru import logger

from kiro.core.auth import Account, AccountManager
from kiro.core.cache import ModelInfoCache
from kiro.providers.base import BaseProvider


class KiroProvider(BaseProvider):
    """
    Provider for Kiro (Amazon Q Developer) API.
    
    Handles all Kiro-specific logic including:
    - Format conversion (OpenAI/Anthropic to Kiro)
    - API calls to Kiro
    - Response streaming
    - Truncation recovery
    - Error handling
    """
    
    def __init__(self, auth_manager: AccountManager, model_cache: ModelInfoCache):
        """
        Initialize Kiro provider.
        
        Args:
            auth_manager: Account manager for authentication
            model_cache: Model info cache for model metadata
        """
        super().__init__("kiro")
        self.auth_manager = auth_manager
        self.model_cache = model_cache
    
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
        Send chat request to Kiro API and return OpenAI format.
        
        This method:
        1. Converts OpenAI messages to Anthropic format
        2. Calls chat_anthropic()
        3. Converts Anthropic SSE to OpenAI SSE
        
        Args:
            account: Account with Kiro credentials
            model: Model name
            messages: Chat messages in OpenAI format
            stream: Whether to stream
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            tools: Tool definitions in OpenAI format
            **kwargs: Additional parameters
        
        Yields:
            bytes: SSE chunks in OpenAI format
        """
        from kiro.models.api import AnthropicMessage, AnthropicMessagesRequest
        
        # Convert OpenAI messages to Anthropic format
        anthropic_messages = []
        system_prompt = None
        
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content", "")
            else:
                role = msg.role
                content = msg.content
            
            if role == "system":
                system_prompt = content
            else:
                anthropic_messages.append(
                    AnthropicMessage(role=role, content=content)
                )
        
        # Call chat_anthropic() to get Anthropic SSE
        if stream:
            # Streaming mode: convert Anthropic SSE to OpenAI SSE
            async for chunk in self.chat_anthropic(
                account=account,
                model=model,
                messages=anthropic_messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
                system=system_prompt,
                tools=tools,
                **kwargs
            ):
                # Convert Anthropic SSE to OpenAI SSE
                openai_chunk = self._convert_anthropic_sse_to_openai(chunk, model)
                if openai_chunk:
                    yield openai_chunk
        else:
            # Non-streaming mode: collect response and convert
            chunks = []
            async for chunk in self.chat_anthropic(
                account=account,
                model=model,
                messages=anthropic_messages,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
                system=system_prompt,
                tools=tools,
                **kwargs
            ):
                chunks.append(chunk)
            
            # Parse Anthropic response
            response_data = json.loads(b"".join(chunks).decode("utf-8"))
            
            # Convert to OpenAI format
            content_text = ""
            if response_data.get("content"):
                for block in response_data["content"]:
                    if block.get("type") == "text":
                        content_text += block.get("text", "")
            
            openai_response = {
                "id": response_data.get("id", f"chatcmpl-{int(time.time())}"),
                "object": "chat.completion",
                "created": int(time.time()),
                "model": response_data.get("model", model),
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content_text
                    },
                    "finish_reason": response_data.get("stop_reason", "stop")
                }],
                "usage": response_data.get("usage", {})
            }
            
            yield json.dumps(openai_response).encode('utf-8')
    
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
        Send chat request to Kiro API and return Anthropic format.
        
        This is the core method that:
        1. Applies truncation recovery
        2. Converts Anthropic messages to Kiro format
        3. Calls Kiro API
        4. Streams response in Anthropic SSE format
        
        Args:
            account: Account with Kiro credentials
            model: Model name
            messages: Chat messages in Anthropic format
            stream: Whether to stream
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            system: System prompt
            tools: Tool definitions in Anthropic format
            **kwargs: Additional parameters
        
        Yields:
            bytes: SSE chunks in Anthropic format
        """
        from kiro.converters.kiro import anthropic_to_kiro
        from kiro.streaming.kiro import stream_kiro_to_anthropic, collect_anthropic_response
        from kiro.core.http_client import KiroHttpClient
        from kiro.utils_pkg.helpers import generate_conversation_id
        from kiro.models.api import AnthropicMessagesRequest, AnthropicMessage
        
        # Apply truncation recovery
        modified_messages, tool_results_modified, content_notices_added = self._apply_truncation_recovery(messages)
        
        if tool_results_modified > 0 or content_notices_added > 0:
            logger.info(f"Truncation recovery: modified {tool_results_modified} tool_result(s), added {content_notices_added} content notice(s)")
            messages = modified_messages
        
        # Create Anthropic request object for conversion
        request_data = AnthropicMessagesRequest(
            model=model,
            messages=messages,
            max_tokens=max_tokens or 4096,
            temperature=temperature,
            stream=stream,
            system=system,
            tools=tools
        )
        
        # Generate conversation ID
        conversation_id = generate_conversation_id()
        
        # Get profileArn from account config
        profile_arn = account.config.get("profileArn") or account.config.get("profile_arn") or ""
        
        # Convert to Kiro format
        try:
            kiro_payload = anthropic_to_kiro(
                request_data,
                conversation_id,
                profile_arn
            )
        except ValueError as e:
            logger.error(f"Conversion error: {e}")
            raise Exception(f"Invalid request: {e}")
        
        # Build Kiro API URL
        region = account.config.get("region", "us-east-1")
        url = f"https://q.{region}.amazonaws.com/generateAssistantResponse"
        logger.debug(f"Kiro API URL: {url}")
        
        # Create HTTP client
        http_client = KiroHttpClient(self.auth_manager, account, shared_client=None)
        
        # Prepare messages for tokenizer
        messages_for_tokenizer = [msg.model_dump() if hasattr(msg, 'model_dump') else msg for msg in messages]
        tools_for_tokenizer = [tool.model_dump() if hasattr(tool, 'model_dump') else tool for tool in tools] if tools else None
        
        try:
            # Call Kiro API
            response = await http_client.request_with_retry(
                "POST",
                url,
                kiro_payload,
                stream=True
            )
            
            if response.status_code != 200:
                try:
                    error_content = await response.aread()
                except Exception:
                    error_content = b"Unknown error"
                
                await http_client.close()
                error_text = error_content.decode('utf-8', errors='replace')
                
                # Try to parse and enhance error message
                error_message = error_text
                try:
                    error_json = json.loads(error_text)
                    from kiro.kiro_errors import enhance_kiro_error
                    error_info = enhance_kiro_error(error_json)
                    error_message = error_info.user_message
                    logger.debug(f"Original Kiro error: {error_info.original_message} (reason: {error_info.reason})")
                except (json.JSONDecodeError, KeyError, ImportError):
                    pass
                
                logger.warning(f"Kiro API error ({response.status_code}): {error_message[:100]}")
                raise Exception(f"Kiro API error ({response.status_code}): {error_message}")
            
            # Stream response
            if stream:
                async for chunk in stream_kiro_to_anthropic(
                    response,
                    model,
                    self.model_cache,
                    self.auth_manager,
                    account,
                    request_messages=messages_for_tokenizer
                ):
                    yield chunk
            else:
                # Non-streaming: collect full response
                result = await collect_anthropic_response(
                    response,
                    model,
                    self.model_cache,
                    self.auth_manager,
                    request_messages=messages_for_tokenizer
                )
                yield json.dumps(result).encode('utf-8')
            
            await http_client.close()
        
        except Exception as e:
            await http_client.close()
            raise
    
    def _apply_truncation_recovery(
        self,
        messages: List[Any]
    ) -> Tuple[List[Any], int, int]:
        """
        Apply truncation recovery to messages.
        
        Args:
            messages: List of messages (Anthropic format)
        
        Returns:
            Tuple of (modified_messages, tool_results_modified, content_notices_added)
        """
        from kiro.utils_pkg.truncation_state import get_tool_truncation, get_content_truncation
        from kiro.utils_pkg.truncation_recovery import generate_truncation_tool_result, generate_truncation_user_message
        from kiro.models.api import AnthropicMessage
        
        modified_messages = []
        tool_results_modified = 0
        content_notices_added = 0
        
        for msg in messages:
            # Check if this is a user message with tool_result blocks
            if msg.role == "user" and msg.content and isinstance(msg.content, list):
                modified_content_blocks = []
                has_modifications = False
                
                for block in msg.content:
                    # Handle both dict and Pydantic objects
                    if isinstance(block, dict):
                        block_type = block.get("type")
                        tool_use_id = block.get("tool_use_id")
                        original_content = block.get("content", "")
                    elif hasattr(block, "type"):
                        block_type = block.type
                        tool_use_id = getattr(block, "tool_use_id", None)
                        original_content = getattr(block, "content", "")
                    else:
                        modified_content_blocks.append(block)
                        continue
                    
                    if block_type == "tool_result" and tool_use_id:
                        truncation_info = get_tool_truncation(tool_use_id)
                        if truncation_info:
                            # Modify tool_result content
                            synthetic = generate_truncation_tool_result(
                                tool_name=truncation_info.tool_name,
                                tool_use_id=tool_use_id,
                                truncation_info=truncation_info.truncation_info
                            )
                            modified_content = f"{synthetic['content']}\n\n---\n\nOriginal tool result:\n{original_content}"
                            
                            # Create modified block
                            if isinstance(block, dict):
                                modified_block = block.copy()
                                modified_block["content"] = modified_content
                            else:
                                modified_block = block.model_copy(update={"content": modified_content})
                            
                            modified_content_blocks.append(modified_block)
                            tool_results_modified += 1
                            has_modifications = True
                            logger.debug(f"Modified tool_result for {tool_use_id} to include truncation notice")
                            continue
                    
                    modified_content_blocks.append(block)
                
                # Create new message if modifications were made
                if has_modifications:
                    modified_msg = msg.model_copy(update={"content": modified_content_blocks})
                    modified_messages.append(modified_msg)
                    continue
            
            # Check if this is an assistant message with truncated content
            if msg.role == "assistant" and msg.content:
                # Extract text content for hash check
                text_content = ""
                if isinstance(msg.content, str):
                    text_content = msg.content
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_content += block.get("text", "")
                
                if text_content:
                    truncation_info = get_content_truncation(text_content)
                    if truncation_info:
                        # Add this message first
                        modified_messages.append(msg)
                        # Then add synthetic user message
                        synthetic_user_msg = AnthropicMessage(
                            role="user",
                            content=[{"type": "text", "text": generate_truncation_user_message()}]
                        )
                        modified_messages.append(synthetic_user_msg)
                        content_notices_added += 1
                        logger.debug(f"Added truncation notice after assistant message (hash: {truncation_info.message_hash})")
                        continue
            
            modified_messages.append(msg)
        
        return modified_messages, tool_results_modified, content_notices_added
    
    def _convert_anthropic_sse_to_openai(self, chunk: bytes, model: str) -> Optional[bytes]:
        """
        Convert Anthropic SSE chunk to OpenAI SSE format.
        
        Args:
            chunk: Anthropic SSE chunk
            model: Model name
        
        Returns:
            OpenAI SSE chunk or None
        """
        try:
            chunk_str = chunk.decode('utf-8')
            
            # Parse Anthropic SSE format
            if not chunk_str.startswith('event: '):
                return None
            
            lines = chunk_str.strip().split('\n')
            event_type = None
            data = None
            
            for line in lines:
                if line.startswith('event: '):
                    event_type = line[7:]
                elif line.startswith('data: '):
                    data = json.loads(line[6:])
            
            if not event_type or not data:
                return None
            
            # Convert based on event type
            if event_type == "content_block_delta":
                # Extract text delta
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    openai_data = {
                        "id": f"chatcmpl-{int(time.time())}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": text},
                            "finish_reason": None
                        }]
                    }
                    return f"data: {json.dumps(openai_data)}\n\n".encode('utf-8')
            
            elif event_type == "message_stop":
                # Send [DONE]
                return b"data: [DONE]\n\n"
            
            return None
        
        except Exception as e:
            logger.debug(f"Error converting Anthropic SSE to OpenAI: {e}")
            return None

