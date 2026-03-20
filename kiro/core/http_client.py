# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
HTTP client for Kiro API with retry logic support.

Handles:
- 403: automatic token refresh and retry
- 429: exponential backoff
- 5xx: exponential backoff
- Timeouts: exponential backoff

Supports both per-request clients and shared application-level client
with connection pooling for better resource management.
"""

import asyncio
import json
from typing import Optional

import httpx
from fastapi import HTTPException
from loguru import logger

from kiro.core.config import MAX_RETRIES, BASE_RETRY_DELAY, FIRST_TOKEN_MAX_RETRIES, STREAMING_READ_TIMEOUT
from kiro.core.auth import AccountManager
from kiro.core.auth import Account
from kiro.utils_pkg.helpers import get_kiro_headers
from kiro.utils_pkg.network_errors import classify_network_error, get_short_error_message, NetworkErrorInfo


class KiroHttpClient:
    """
    HTTP client for Kiro API with retry logic support.
    
    Automatically handles errors and retries requests:
    - 403: refreshes token and retries
    - 429: waits with exponential backoff
    - 5xx: waits with exponential backoff
    - Timeouts: waits with exponential backoff
    
    Supports two modes of operation:
    1. Per-request client: Creates and owns its own httpx.AsyncClient
    2. Shared client: Uses an application-level shared client (recommended)
    
    Using a shared client reduces memory usage and enables connection pooling,
    which is especially important for handling concurrent requests.
    
    Attributes:
        auth_manager: Authentication manager for obtaining tokens
        client: httpx HTTP client (owned or shared)
    
    Example:
        >>> # Per-request client (legacy mode)
        >>> client = KiroHttpClient(auth_manager)
        >>> response = await client.request_with_retry(...)
        
        >>> # Shared client (recommended)
        >>> shared = httpx.AsyncClient(limits=httpx.Limits(...))
        >>> client = KiroHttpClient(auth_manager, shared_client=shared)
        >>> response = await client.request_with_retry(...)
    """
    
    def __init__(
        self,
        auth_manager: AccountManager,
        account: Account,
        shared_client: Optional[httpx.AsyncClient] = None
    ):
        """
        Initializes the HTTP client.
        
        Args:
            auth_manager: Account manager
            account: The account to use for this request (token + force_refresh)
            shared_client: Optional shared httpx.AsyncClient for connection pooling.
        """
        self.auth_manager = auth_manager
        self.account = account
        self._shared_client = shared_client
        self._owns_client = shared_client is None
        self.client: Optional[httpx.AsyncClient] = shared_client
    
    async def _get_client(self, stream: bool = False) -> httpx.AsyncClient:
        """
        Returns or creates an HTTP client with proper timeouts.
        
        If a shared client was provided at initialization, it is returned as-is.
        Otherwise, creates a new client with appropriate timeout configuration.
        
        httpx timeouts:
        - connect: TCP handshake (DNS + TCP SYN/ACK)
        - read: waiting for data from server between chunks
        - write: sending data to server
        - pool: waiting for free connection from pool
        
        IMPORTANT: FIRST_TOKEN_TIMEOUT is NOT used here!
        It is applied in streaming_openai.py via asyncio.wait_for() to control
        the wait time for the first token from the model (retry business logic).
        
        Args:
            stream: If True, uses STREAMING_READ_TIMEOUT for read (only for new clients)
        
        Returns:
            Active HTTP client
        """
        # If using shared client, return it directly
        # Shared client should be pre-configured with appropriate timeouts
        if self._shared_client is not None:
            return self._shared_client
        
        # Create new client if needed (per-request mode)
        if self.client is None or self.client.is_closed:
            if stream:
                # For streaming:
                # - connect: 30 sec (TCP connection, usually < 1 sec)
                # - read: STREAMING_READ_TIMEOUT (300 sec) - model may "think" between chunks
                # - write/pool: standard values
                timeout_config = httpx.Timeout(
                    connect=30.0,
                    read=STREAMING_READ_TIMEOUT,
                    write=30.0,
                    pool=30.0
                )
                logger.debug(f"Creating streaming HTTP client (read_timeout={STREAMING_READ_TIMEOUT}s)")
            else:
                # For regular requests: single timeout of 300 sec
                timeout_config = httpx.Timeout(timeout=300.0)
                logger.debug("Creating non-streaming HTTP client (timeout=300s)")
            
            self.client = httpx.AsyncClient(timeout=timeout_config, follow_redirects=True)
        return self.client
    
    async def close(self) -> None:
        """
        Closes the HTTP client if this instance owns it.
        
        If using a shared client, this method does nothing - the shared client
        should be closed by the application lifecycle manager.
        
        Uses graceful exception handling to prevent errors during cleanup
        from masking the original exception in finally blocks.
        """
        # Don't close shared clients - they're managed by the application
        if not self._owns_client:
            return
        
        if self.client and not self.client.is_closed:
            try:
                await self.client.aclose()
            except Exception as e:
                # Log but don't propagate - we're in cleanup code
                # Propagating here could mask the original exception
                logger.warning(f"Error closing HTTP client: {e}")
    
    async def request_with_retry(
        self,
        method: str,
        url: str,
        json_data: dict,
        stream: bool = False
    ) -> httpx.Response:
        """
        Executes an HTTP request with retry logic.
        
        Automatically handles various error types:
        - 403: refreshes token via auth_manager.force_refresh() and retries
        - 429: waits with exponential backoff (1s, 2s, 4s)
        - 5xx: waits with exponential backoff
        - Timeouts: waits with exponential backoff
        
        For streaming, STREAMING_READ_TIMEOUT is used for waiting between chunks.
        First token timeout is controlled separately in streaming_openai.py via asyncio.wait_for().
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            json_data: Request body (JSON)
            stream: Use streaming (default False)
        
        Returns:
            httpx.Response with successful response
        
        Raises:
            HTTPException: On failure after all attempts (502/504)
        """
        # Ensure token is valid before making the request
        if self.account.type == "kiro":
            logger.debug(f"Checking token validity for account {self.account.id} before request")
            valid_token = await self.auth_manager._ensure_valid_token_kiro(self.account)
            if valid_token:
                self.account.config["accessToken"] = valid_token
                logger.debug(f"Token validated/refreshed for account {self.account.id}")
            else:
                logger.warning(f"Could not ensure valid token for account {self.account.id}, proceeding with existing token")
        
        # Determine the number of retry attempts
        # FIRST_TOKEN_TIMEOUT is used in streaming_openai.py, not here
        max_retries = FIRST_TOKEN_MAX_RETRIES if stream else MAX_RETRIES
        
        client = await self._get_client(stream=stream)
        last_error = None
        last_error_info: Optional[NetworkErrorInfo] = None
        
        for attempt in range(max_retries):
            try:
                # Get current token
                token = self.account.config.get("accessToken") or self.account.config.get("access_token") or ""
                headers = get_kiro_headers(token)
                
                if stream:
                    req = client.build_request(method, url, json=json_data, headers=headers)
                    logger.debug("Sending request to Kiro API...")
                    response = await client.send(req, stream=True)
                else:
                    logger.debug("Sending request to Kiro API...")
                    response = await client.request(method, url, json=json_data, headers=headers)
                
                # Check status
                if response.status_code == 200:
                    self.auth_manager.clear_cooldown(self.account.id)
                    return response
                
                # 403 - token expired, refresh and retry
                if response.status_code == 403:
                    logger.warning(f"Received 403, refreshing token (attempt {attempt + 1}/{MAX_RETRIES})")
                    try:
                        token = await self.auth_manager.force_refresh(self.account)
                        self.account.config["accessToken"] = token
                        continue
                    except RuntimeError as e:
                        logger.error(f"Token refresh failed for account {self.account.id}: {e}")
                        last_error = e
                        last_error_info = NetworkErrorInfo(
                            error_type="authentication_error",
                            user_message=f"Account {self.account.id} authentication failed. Token refresh unsuccessful.",
                            technical_details=str(e),
                            is_retryable=False,
                            suggested_http_code=401,
                            troubleshooting_steps=[
                                "Check if the account credentials are still valid",
                                "Try re-authenticating the account in settings"
                            ]
                        )
                        break
                
                # 429 - rate limit, immediately mark account and fail
                # The caller (Kiro IDE) will retry the request, which will be routed to a different account
                if response.status_code == 429:
                    logger.warning(f"Received 429 for account {self.account.id}, marking as rate-limited and failing immediately")
                    self.auth_manager.mark_rate_limited(self.account.id)
                    
                    if stream:
                        error_event = {
                            "type": "error",
                            "error": {
                                "type": "rate_limit_error",
                                "message": f"Account {self.account.id} rate-limited. Retry to use a different account."
                            }
                        }
                        class RateLimitErrorResponse:
                            status_code = 429
                            async def aiter_lines(self):
                                yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
                            async def aread(self):
                                return json.dumps({"message": f"Account {self.account.id} rate-limited. Retry to use a different account.", "reason": "RATE_LIMITED"}).encode('utf-8')
                            async def aclose(self):
                                pass
                        return RateLimitErrorResponse()
                    else:
                        raise HTTPException(
                            status_code=429,
                            detail=f"Account {self.account.id} rate-limited. Retry to use a different account."
                        )
                
                # 504 - gateway timeout, mark account as rate-limited and fail immediately
                # No retry needed - let the caller retry with a different account
                if response.status_code == 504:
                    logger.warning(f"Received 504 for account {self.account.id}, marking as rate-limited and failing immediately")
                    self.auth_manager.mark_rate_limited(self.account.id)
                    
                    if stream:
                        error_event = {
                            "type": "error",
                            "error": {
                                "type": "timeout_error",
                                "message": f"Account {self.account.id} gateway timeout. Retry to use a different account."
                            }
                        }
                        class TimeoutErrorResponse:
                            status_code = 504
                            async def aiter_lines(self):
                                yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
                            async def aread(self):
                                return json.dumps({"message": f"Account {self.account.id} gateway timeout. Retry to use a different account.", "reason": "GATEWAY_TIMEOUT"}).encode('utf-8')
                            async def aclose(self):
                                pass
                        return TimeoutErrorResponse()
                    else:
                        raise HTTPException(
                            status_code=504,
                            detail=f"Account {self.account.id} gateway timeout. Retry to use a different account."
                        )
                
                # Other 5xx - server error, wait and retry
                if 500 <= response.status_code < 600:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Received {response.status_code}, waiting {delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(delay)
                    continue
                
                # Other errors - return as is
                return response
                
            except httpx.TimeoutException as e:
                last_error = e
                
                # Classify timeout error for user-friendly messaging
                error_info = classify_network_error(e)
                last_error_info = error_info
                
                # Log with user-friendly message
                short_msg = get_short_error_message(error_info)
                
                if error_info.is_retryable and attempt < max_retries - 1:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"{short_msg} - waiting {delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"{short_msg} - no more retries (attempt {attempt + 1}/{max_retries})")
                    if not error_info.is_retryable:
                        break  # Don't retry non-retryable errors
                
            except httpx.RequestError as e:
                last_error = e
                
                # Classify the error for user-friendly messaging
                error_info = classify_network_error(e)
                last_error_info = error_info
                
                # Log with user-friendly message
                short_msg = get_short_error_message(error_info)
                
                if error_info.is_retryable and attempt < max_retries - 1:
                    delay = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"{short_msg} - waiting {delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"{short_msg} - no more retries (attempt {attempt + 1}/{max_retries})")
                    if not error_info.is_retryable:
                        break  # Don't retry non-retryable errors
        
        # All attempts exhausted - provide detailed, user-friendly error message
        if last_error_info:
            # Use classified error information
            error_message = last_error_info.user_message
            
            # Add troubleshooting steps
            if last_error_info.troubleshooting_steps:
                error_message += "\n\nTroubleshooting:\n"
                for i, step in enumerate(last_error_info.troubleshooting_steps, 1):
                    error_message += f"{i}. {step}\n"
            
            # Add technical details for debugging
            error_message += f"\nTechnical details: {last_error_info.technical_details}"
            
            if stream:
                error_event = {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": error_message.strip()
                    }
                }
                class ErrorResponseClassified:
                    status_code = last_error_info.suggested_http_code
                    async def aiter_lines(self):
                        yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
                    async def aread(self):
                        return json.dumps({"message": error_message.strip(), "reason": "RETRY_EXHAUSTED"}).encode('utf-8')
                    async def aclose(self):
                        pass
                return ErrorResponseClassified()
            else:
                raise HTTPException(
                    status_code=last_error_info.suggested_http_code,
                    detail=error_message.strip()
                )
        else:
            # Fallback if no error info was captured
            error_detail = f"Request failed after {max_retries} attempts."
            if last_error:
                error_detail += f" Last error: {type(last_error).__name__}: {str(last_error)}"
                logger.error(f"Request failed with unclassified error: {error_detail}")
            else:
                error_detail += " No error details available."
                logger.error(f"Request failed without capturing error details")
            
            if stream:
                error_event = {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": error_detail
                    }
                }
                class ErrorResponse:
                    status_code = 504
                    async def aiter_lines(self):
                        yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
                    async def aread(self):
                        return json.dumps({"message": error_detail, "reason": "RETRY_EXHAUSTED"}).encode('utf-8')
                    async def aclose(self):
                        pass
                return ErrorResponse()
            else:
                raise HTTPException(
                    status_code=502,
                    detail=error_detail
                )
    
    async def __aenter__(self) -> "KiroHttpClient":
        """Async context manager support."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Closes the client when exiting context."""
        await self.close()