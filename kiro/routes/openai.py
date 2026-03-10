# -*- coding: utf-8 -*-
"""
FastAPI routes for OpenAI and Anthropic compatible APIs.

Contains:
- OpenAI endpoints: /v1/models, /v1/chat/completions, /v1/responses
- Anthropic endpoints: /v1/messages

Supports multiple providers (Kiro, GLM) with automatic routing based on model name.
"""

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header, Security
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from loguru import logger
from pydantic import BaseModel, Field

from kiro.core.auth import AccountManager
from kiro.core.cache import ModelInfoCache
from kiro.core.provider_router import ProviderRouter
from kiro.models.api import (
    AnthropicMessagesRequest,
)


# --- Security schemes ---
# OpenAI: Authorization: Bearer
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

# Anthropic: x-api-key or Authorization: Bearer
anthropic_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)
auth_header = APIKeyHeader(name="Authorization", auto_error=False)


# --- Authentication functions ---
async def verify_api_key(
    authorization: Optional[str] = Depends(api_key_header),
    request: Request = None
) -> int:
    """
    Verify API key for OpenAI API against database.
    
    Args:
        authorization: Value from Authorization header
        request: FastAPI Request for accessing app.state
    
    Returns:
        API key ID if valid
    
    Raises:
        HTTPException: 401 if key is invalid or missing
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    
    if not token:
        logger.warning("Access attempt without API key (OpenAI API)")
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Invalid or missing API key. Use Authorization: Bearer header.",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key"
                }
            }
        )
    
    # Verify against database
    manager = request.app.state.auth_manager if request else None
    if manager:
        api_key = manager.get_api_key_by_token(token)
        if api_key:
            return api_key.id
    
    logger.warning("Access attempt with invalid API key (OpenAI endpoint)")
    raise HTTPException(
        status_code=401,
        detail={
            "error": {
                "message": "Invalid API key provided.",
                "type": "invalid_request_error",
                "code": "invalid_api_key"
            }
        }
    )


async def verify_anthropic_api_key(
    x_api_key: Optional[str] = Security(anthropic_api_key_header),
    authorization: Optional[str] = Security(auth_header),
    request: Request = None
) -> int:
    """
    Verify API key for Anthropic API against database.
    
    Supports two authentication methods:
    1. x-api-key header (Anthropic native)
    2. Authorization: Bearer header (for compatibility)
    
    Args:
        x_api_key: Value from x-api-key header
        authorization: Value from Authorization header
        request: FastAPI Request for accessing app.state
    
    Returns:
        API key ID if valid
    
    Raises:
        HTTPException: 401 if key is invalid or missing
    """
    # Check x-api-key first (Anthropic native)
    token = None
    if x_api_key:
        token = x_api_key
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    
    if not token:
        logger.warning("Access attempt without API key (Anthropic API).")
        raise HTTPException(
            status_code=401,
            detail={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": "Invalid or missing API key. Use x-api-key header or Authorization: Bearer."
                }
            }
        )
    
    # Verify against database and get API key object
    manager = request.app.state.auth_manager if request else None
    if manager:
        api_key = manager.get_api_key_by_token(token)
        if api_key:
            return api_key.id
    
    logger.warning("Access attempt with invalid API key (Anthropic endpoint)")
    raise HTTPException(
        status_code=401,
        detail={
            "type": "error",
            "error": {
                "type": "authentication_error",
                "message": "Invalid or missing API key. Use x-api-key header or Authorization: Bearer."
            }
        }
    )


# --- Pydantic Models ---
class ChatMessage(BaseModel):
    """Chat message in OpenAI format."""
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI chat completion request."""
    model: str
    messages: list
    stream: Optional[bool] = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[list] = None


# --- Router ---
router = APIRouter(tags=["API"])


# ==================== OpenAI Endpoints ====================

