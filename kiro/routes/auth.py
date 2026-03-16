# -*- coding: utf-8 -*-
"""
Authentication routes for admin web UI.

Provides login/logout functionality with JWT-based authentication.
JWT tokens are stateless and don't require server-side storage.
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel


router = APIRouter(prefix="/auth", tags=["auth"])

# JWT configuration - use fixed secret key from environment or generate a persistent one
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "kiro-gateway-default-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7


class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response."""
    success: bool
    message: str
    token: Optional[str] = None


def create_jwt_token(username: str) -> str:
    """Create a JWT token for the user.
    
    Args:
        username: Username to encode in token.
    
    Returns:
        JWT token string.
    """
    expiration = datetime.utcnow() + timedelta(days=JWT_EXPIRATION_DAYS)
    payload = {
        "sub": username,
        "exp": expiration,
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def verify_jwt_token(token: str) -> Optional[str]:
    """Verify JWT token and return username.
    
    Args:
        token: JWT token string.
    
    Returns:
        Username if token is valid, None otherwise.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        return username
    except jwt.ExpiredSignatureError:
        logger.debug("JWT token expired")
        return None
    except jwt.InvalidTokenError:
        logger.debug("Invalid JWT token")
        return None


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

    # Generate JWT token (contains username and expiration)
    token = create_jwt_token(body.username)

    logger.info(f"User logged in: {body.username}")
    
    # Create redirect response to /admin
    from fastapi.responses import RedirectResponse
    response = RedirectResponse(url="/admin", status_code=302)
    
    # Set cookie (httponly for security)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=86400 * JWT_EXPIRATION_DAYS,
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
    session_token = request.cookies.get("session_token")
    
    if session_token:
        username = verify_jwt_token(session_token)
        if username:
            logger.info(f"User logged out: {username}")

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
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    # Verify JWT token
    username = verify_jwt_token(session_token)
    if not username:
        # Token invalid or expired - clear cookie
        response = JSONResponse(
            {"detail": "Token expired or invalid"},
            status_code=401
        )
        response.delete_cookie("session_token", path="/")
        return response

    return JSONResponse({"username": username})


def verify_session(request: Request) -> str:
    """Dependency to verify JWT token.

    Args:
        request: FastAPI request.

    Returns:
        Username of logged-in user.

    Raises:
        HTTPException: 401 if token is invalid or expired.
    """
    session_token = request.cookies.get("session_token")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    # Verify JWT token
    username = verify_jwt_token(session_token)
    if not username:
        raise HTTPException(status_code=401, detail="Token expired or invalid")

    return username
