# -*- coding: utf-8 -*-
"""
FastAPI routes for OpenAI-compatible API.

Contains /v1/chat/completions and /v1/models endpoints.
Supports multiple providers (Kiro, GLM) with automatic routing based on model name.
"""

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from loguru import logger
from pydantic import BaseModel, Field

from kiro.core.auth import AccountManager
from kiro.core.provider_router import ProviderRouter


# --- Security scheme ---
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


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
router = APIRouter(tags=["OpenAI API"])


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
    OpenAI-compatible chat completions endpoint.
    
    Supports multiple providers:
    - GLM models (glm-*) → GLMProvider
    - Other models (claude-*, auto) → KiroProvider (via existing logic)
    
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
    provider_router = ProviderRouter(auth_manager)
    
    try:
        # Route to appropriate provider and get account
        provider, account = await provider_router.route_request(request_data.model)
        
        logger.info(
            f"Routed to provider '{provider.name}' with account {account.id}"
        )
        
        # For GLM provider, use the new provider system
        if provider.name == "glm":
            if request_data.stream:
                # Streaming response
                return StreamingResponse(
                    provider.chat(
                        account=account,
                        model=request_data.model,
                        messages=request_data.messages,
                        stream=True,
                        temperature=request_data.temperature,
                        max_tokens=request_data.max_tokens,
                        tools=request_data.tools
                    ),
                    media_type="text/event-stream"
                )
            else:
                # Non-streaming response
                chunks = []
                async for chunk in provider.chat(
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
                return JSONResponse(
                    content=json.loads(response_data.decode("utf-8")),
                    media_type="application/json"
                )
        
        # For Kiro provider, return error for now
        # (Kiro logic is still in Anthropic endpoint)
        else:
            raise HTTPException(
                status_code=501,
                detail={
                    "error": {
                        "message": "OpenAI endpoint for Kiro models not yet implemented. "
                                 "Please use /v1/messages endpoint (Anthropic format) for Kiro models.",
                        "type": "not_implemented_error"
                    }
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in chat_completions: {e}")
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Log the error
        try:
            auth_manager.create_request_log(
                api_key_id=api_key_id,
                account_id=None,
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