@router.get("/v1/models")
async def list_models(
    request: Request,
    api_key_id: int = Depends(verify_api_key)
):
    """
    List available models from all providers.
    
    Returns models from:
    - Kiro (dynamically fetched + hidden models)
    - GLM (static list)
    
    Returns:
        JSON response with model list in OpenAI format
    """
    logger.info("Request to /v1/models")
    
    model_resolver = request.app.state.model_resolver
    
    # Get all available models (Kiro + hidden + aliases)
    kiro_models = model_resolver.get_available_models()
    
    # Get GLM models
    from kiro.providers.glm_provider import GLMProvider
    glm_provider = GLMProvider()
    glm_models = glm_provider.get_supported_models()
    
    # Combine all models
    all_models = list(set(kiro_models + glm_models))
    all_models.sort()
    
    # Format as OpenAI model list
    models_data = [
        {
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "kiro-gateway"
        }
        for model_id in all_models
    ]
    
    logger.info(f"Returning {len(models_data)} models")
    
    return {
        "object": "list",
        "data": models_data
    }


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    request_data: ChatCompletionRequest,
    api_key_id: int = Depends(verify_api_key)
):
    """
    OpenAI-compatible chat completions endpoint with multi-provider support.
    
    Supports automatic routing:
    - GLM models (glm-*) → GLMProvider
    - Other models (claude-*, auto) → Kiro (via Anthropic endpoint conversion)
    
    Args:
        request: FastAPI Request
        request_data: Chat completion request
        api_key_id: Verified API key ID
    
    Returns:
        StreamingResponse for streaming mode
        JSONResponse for non-streaming mode
    """
    logger.info(
        f"Request to /v1/chat/completions (model={request_data.model}, "
        f"stream={request_data.stream})"
    )
    
    start_time = time.time()
    
    auth_manager: AccountManager = request.app.state.auth_manager
    
    # Initialize provider router
    model_cache: ModelInfoCache = request.app.state.model_cache
    provider_router = ProviderRouter(auth_manager, model_cache)
    
    try:
        # Route to appropriate provider and get account
        provider, account = await provider_router.route_request(request_data.model)
        
        logger.info(
            f"Routed to provider '{provider.name}' with account {account.email}"
        )
        
        # Use provider's chat_openai() method for all providers
        if request_data.stream:
            # Streaming response with logging wrapper
            output_content = []
            
            async def stream_with_logging():
                """Wrapper to collect output and log request."""
                nonlocal output_content
                try:
                    async for chunk in provider.chat_openai(
                        account=account,
                        model=request_data.model,
                        messages=request_data.messages,
                        stream=True,
                        temperature=request_data.temperature,
                        max_tokens=request_data.max_tokens,
                        tools=request_data.tools
                    ):
                        # Collect output content for token counting
                        try:
                            chunk_str = chunk.decode('utf-8')
                            
                            # Extract content from OpenAI SSE format
                            if chunk_str.startswith('data: ') and '[DONE]' not in chunk_str:
                                data = json.loads(chunk_str[6:])
                                delta = data.get('choices', [{}])[0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    output_content.append(content)
                            
                            # Extract content from Anthropic SSE format
                            elif 'event: content_block_delta' in chunk_str:
                                lines = chunk_str.split('\n')
                                for line in lines:
                                    if line.startswith('data: '):
                                        data = json.loads(line[6:])
                                        if data.get('type') == 'content_block_delta':
                                            text = data.get('delta', {}).get('text', '')
                                            if text:
                                                output_content.append(text)
                                                logger.debug(f"Anthropic: Collected {len(text)} chars")
                                                output_content.append(text)
                        except:
                            pass
                        yield chunk
                finally:
                    # Calculate tokens using tokenizer
                    from kiro.utils_pkg.tokenizer import count_message_tokens, count_tokens
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    # Calculate input tokens from request messages
                    input_tokens = count_message_tokens(
                        [{"role": msg.role, "content": msg.content} for msg in request_data.messages]
                    )
                    
                    # Calculate output tokens from collected content
                    output_text = ''.join(output_content)
                    output_tokens = count_tokens(output_text)
                    logger.info(f"OpenAI: {len(output_text)} chars, {output_tokens} tokens")
                    
                    try:
                        auth_manager.log_request(
                            api_key_id=api_key_id,
                            account_id=account.id,
                            model=request_data.model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            status="success",
                            channel="openai",
                            duration_ms=duration_ms
                        )
                    except Exception as log_error:
                        logger.error(f"Failed to log streaming request: {log_error}")
            
            return StreamingResponse(
                stream_with_logging(),
                media_type="text/event-stream"
            )
        else:
            # Non-streaming response
            chunks = []
            async for chunk in provider.chat_openai(
                account=account,
                model=request_data.model,
                messages=request_data.messages,
                stream=False,
                temperature=request_data.temperature,
                max_tokens=request_data.max_tokens,
                tools=request_data.tools
            ):
                chunks.append(chunk)
            
            response_data = b"".join(chunks)
            response_json = json.loads(response_data.decode("utf-8"))
            
            # Calculate tokens using tokenizer
            from kiro.utils_pkg.tokenizer import count_message_tokens, count_tokens
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Calculate input tokens from request messages
            input_tokens = count_message_tokens(
                [{"role": msg.role, "content": msg.content} for msg in request_data.messages]
            )
            
            # Calculate output tokens from response
            output_text = ""
            if "choices" in response_json and response_json["choices"]:
                message = response_json["choices"][0].get("message", {})
                content = message.get("content", "")
                if content:
                    output_text = content
            output_tokens = count_tokens(output_text)
            logger.info(f"OpenAI non-streaming: {len(output_text)} chars, {output_tokens} tokens")
            
            try:
                auth_manager.log_request(
                    api_key_id=api_key_id,
                    account_id=account.id,
                    model=request_data.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status="success",
                    channel="openai",
                    duration_ms=duration_ms
                )
            except Exception as log_error:
                logger.error(f"Failed to log request: {log_error}")
            
            return JSONResponse(
                content=response_json,
                media_type="application/json"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in chat_completions: {e}")
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Log the error
        try:
            auth_manager.log_request(
                api_key_id=api_key_id,
                account_id=account.id if 'account' in locals() else None,
                model=request_data.model,
                input_tokens=0,
                output_tokens=0,
                status="error",
                channel="openai",
                duration_ms=duration_ms
            )
        except Exception as log_error:
            logger.error(f"Failed to log error: {log_error}")
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": str(e),
                    "type": "internal_error"
                }
            }
        )


