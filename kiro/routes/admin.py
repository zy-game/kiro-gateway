# -*- coding: utf-8 -*-
"""
Admin REST API for account and API key management.

Endpoints:
    GET    /admin/accounts              List all accounts
    POST   /admin/accounts              Create account
    GET    /admin/accounts/{id}         Get account
    PUT    /admin/accounts/{id}         Update account
    DELETE /admin/accounts/{id}         Delete account
    POST   /admin/accounts/{id}/refresh-usage  Refresh usage from Kiro API
    
    GET    /admin/api-keys              List all API keys
    POST   /admin/api-keys              Generate new API key
    DELETE /admin/api-keys/{id}         Delete API key
    
    GET    /admin/users                 List all admin users
    POST   /admin/users                 Create admin user
    DELETE /admin/users/{id}            Delete admin user
"""

import copy
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from kiro.routes.auth import verify_session

router = APIRouter(prefix="/admin", tags=["admin"])


def _mask_config(config: dict) -> dict:
    """Return a copy of config with sensitive token fields replaced by '***'.

    Args:
        config: Raw credentials dict.

    Returns:
        Sanitised copy safe for API responses.
    """
    masked = copy.deepcopy(config)
    for key in ("accessToken", "access_token", "refreshToken", "refresh_token",
                "clientSecret", "client_secret"):
        if key in masked:
            masked[key] = "***"
    return masked


def _account_to_dict(account: Any, mask: bool = True) -> dict:
    """Serialise an Account dataclass to a response dict.

    Args:
        account: Account instance.
        mask: Whether to mask sensitive config fields.

    Returns:
        JSON-serialisable dict.
    """
    return {
        "id": account.id,
        "type": account.type,
        "priority": account.priority,
        "config": _mask_config(account.config) if mask else account.config,
        "limit": account.limit,
        "usage": account.usage,
        "email": getattr(account, "email", None),
        "expires_at": getattr(account, "expires_at", None),
        "next_reset_at": getattr(account, "next_reset_at", None),
    }


# ------------------------------------------------------------------
# Pydantic request models
# ------------------------------------------------------------------

class AccountCreateRequest(BaseModel):
    """Request body for creating an account."""

    type: str = Field(default="kiro", description="Account type")
    priority: int = Field(default=0, description="Scheduling priority (higher = preferred)")
    config: Dict[str, Any] = Field(default_factory=dict, description="Credentials JSON")
    limit: int = Field(default=0, description="Usage limit (0 = unlimited)")


class AccountUpdateRequest(BaseModel):
    """Request body for updating an account. All fields are optional."""

    type: Optional[str] = None
    priority: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    limit: Optional[int] = None
    usage: Optional[float] = None


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("/accounts", dependencies=[Depends(verify_session)])
async def list_accounts(request: Request) -> JSONResponse:
    """List all accounts sorted by priority DESC.

    Returns:
        JSON array of account objects (config fields masked).
    """
    manager = request.app.state.auth_manager
    accounts = manager.list_accounts()
    return JSONResponse([_account_to_dict(a) for a in accounts])


@router.post("/accounts", dependencies=[Depends(verify_session)], status_code=201)
async def create_account(request: Request, body: AccountCreateRequest) -> JSONResponse:
    """Create a new account.

    Args:
        body: Account creation parameters.

    Returns:
        Created account object (config fields masked).
    """
    manager = request.app.state.auth_manager
    account = manager.create_account(
        type=body.type,
        priority=body.priority,
        config=body.config,
        limit=body.limit,
    )
    logger.info(f"Admin: created account id={account.id}")
    return JSONResponse(_account_to_dict(account), status_code=201)


