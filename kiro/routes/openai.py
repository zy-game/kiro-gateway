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
            f"Routed to provider '{provider.name}' with account {account.id}"
        )
        
        # Use provider's chat_openai() method for all providers
        if request_data.stream:
            # Streaming response with logging wrapper
            final_usage = {"input_tokens": 0, "output_tokens": 0}
            
            async def stream_with_logging():
                """Wrapper to track usage and log request."""
                nonlocal final_usage
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
                        # Try to extract usage from chunk
                        try:
                            chunk_str = chunk.decode('utf-8')
                            if chunk_str.startswith('data: ') and '[DONE]' not in chunk_str:
                                data = json.loads(chunk_str[6:])
                                if 'usage' in data:
                                    usage = data['usage']
                                    final_usage['input_tokens'] = usage.get('input_tokens', 0) or usage.get('prompt_tokens', 0)
                                    final_usage['output_tokens'] = usage.get('output_tokens', 0) or usage.get('completion_tokens', 0)
                        except:
                            pass
                        yield chunk
                finally:
                    # Log request after streaming completes
                    duration_ms = int((time.time() - start_time) * 1000)
                    try:
                        auth_manager.log_request(
                            api_key_id=api_key_id,
                            account_id=account.id,
                            model=request_data.model,
                            input_tokens=final_usage['input_tokens'],
                            output_tokens=final_usage['output_tokens'],
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
            
            # Log successful request
            duration_ms = int((time.time() - start_time) * 1000)
            usage = response_json.get("usage", {})
            try:
                auth_manager.log_request(
                    api_key_id=api_key_id,
                    account_id=account.id,
                    model=request_data.model,
                    input_tokens=usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0) or usage.get("completion_tokens", 0),
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
            f"Routed to provider '{provider.name}' with account {account.id}"
        )
        
        # Use provider's chat_anthropic() method for all providers
        if request_data.stream:
            # Streaming response with logging wrapper
            final_usage = {"input_tokens": 0, "output_tokens": 0}
            
            async def stream_with_logging():
                """Wrapper to track usage and log request."""
                nonlocal final_usage
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
                        # Try to extract usage from Anthropic SSE chunk
                        try:
                            chunk_str = chunk.decode('utf-8')
                            if 'event: message_delta' in chunk_str or 'event: message_stop' in chunk_str:
                                lines = chunk_str.split('\n')
                                for line in lines:
                                    if line.startswith('data: '):
                                        data = json.loads(line[6:])
                                        if 'usage' in data:
                                            usage = data['usage']
                                            final_usage['input_tokens'] = usage.get('input_tokens', 0)
                                            final_usage['output_tokens'] = usage.get('output_tokens', 0)
                        except:
                            pass
                        yield chunk
                finally:
                    # Log request after streaming completes
                    duration_ms = int((time.time() - start_time) * 1000)
                    try:
                        auth_manager.log_request(
                            api_key_id=api_key_id,
                            account_id=account.id,
                            model=request_data.model,
                            input_tokens=final_usage['input_tokens'],
                            output_tokens=final_usage['output_tokens'],
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
            
            # Log successful request
            duration_ms = int((time.time() - start_time) * 1000)
            usage = response_json.get("usage", {})
            try:
                auth_manager.log_request(
                    api_key_id=api_key_id,
                    account_id=account.id,
                    model=request_data.model,
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
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