@router.post("/v1/responses")
async def responses(
    request: Request,
    request_data: ChatCompletionRequest,
    api_key_id: int = Depends(verify_api_key)
):
    """
    OpenAI /v1/responses endpoint with multi-provider support.
    
    This endpoint is an alias for /v1/chat/completions for compatibility.
    
    Supports automatic routing:
    - GLM models (glm-*) → GLMProvider
    - Other models (claude-*, auto) → Kiro
    
    Args:
        request: FastAPI Request
        request_data: Chat completion request
        api_key_id: Verified API key ID
    
    Returns:
        StreamingResponse for streaming mode
        JSONResponse for non-streaming mode
    """
    logger.info(
        f"Request to /v1/responses (model={request_data.model}, "
        f"stream={request_data.stream})"
    )
    
    # Forward to chat_completions endpoint
    return await chat_completions(request, request_data, api_key_id)


# ==================== Anthropic Endpoints ====================

@router.post("/v1/messages")
async def messages(
    request: Request,
    request_data: AnthropicMessagesRequest,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    api_key_id: int = Depends(verify_anthropic_api_key)
):
    """
    Anthropic Messages API endpoint with multi-provider support.
    
    Supports automatic routing:
    - GLM models (glm-*) → GLMProvider
    - Other models (claude-*, auto) → KiroProvider
    
    Required headers:
    - x-api-key: Your API key (or Authorization: Bearer)
    - anthropic-version: API version (optional, for compatibility)
    - Content-Type: application/json
    
    Args:
        request: FastAPI Request for accessing app.state
        request_data: Request in Anthropic MessagesRequest format
        anthropic_version: Anthropic API version header (optional)
    
    Returns:
        StreamingResponse for streaming mode (SSE)
        JSONResponse for non-streaming mode
    
    Raises:
        HTTPException: On validation or API errors
    """
    logger.info(f"Request to /v1/messages (model={request_data.model}, stream={request_data.stream})")
    
    # Record start time for duration tracking
    start_time = time.time()
    
    if anthropic_version:
        logger.debug(f"Anthropic-Version header: {anthropic_version}")
    
    auth_manager: AccountManager = request.app.state.auth_manager
    model_cache: ModelInfoCache = request.app.state.model_cache
    
    # Initialize provider router
    provider_router = ProviderRouter(auth_manager, model_cache)
    
    try:
        # Route to appropriate provider and get account
        provider, account = await provider_router.route_request(request_data.model)
        
        logger.info(
            f"Routed to provider '{provider.name}' with account {account.email}"
        )
        
        # Use provider's chat_anthropic() method for all providers
        if request_data.stream:
            # Streaming response with logging wrapper
            output_content = []
            
            async def stream_with_logging():
                """Wrapper to collect output and log request."""
                nonlocal output_content
                try:
                    async for chunk in provider.chat_anthropic(
                        account=account,
                        model=request_data.model,
                        messages=request_data.messages,
                        stream=True,
                        temperature=request_data.temperature,
                        max_tokens=request_data.max_tokens,
                        system=request_data.system,
                        tools=request_data.tools
                    ):
                        # Collect output content for token counting
                        try:
                            # Handle both bytes and str
                            if isinstance(chunk, bytes):
                                chunk_str = chunk.decode('utf-8')
                            else:
                                chunk_str = chunk
                            # logger.info(f"Anthropic chunk preview: {chunk_str[:100]}")
                            if 'event: content_block_delta' in chunk_str:
                                lines = chunk_str.split('\n')
                                for line in lines:
                                    if line.startswith('data: '):
                                        data = json.loads(line[6:])
                                        if data.get('type') == 'content_block_delta':
                                            delta = data.get('delta', {})
                                            # Extract text from text_delta
                                            text = delta.get('text', '')
                                            if text:
                                                output_content.append(text)
                                                logger.debug(f"Anthropic: Collected text {len(text)} chars")
                                            # Extract thinking from thinking_delta
                                            thinking = delta.get('thinking', '')
                                            if thinking:
                                                output_content.append(thinking)
                                                logger.debug(f"Anthropic: Collected thinking {len(thinking)} chars")
                        except Exception as e:
                            logger.debug(f"Anthropic: Error collecting content: {e}")
                        yield chunk
                finally:
                    # Calculate tokens using tokenizer
                    from kiro.utils_pkg.tokenizer import count_message_tokens, count_tokens
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    # Calculate input tokens
                    messages_for_count = []
                    for msg in request_data.messages:
                        if isinstance(msg.content, str):
                            messages_for_count.append({"role": msg.role, "content": msg.content})
                        elif isinstance(msg.content, list):
                            text_content = ""
                            for block in msg.content:
                                if hasattr(block, 'type') and block.type == 'text':
                                    text_content += block.text
                            messages_for_count.append({"role": msg.role, "content": text_content})
                    
                    input_tokens = count_message_tokens(messages_for_count)
                    if request_data.system:
                        input_tokens += count_tokens(request_data.system)
                    
                    # Calculate output tokens
                    output_text = ''.join(output_content)
                    output_tokens = count_tokens(output_text)
                    logger.info(f"Anthropic: Collected {len(output_content)} chunks, {len(output_text)} chars, {output_tokens} tokens")
                    
                    try:
                        auth_manager.log_request(
                            api_key_id=api_key_id,
                            account_id=account.id,
                            model=request_data.model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            status="success",
                            channel="anthropic",
                            duration_ms=duration_ms
                        )
                    except Exception as log_error:
                        logger.error(f"Failed to log streaming request: {log_error}")
            
            return StreamingResponse(
                stream_with_logging(),
                media_type="text/event-stream"
            )
        else:
            # Non-streaming response
            chunks = []
            async for chunk in provider.chat_anthropic(
                account=account,
                model=request_data.model,
                messages=request_data.messages,
                stream=False,
                temperature=request_data.temperature,
                max_tokens=request_data.max_tokens,
                system=request_data.system,
                tools=request_data.tools
            ):
                chunks.append(chunk)
            
            response_data = b"".join(chunks)
            response_json = json.loads(response_data.decode("utf-8"))
            
            # Calculate tokens using tokenizer
            from kiro.utils_pkg.tokenizer import count_message_tokens, count_tokens
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Calculate input tokens
            messages_for_count = []
            for msg in request_data.messages:
                if isinstance(msg.content, str):
                    messages_for_count.append({"role": msg.role, "content": msg.content})
                elif isinstance(msg.content, list):
                    text_content = ""
                    for block in msg.content:
                        if hasattr(block, 'type') and block.type == 'text':
                            text_content += block.text
                    messages_for_count.append({"role": msg.role, "content": text_content})
            
            input_tokens = count_message_tokens(messages_for_count)
            if request_data.system:
                input_tokens += count_tokens(request_data.system)
            
            # Calculate output tokens from response
            output_text = ""
            if "content" in response_json:
                for block in response_json["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        output_text += block.get("text", "")
            output_tokens = count_tokens(output_text)
            logger.info(f"OpenAI non-streaming: {len(output_text)} chars, {output_tokens} tokens")
            
            try:
                auth_manager.log_request(
                    api_key_id=api_key_id,
                    account_id=account.id,
                    model=request_data.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status="success",
                    channel="anthropic",
                    duration_ms=duration_ms
                )
            except Exception as log_error:
                logger.error(f"Failed to log request: {log_error}")
            
            return JSONResponse(
                content=response_json,
                media_type="application/json"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in messages: {e}")
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Log the error
        try:
            auth_manager.log_request(
                api_key_id=api_key_id,
                account_id=account.id if 'account' in locals() else None,
                model=request_data.model,
                input_tokens=0,
                output_tokens=0,
                status="error",
                channel="anthropic",
                duration_ms=duration_ms
            )
        except Exception as log_error:
            logger.error(f"Failed to log error: {log_error}")
        
        raise HTTPException(
            status_code=500,
            detail={
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": str(e)
                }
            }
        )

