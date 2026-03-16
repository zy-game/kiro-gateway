# -*- coding: utf-8 -*-
"""
Authentication routes for admin web UI.

Provides login/logout functionality with database-backed session management.
Sessions are stored in the database and validated on each request.
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel


router = APIRouter(prefix="/auth", tags=["auth"])

# Session configuration
SESSION_EXPIRATION_DAYS = 7


class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response."""
    success: bool
    message: str
    token: Optional[str] = None


def create_session_token() -> str:
    """Generate a secure random session token.
    
    Returns:
        Random session token string (32 bytes hex = 64 characters).
    """
    return secrets.token_hex(32)


@router.post("/login")
async def login(request: Request, body: LoginRequest) -> Response:
    """Admin login endpoint.

    Args:
        request: FastAPI request.
        body: Login credentials.

    Returns:
        302 redirect to /admin with session cookie set.
    """
    manager = request.app.state.auth_manager

    # Verify credentials
    user = manager.verify_admin_user(body.username, body.password)
    if not user:
        logger.warning(f"Failed login attempt for username: {body.username}")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Generate session token and store in database
    session_token = create_session_token()
    manager.create_session(body.username, session_token, expires_in_days=SESSION_EXPIRATION_DAYS)

    logger.info(f"User logged in: {body.username}")
    
    # Create redirect response to /admin
    from fastapi.responses import RedirectResponse
    response = RedirectResponse(url="/admin", status_code=302)
    
    # Set cookie (httponly for security)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=86400 * SESSION_EXPIRATION_DAYS,
        samesite="lax",
        path="/",
        secure=False  # Set to True if using HTTPS
    )
    
    return response


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Admin logout endpoint.

    Args:
        request: FastAPI request.

    Returns:
        JSON with success status (cookie cleared in response).
    """
    manager = request.app.state.auth_manager
    session_token = request.cookies.get("session_token")
    
    if session_token:
        # Get username before deleting session
        username = manager.get_session(session_token)
        if username:
            logger.info(f"User logged out: {username}")
        
        # Delete session from database
        manager.delete_session(session_token)

    # Create response
    response = JSONResponse({"success": True, "message": "Logged out"})
    
    # Clear cookie with same settings as when it was set
    response.delete_cookie(
        key="session_token",
        path="/",
        samesite="lax"
    )

    return response


@router.get("/me")
async def get_current_user(request: Request) -> JSONResponse:
    """Get current logged-in user.

    Args:
        request: FastAPI request.

    Returns:
        JSON with username if logged in.
    """
    manager = request.app.state.auth_manager
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    # Verify session in database
    username = manager.get_session(session_token)
    if not username:
        # Session invalid or expired - clear cookie
        response = JSONResponse(
            {"detail": "Session expired or invalid"},
            status_code=401
        )
        response.delete_cookie("session_token", path="/")
        return response

    return JSONResponse({"username": username})


def verify_session(request: Request) -> str:
    """Dependency to verify session token in database.

    Args:
        request: FastAPI request.

    Returns:
        Username of logged-in user.

    Raises:
        HTTPException: 401 if session is invalid or expired.
    """
    manager = request.app.state.auth_manager
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    # Verify session in database
    username = manager.get_session(session_token)
    if not username:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return username