@router.get("/accounts/{account_id}", dependencies=[Depends(verify_session)])
async def get_account(request: Request, account_id: int) -> JSONResponse:
    """Get a single account by ID.

    Args:
        account_id: Account primary key.

    Returns:
        Account object (config fields masked).

    Raises:
        HTTPException: 404 if not found.
    """
    manager = request.app.state.auth_manager
    try:
        account = manager.get_account(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return JSONResponse(_account_to_dict(account))


@router.put("/accounts/{account_id}", dependencies=[Depends(verify_session)])
async def update_account(
    request: Request, account_id: int, body: AccountUpdateRequest
) -> JSONResponse:
    """Update account fields.

    Args:
        account_id: Account primary key.
        body: Fields to update (only provided fields are changed).

    Returns:
        Updated account object (config fields masked).

    Raises:
        HTTPException: 404 if not found, 400 if no fields provided.
    """
    manager = request.app.state.auth_manager
    try:
        manager.get_account(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    try:
        account = manager.update_account(account_id, **updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"Admin: updated account id={account_id}")
    return JSONResponse(_account_to_dict(account))


@router.delete("/accounts/{account_id}", dependencies=[Depends(verify_session)], status_code=204)
async def delete_account(request: Request, account_id: int) -> JSONResponse:
    """Delete an account.

    Args:
        account_id: Account primary key.

    Raises:
        HTTPException: 404 if not found.
    """
    manager = request.app.state.auth_manager
    try:
        manager.delete_account(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    logger.info(f"Admin: deleted account id={account_id}")
    return JSONResponse(None, status_code=204)


@router.post("/accounts/{account_id}/refresh-usage", dependencies=[Depends(verify_session)])
async def refresh_usage(request: Request, account_id: int) -> JSONResponse:
    """Trigger a usage refresh from the Kiro API for the given account.

    Args:
        account_id: Account primary key.

    Returns:
        JSON with updated used and limit values.

    Raises:
        HTTPException: 404 if not found, 502 if Kiro API call fails.
    """
    manager = request.app.state.auth_manager
    try:
        account = manager.get_account(account_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    try:
        used, limit = await manager.refresh_usage(account)
    except Exception as e:
        logger.error(f"Admin: usage refresh failed for account {account_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Usage refresh failed: {e}")

    logger.info(f"Admin: refreshed usage for account {account_id} — used={used}, limit={limit}")
    return JSONResponse({"id": account_id, "usage": used, "limit": limit})


# ------------------------------------------------------------------
# API Key Management Routes
# ------------------------------------------------------------------

class ApiKeyCreateRequest(BaseModel):
    """Request body for creating an API key."""
    name: str = Field(default="Default Key", description="Human-readable name for the key")


@router.get("/api-keys", dependencies=[Depends(verify_session)])
async def list_api_keys(request: Request, show_full: bool = False) -> JSONResponse:
    """List all API keys.

    Args:
        show_full: If True, return full keys. If False (default), mask keys for security.

    Returns:
        JSON array of API key objects (key field is masked by default).
    """
    manager = request.app.state.auth_manager
    keys = manager.list_api_keys()
    
    # Format keys based on show_full parameter
    formatted_keys = []
    for key in keys:
        formatted_keys.append({
            "id": key.id,
            "key": key.key if show_full else (f"...{key.key[-8:]}" if len(key.key) > 8 else "***"),
            "full_key": key.key,  # Always include full key for copy functionality
            "name": key.name,
            "created_at": key.created_at,
        })
    
    return JSONResponse(formatted_keys)


@router.post("/api-keys", dependencies=[Depends(verify_session)], status_code=201)
async def create_api_key(request: Request, body: ApiKeyCreateRequest) -> JSONResponse:
    """Generate a new API key.

    Args:
        body: API key creation parameters.

    Returns:
        Created API key object (full key is shown ONLY on creation).
    """
    manager = request.app.state.auth_manager
    api_key = manager.generate_api_key(name=body.name)
    
    logger.info(f"Admin: generated API key id={api_key.id} name={api_key.name}")
    
    return JSONResponse({
        "id": api_key.id,
        "key": api_key.key,  # Full key shown only on creation
        "name": api_key.name,
        "created_at": api_key.created_at,
    }, status_code=201)


@router.delete("/api-keys/{key_id}", dependencies=[Depends(verify_session)], status_code=204)
async def delete_api_key(request: Request, key_id: int) -> JSONResponse:
    """Delete an API key.

    Args:
        key_id: API key primary key.

    Raises:
        HTTPException: 404 if not found.
    """
    manager = request.app.state.auth_manager
    try:
        manager.delete_api_key(key_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"API key {key_id} not found")
    logger.info(f"Admin: deleted API key id={key_id}")
    return JSONResponse(None, status_code=204)





# ------------------------------------------------------------------
# Admin User Management Routes
# ------------------------------------------------------------------

class AdminUserCreateRequest(BaseModel):
    """Request body for creating an admin user."""
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")


@router.get("/users", dependencies=[Depends(verify_session)])
async def list_admin_users(request: Request) -> JSONResponse:
    """List all admin users."""
    manager = request.app.state.auth_manager
    users = manager.list_admin_users()
    users_data = [{"id": u.id, "username": u.username, "created_at": u.created_at} for u in users]
    return JSONResponse(users_data)


@router.post("/users", dependencies=[Depends(verify_session)], status_code=201)
async def create_admin_user(request: Request, body: AdminUserCreateRequest) -> JSONResponse:
    """Create a new admin user."""
    manager = request.app.state.auth_manager
    try:
        user = manager.create_admin_user(username=body.username, password=body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info(f"Admin: created user id={user.id} username={user.username}")
    return JSONResponse({"id": user.id, "username": user.username, "created_at": user.created_at}, status_code=201)


@router.delete("/users/{user_id}", dependencies=[Depends(verify_session)], status_code=204)
async def delete_admin_user(request: Request, user_id: int) -> JSONResponse:
    """Delete an admin user."""
    manager = request.app.state.auth_manager
    try:
        manager.delete_admin_user(user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Admin user {user_id} not found")
    logger.info(f"Admin: deleted user id={user_id}")
    return JSONResponse(None, status_code=204)


# ==================== Request Logs & Statistics ====================

@router.get("/stats/hourly", dependencies=[Depends(verify_session)])
async def get_hourly_stats(request: Request, hours: int = 24) -> JSONResponse:
    """Get hourly usage statistics.
    
    Args:
        hours: Number of hours to query (1-168, default 24).
    
    Returns:
        List of hourly statistics.
    """
    # Limit range: 1 hour to 7 days (168 hours)
    if hours < 1:
        hours = 1
    elif hours > 168:
        hours = 168
    
    manager = request.app.state.auth_manager
    stats = manager.get_hourly_stats(hours=hours)
    return JSONResponse(stats)


@router.get("/stats/daily", dependencies=[Depends(verify_session)])
async def get_daily_stats(request: Request, days: int = 30) -> JSONResponse:
    """Get daily usage statistics.
    
    Args:
        days: Number of days to query (default 30).
    
    Returns:
        List of daily statistics.
    """
    manager = request.app.state.auth_manager
    stats = manager.get_daily_stats(days=days)
    return JSONResponse(stats)


@router.get("/logs", dependencies=[Depends(verify_session)])
async def list_request_logs(
    request: Request, 
    limit: int = 20, 
    offset: int = 0,
    search_model: str = None,
    search_status: str = None
) -> JSONResponse:
    """List request logs with pagination and search."""
    manager = request.app.state.auth_manager
    logs, total = manager.list_request_logs(
        limit=limit, 
        offset=offset,
        search_model=search_model,
        search_status=search_status
    )
    return JSONResponse({
        "logs": logs,
        "total": total,
        "limit": limit,
        "offset": offset
    })
