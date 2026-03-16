# -*- coding: utf-8 -*-
"""
Account manager for Kiro Gateway.

Manages multiple accounts and API keys stored in a SQLite database.
Supports round-robin selection, CRUD operations, and token refresh for kiro-type accounts.
"""

import asyncio
import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
from loguru import logger


DEFAULT_REGION = "us-east-1"
KIRO_VERSION = "0.8.140"


@dataclass
class Account:
    """Represents a single account stored in the database.

    Attributes:
        id: Primary key.
        type: Account type, e.g. "kiro".
        priority: Higher value = higher priority in round-robin.
        config: Parsed JSON credentials dict.
        limit: Total usage limit (0 = unlimited).
        usage: Current usage amount.
    """

    id: int
    type: str
    priority: int
    config: Dict[str, Any]
    limit: int
    usage: float
    email: Optional[str] = None
    expires_at: Optional[str] = None
    next_reset_at: Optional[int] = None


@dataclass
class ApiKey:
    """Represents an API key for accessing the gateway.

    Attributes:
        id: Primary key.
        key: The actual API key string.
        name: Human-readable name/description.
        created_at: ISO 8601 timestamp of creation.
    """

    id: int
    key: str
    name: str
    created_at: str
    duration_ms: Optional[int] = None
    duration_ms: Optional[int] = None


@dataclass
class AdminUser:
    """Represents an admin user for web UI access.

    Attributes:
        id: Primary key.
        username: Login username.
        password_hash: SHA256 hash of password.
        created_at: ISO 8601 timestamp of creation.
    """

    id: int
    username: str
    password_hash: str
    created_at: str
    duration_ms: Optional[int] = None
    duration_ms: Optional[int] = None


@dataclass
class RequestLog:
    """Represents a request log entry.

    Attributes:
        id: Primary key.
        api_key_id: Foreign key to api_keys table (nullable).
        account_id: Foreign key to accounts table (nullable).
        model: Model name used.
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.
        status: Request status (success/error).
        channel: Channel type (openai/anthropic).
        created_at: ISO 8601 timestamp of request.
    """

    id: int
    api_key_id: Optional[int]
    account_id: Optional[int]
    model: str
    input_tokens: int
    output_tokens: int
    status: str
    channel: str
    created_at: str
    duration_ms: Optional[int] = None


def _build_kiro_headers(access_token: str) -> dict:
    """Build HTTP headers for Kiro API requests.

    Args:
        access_token: Bearer token.

    Returns:
        Headers dict.
    """
    machine_id = uuid.uuid4().hex
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "amz-sdk-request": "attempt=1; max=1",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "x-amzn-kiro-agent-mode": "vibe",
        "x-amz-user-agent": f"aws-sdk-js/1.0.0 KiroIDE-{KIRO_VERSION}-{machine_id}",
        "user-agent": f"aws-sdk-js/1.0.0 ua/2.1 os/windows lang/js md/nodejs api/codewhispererruntime#1.0.0 m/E KiroIDE-{KIRO_VERSION}-{machine_id}",
    }


def _is_token_expired(config: dict) -> bool:
    """Check whether the access token in config is expired.

    Mirrors the logic from AiHub/providers/kiro.py::_is_token_expired.

    Args:
        config: Credentials dict with refreshedAt/expiresIn or expiresAt fields.

    Returns:
        True if expired or expiry cannot be determined.
    """
    refreshed_at = config.get("refreshedAt", 0)
    expires_in = config.get("expiresIn", 3600)

    if refreshed_at == 0 and "expiresAt" in config:
        try:
            expires_at_str = config.get("expiresAt")
            if expires_at_str:
                expires_at_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                expires_at_timestamp = int(expires_at_dt.timestamp())
                refreshed_at = expires_at_timestamp - expires_in
        except Exception as e:
            logger.warning(f"Failed to parse expiresAt from credentials: {e}")

    if refreshed_at == 0:
        return True

    current_time = int(datetime.now(timezone.utc).timestamp())
    expiry_time = refreshed_at + expires_in - 60
    return current_time >= expiry_time


async def _refresh_kiro_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    region: str,
) -> Optional[dict]:
    """Refresh a Kiro access token via AWS SSO OIDC.

    Args:
        refresh_token: Current refresh token.
        client_id: OAuth client ID.
        client_secret: OAuth client secret.
        region: AWS region for the OIDC endpoint.

    Returns:
        Dict with accessToken, expiresIn, refreshedAt on success; None on failure.
    """
    sso_url = f"https://oidc.{region}.amazonaws.com/token"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                sso_url,
                json={
                    "clientId": client_id,
                    "clientSecret": client_secret,
                    "refreshToken": refresh_token,
                    "grantType": "refresh_token",
                },
                headers={"Content-Type": "application/json"},
            )
            if response.status_code == 200:
                data = response.json()
                new_access_token = data.get("accessToken")
                if new_access_token:
                    return {
                        "accessToken": new_access_token,
                        "expiresIn": data.get("expiresIn", 3600),
                        "refreshedAt": int(datetime.now(timezone.utc).timestamp()),
                    }
                logger.error(f"Token refresh response missing accessToken. Response: {response.text}")
                return None
            logger.error(f"Token refresh failed - HTTP {response.status_code}: {response.text}")
            return None
    except httpx.TimeoutException as e:
        logger.error(f"Token refresh timeout: {e}. URL: {sso_url}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Token refresh network error: {e}. URL: {sso_url}")
        return None
    except Exception as e:
        logger.error(f"Token refresh unexpected error: {type(e).__name__}: {e}", exc_info=True)
        return None


class AccountManager:
    """Manages multiple accounts with round-robin selection and token lifecycle.

    Accounts are persisted in a SQLite database. On each call to
    get_access_token() the manager picks the next available account
    (sorted by priority DESC, skipping exhausted ones) and ensures its
    token is valid before returning it.

    Args:
        db_path: Path to the SQLite database file.
    """

    _CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS accounts (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            type     TEXT    NOT NULL DEFAULT 'kiro',
            priority INTEGER NOT NULL DEFAULT 0,
            config   TEXT    NOT NULL,
            limit_   INTEGER NOT NULL DEFAULT 0,
            usage    REAL    NOT NULL DEFAULT 0
        )
    """

    _CREATE_API_KEYS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS api_keys (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            key        TEXT    NOT NULL UNIQUE,
            name       TEXT    NOT NULL,
            created_at TEXT    NOT NULL
        )
    """

    _CREATE_ADMIN_USERS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS admin_users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL
        )
    """

    _CREATE_REQUEST_LOGS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS request_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id    INTEGER,
            account_id    INTEGER,
            model         TEXT    NOT NULL,
            input_tokens  INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            status        TEXT    NOT NULL,
            channel       TEXT    NOT NULL,
            created_at    TEXT    NOT NULL,
            FOREIGN KEY (api_key_id) REFERENCES api_keys(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """

    _CREATE_REQUEST_LOGS_INDEX_SQL = """
        CREATE INDEX IF NOT EXISTS idx_request_logs_created_at 
        ON request_logs(created_at DESC)
    """

    _CREATE_SESSIONS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS sessions (
            session_token TEXT    PRIMARY KEY,
            username      TEXT    NOT NULL,
            created_at    TEXT    NOT NULL,
            expires_at    TEXT    NOT NULL
        )
    """

    _CREATE_SESSIONS_INDEX_SQL = """
        CREATE INDEX IF NOT EXISTS idx_sessions_expires_at 
        ON sessions(expires_at)
    """

    _CREATE_MODELS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS models (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_type TEXT    NOT NULL,
            model_id      TEXT    NOT NULL,
            display_name  TEXT,
            enabled       INTEGER NOT NULL DEFAULT 1,
            priority      INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT    NOT NULL,
            updated_at    TEXT    NOT NULL,
            UNIQUE(provider_type, model_id)
        )
    """

    _CREATE_MODELS_INDEX_SQL = """
        CREATE INDEX IF NOT EXISTS idx_models_provider_type 
        ON models(provider_type, enabled)
    """

    def __init__(self, db_path: str = "accounts.db") -> None:
        self._db_path = str(Path(db_path).expanduser())
        self._lock = asyncio.Lock()
        self._cursor_index: int = 0
        self._token_cache: Dict[int, Tuple[str, float]] = {}  # account_id -> (token, expiry_timestamp)
        self._init_db()

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create the accounts, api_keys, admin_users, and request_logs tables if they do not exist."""
        try:
            with self._connect() as conn:
                conn.execute(self._CREATE_TABLE_SQL)
                conn.execute(self._CREATE_API_KEYS_TABLE_SQL)
                conn.execute(self._CREATE_ADMIN_USERS_TABLE_SQL)
                conn.execute(self._CREATE_REQUEST_LOGS_TABLE_SQL)
                conn.execute(self._CREATE_REQUEST_LOGS_INDEX_SQL)
                conn.execute(self._CREATE_SESSIONS_TABLE_SQL)
                conn.execute(self._CREATE_SESSIONS_INDEX_SQL)
                conn.execute(self._CREATE_MODELS_TABLE_SQL)
                conn.execute(self._CREATE_MODELS_INDEX_SQL)
                
                # Add new fields to accounts table if they don't exist
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(accounts)")
                columns = [col[1] for col in cursor.fetchall()]
                
                if "email" not in columns:
                    conn.execute("ALTER TABLE accounts ADD COLUMN email TEXT")
                    logger.info("Added 'email' column to accounts table")
                
                if "expires_at" not in columns:
                    conn.execute("ALTER TABLE accounts ADD COLUMN expires_at TEXT")
                    logger.info("Added 'expires_at' column to accounts table")
                
                if "next_reset_at" not in columns:
                    conn.execute("ALTER TABLE accounts ADD COLUMN next_reset_at INTEGER")
                    logger.info("Added 'next_reset_at' column to accounts table")
                
                
                # Add duration_ms field to request_logs table if it doesn't exist
                cursor.execute("PRAGMA table_info(request_logs)")
                log_columns = [col[1] for col in cursor.fetchall()]
                
                if "duration_ms" not in log_columns:
                    conn.execute("ALTER TABLE request_logs ADD COLUMN duration_ms INTEGER")
                    logger.info("Added 'duration_ms' column to request_logs table")
                
                conn.commit()
            logger.info(f"AccountManager initialized with database: {self._db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize accounts database: {e}")
            raise

    def _row_to_account(self, row: sqlite3.Row) -> Account:
        config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        
        # Get optional fields, handling cases where they might not exist
        try:
            email = row["email"]
        except (KeyError, IndexError):
            email = None
        
        try:
            expires_at = row["expires_at"]
        except (KeyError, IndexError):
            expires_at = None
        
        try:
            next_reset_at = row["next_reset_at"]
        except (KeyError, IndexError):
            next_reset_at = None
        
        return Account(
            id=row["id"],
            type=row["type"],
            priority=row["priority"],
            config=config,
            limit=row["limit_"],
            usage=row["usage"],
            email=email,
            expires_at=expires_at,
            next_reset_at=next_reset_at,
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_accounts(self) -> List[Account]:
        """Return all accounts sorted by priority DESC.

        Returns:
            List of Account objects.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM accounts ORDER BY priority DESC"
            ).fetchall()
        return [self._row_to_account(r) for r in rows]

    def get_account(self, account_id: int) -> Account:
        """Fetch a single account by ID.

        Args:
            account_id: Account primary key.

        Returns:
            Account object.

        Raises:
            KeyError: If account not found.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Account {account_id} not found")
        return self._row_to_account(row)

    async def get_account_by_type(self, account_type: str) -> Optional[Account]:
        """
        Get an available account of the specified type.
        
        Selects accounts by:
        1. Filter by type
        2. Sort by priority DESC, usage ASC
        3. Return first account that hasn't exceeded limit
        
        Args:
            account_type: Account type ("kiro", "glm", etc.)
        
        Returns:
            Account object or None if no available account
        """
        async with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM accounts 
                    WHERE type = ?
                    ORDER BY priority DESC, usage ASC
                    """,
                    (account_type,)
                ).fetchall()
            
            if not rows:
                logger.warning(f"No accounts found for type '{account_type}'")
                return None
            
            logger.info(f"Found {len(rows)} account(s) for type '{account_type}'")
            
            # Find first account that hasn't exceeded limit
            for idx, row in enumerate(rows):
                account = self._row_to_account(row)
                threshold = account.limit - 1
                is_unlimited = account.limit == 0
                is_available = account.usage < threshold
                
                logger.info(
                    f"Account #{idx+1}: id={account.id}, "
                    f"usage={account.usage:.2f}, limit={account.limit}, "
                    f"threshold={threshold}, unlimited={is_unlimited}, "
                    f"available={is_available or is_unlimited}"
                )
                
                # limit = 0 means unlimited
                # Filter out accounts where usage >= limit - 1 to prevent quota errors
                if is_unlimited or is_available:
                    logger.info(f"Selected account {account.id} (usage={account.usage:.2f}, limit={account.limit})")
                    return account
            
            # All accounts exceeded limit
            logger.warning(f"All accounts for type '{account_type}' have exceeded their limits")
            return None

    def create_account(
        self,
        type: str = "kiro",
        priority: int = 0,
        config: Optional[Dict[str, Any]] = None,
        limit: int = 0,
    ) -> Account:
        """Create a new account.

        Args:
            type: Account type (default "kiro").
            priority: Scheduling priority (higher = preferred).
            config: Credentials dict (will be JSON-serialised).
            limit: Total usage limit (0 = unlimited).

        Returns:
            Newly created Account.
        """
        config = config or {}
        config_json = json.dumps(config, ensure_ascii=False)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO accounts (type, priority, config, limit_, usage) VALUES (?, ?, ?, ?, ?)",
                (type, priority, config_json, limit, 0.0),
            )
            conn.commit()
            account_id = cursor.lastrowid
        logger.info(f"Created account id={account_id} type={type} priority={priority}")
        return self.get_account(account_id)

    def update_account(self, account_id: int, **kwargs: Any) -> Account:
        """Update account fields.

        Supported kwargs: type, priority, config (dict), limit, usage.

        Args:
            account_id: Account primary key.
            **kwargs: Fields to update.

        Returns:
            Updated Account.

        Raises:
            KeyError: If account not found.
            ValueError: If no valid fields provided.
        """
        # Ensure account exists
        self.get_account(account_id)

        field_map = {
            "type": "type",
            "priority": "priority",
            "config": "config",
            "limit": "limit_",
            "usage": "usage",
        }
        sets = []
        values = []
        for key, col in field_map.items():
            if key in kwargs:
                val = kwargs[key]
                if key == "config":
                    val = json.dumps(val, ensure_ascii=False)
                sets.append(f"{col} = ?")
                values.append(val)

        if not sets:
            raise ValueError("No valid fields provided for update")

        values.append(account_id)
        sql = f"UPDATE accounts SET {', '.join(sets)} WHERE id = ?"
        with self._connect() as conn:
            conn.execute(sql, values)
            conn.commit()
        logger.info(f"Updated account id={account_id} fields={list(kwargs.keys())}")
        return self.get_account(account_id)

    def delete_account(self, account_id: int) -> None:
        """Delete an account.

        Args:
            account_id: Account primary key.

        Raises:
            KeyError: If account not found.
        """
        self.get_account(account_id)  # raises KeyError if missing
        with self._connect() as conn:
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            conn.commit()
        logger.info(f"Deleted account id={account_id}")

    def update_usage(self, account_id: int, usage: float) -> None:
        """Update the usage field for an account.

        Args:
            account_id: Account primary key.
            usage: New usage value.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET usage = ? WHERE id = ?", (usage, account_id)
            )
            conn.commit()

    def increment_usage(self, account_id: int, delta: float) -> None:
        """Atomically increment the usage field for an account.

        Args:
            account_id: Account primary key.
            delta: Amount to add to current usage.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET usage = usage + ? WHERE id = ?", (delta, account_id)
            )
            conn.commit()

    def _persist_config(self, account_id: int, config: dict) -> None:
        """Write updated config JSON back to the database.

        Args:
            account_id: Account primary key.
            config: Updated credentials dict.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET config = ? WHERE id = ?",
                (json.dumps(config, ensure_ascii=False), account_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _get_cached_token(self, account_id: int) -> Optional[str]:
        """Get cached token if still valid.
        
        Args:
            account_id: Account ID.
            
        Returns:
            Cached token if valid, None otherwise.
        """
        if account_id in self._token_cache:
            token, expiry = self._token_cache[account_id]
            # Check if token expires in more than 60 seconds
            if time.time() < expiry - 60:
                return token
        return None
    
    def _cache_token(self, account_id: int, token: str, expires_in: int) -> None:
        """Cache a token with its expiry time.
        
        Args:
            account_id: Account ID.
            token: Access token.
            expires_in: Token lifetime in seconds.
        """
        expiry = time.time() + expires_in
        self._token_cache[account_id] = (token, expiry)

    async def _ensure_valid_token_kiro(self, account: Account) -> Optional[str]:
        """Ensure the kiro account has a valid access token, refreshing if needed.

        Args:
            account: Account with type="kiro".

        Returns:
            Valid access token, or None if unavailable.
        """
        # Check cache first (fast path, no lock needed)
        cached_token = self._get_cached_token(account.id)
        if cached_token:
            return cached_token
        
        config = account.config
        access_token = config.get("accessToken") or config.get("access_token")
        refresh_token = config.get("refreshToken") or config.get("refresh_token")
        client_id = config.get("clientId") or config.get("client_id")
        client_secret = config.get("clientSecret") or config.get("client_secret")
        region = config.get("region") or DEFAULT_REGION

        can_refresh = bool(refresh_token and client_id and client_secret)

        if _is_token_expired(config) and can_refresh:
            logger.info(f"Account {account.id}: access token expired, refreshing...")
            result = await _refresh_kiro_token(refresh_token, client_id, client_secret, region)
            if result:
                config["accessToken"] = result["accessToken"]
                config["expiresIn"] = result["expiresIn"]
                config["refreshedAt"] = result["refreshedAt"]
                self._persist_config(account.id, config)
                account.config = config
                # Cache the new token
                self._cache_token(account.id, result["accessToken"], result["expiresIn"])
                logger.info(f"Account {account.id}: token refreshed successfully")
                return config["accessToken"]
            return None

        if not access_token and can_refresh:
            result = await _refresh_kiro_token(refresh_token, client_id, client_secret, region)
            if result:
                config["accessToken"] = result["accessToken"]
                config["expiresIn"] = result["expiresIn"]
                config["refreshedAt"] = result["refreshedAt"]
                self._persist_config(account.id, config)
                account.config = config
                # Cache the new token
                self._cache_token(account.id, result["accessToken"], result["expiresIn"])
                return config["accessToken"]
            return None

        # Cache existing valid token
        if access_token:
            expires_in = config.get("expiresIn", 3600)
            self._cache_token(account.id, access_token, expires_in)
        
        return access_token

    async def _get_token_for_account(self, account: Account) -> Optional[str]:
        """Get a valid token for any account type.

        Args:
            account: Account to get token for.

        Returns:
            Access token string, or None if unavailable.
        """
        if account.type == "kiro":
            return await self._ensure_valid_token_kiro(account)
        logger.warning(f"Account {account.id}: unsupported type '{account.type}'")
        return None

    async def get_access_token(self) -> Tuple[str, Account]:
        """Return a valid access token and the account it belongs to.

        Iterates accounts sorted by priority DESC in round-robin fashion,
        skipping accounts that have exceeded their usage limit.

        Returns:
            Tuple of (access_token, account).

        Raises:
            RuntimeError: If no accounts are configured or all are exhausted.
        """
        async with self._lock:
            accounts = self.list_accounts()
            if not accounts:
                raise RuntimeError(
                    "No accounts configured. Add at least one account via POST /admin/accounts."
                )

            available = [
                a for a in accounts
                if a.limit == 0 or a.usage < a.limit - 1
            ]
            if not available:
                raise RuntimeError(
                    "All accounts have reached their usage limit."
                )

            # Round-robin over available accounts
            self._cursor_index = self._cursor_index % len(available)
            for _ in range(len(available)):
                account = available[self._cursor_index % len(available)]
                self._cursor_index = (self._cursor_index + 1) % len(available)

                token = await self._get_token_for_account(account)
                if token:
                    return token, account
                logger.warning(f"Account {account.id}: could not obtain token, skipping")

            raise RuntimeError(
                "Could not obtain a valid token from any account. "
                "Check account credentials and refresh tokens."
            )

    async def force_refresh(self, account: Account) -> str:
        """Force a token refresh for the given account.

        Args:
            account: Account to refresh.

        Returns:
            New access token.

        Raises:
            RuntimeError: If refresh fails.
        """
        async with self._lock:
            # Reload fresh config from DB
            fresh = self.get_account(account.id)
            config = fresh.config
            refresh_token = config.get("refreshToken") or config.get("refresh_token")
            client_id = config.get("clientId") or config.get("client_id")
            client_secret = config.get("clientSecret") or config.get("client_secret")
            region = config.get("region") or DEFAULT_REGION

            if fresh.type == "kiro":
                if not (refresh_token and client_id and client_secret):
                    logger.error(
                        f"Account {account.id}: missing refresh credentials for force refresh. "
                        f"Has refresh_token: {bool(refresh_token)}, client_id: {bool(client_id)}, client_secret: {bool(client_secret)}"
                    )
                    raise RuntimeError(
                        f"Account {account.id}: missing refresh credentials for force refresh"
                    )
                result = await _refresh_kiro_token(refresh_token, client_id, client_secret, region)
                if result:
                    config["accessToken"] = result["accessToken"]
                    config["expiresIn"] = result["expiresIn"]
                    config["refreshedAt"] = result["refreshedAt"]
                    self._persist_config(fresh.id, config)
                    account.config = config
                    logger.info(f"Account {account.id}: token refreshed successfully")
                    return config["accessToken"]
                # Token refresh failed - detailed error already logged in _refresh_kiro_token
                logger.warning(f"Account {account.id}: token refresh failed, see detailed error above")
                raise RuntimeError(f"Account {account.id}: token refresh failed")

            logger.error(f"Account {account.id}: force_refresh not supported for type '{fresh.type}'")
            raise RuntimeError(f"Account {account.id}: force_refresh not supported for type '{fresh.type}'")

    # ------------------------------------------------------------------
    # Usage refresh
    # ------------------------------------------------------------------

    async def refresh_usage(self, account: Account) -> Tuple[float, float]:
        """Fetch current usage and limit from the Kiro API and persist them.

        Mirrors AiHub/providers/kiro.py::refresh_usage.

        Args:
            account: Account to refresh usage for.

        Returns:
            Tuple of (used, limit).

        Raises:
            RuntimeError: If the account type is unsupported or request fails.
        """
        if account.type != "kiro":
            raise RuntimeError(f"refresh_usage not supported for type '{account.type}'")

        token = await self._get_token_for_account(account)
        if not token:
            raise RuntimeError(f"Account {account.id}: cannot obtain token for usage refresh")

        config = account.config
        region = config.get("region") or DEFAULT_REGION
        profile_arn = config.get("profileArn") or config.get("profile_arn")

        usage_data = await self._request_usage_limits(token, region, profile_arn, account)
        used, limit = self._extract_kiro_points(usage_data)

        self.update_usage(account.id, float(used))
        if limit > 0:
            self.update_account(account.id, limit=limit)
        
        # Extract and store additional information from API response
        email = usage_data.get("userInfo", {}).get("email")
        next_reset_at = usage_data.get("nextDateReset")
        # expiresAt is in config, not in usage API response
        expires_at = config.get("expiresAt")
        
        # Update additional fields in database
        with self._connect() as conn:
            updates = []
            params = []
            
            if email:
                updates.append("email = ?")
                params.append(email)
            
            if expires_at:
                updates.append("expires_at = ?")
                params.append(expires_at)
            
            if next_reset_at:
                updates.append("next_reset_at = ?")
                params.append(int(next_reset_at))
            
            if updates:
                params.append(account.id)
                sql = f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?"
                conn.execute(sql, params)
                conn.commit()
                logger.debug(f"Account {account.id}: updated email={email}, expires_at={expires_at}, next_reset_at={next_reset_at}")

        logger.info(f"Account {account.id}: usage refreshed — used={used}, limit={limit}")
        return float(used), float(limit)

    async def _request_usage_limits(
        self,
        access_token: str,
        region: str,
        profile_arn: Optional[str],
        account: Account,
    ) -> dict:
        """Call the Kiro getUsageLimits endpoint.

        Args:
            access_token: Bearer token.
            region: AWS region.
            profile_arn: Optional profile ARN.
            account: Account (used for 403 retry with force_refresh).

        Returns:
            Raw usage data dict from the API.

        Raises:
            Exception: On HTTP error.
        """
        base_url = f"https://q.{region}.amazonaws.com/getUsageLimits"
        params: Dict[str, str] = {
            "isEmailRequired": "true",
            "origin": "AI_EDITOR",
            "resourceType": "AGENTIC_REQUEST",
        }
        if profile_arn:
            params["profileArn"] = profile_arn
        url = f"{base_url}?{urlencode(params)}"
        headers = _build_kiro_headers(access_token)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 403:
                # Try once more after force refresh
                new_token = await self.force_refresh(account)
                headers = _build_kiro_headers(new_token)
                response = await client.get(url, headers=headers)
            if response.status_code != 200:
                raise Exception(
                    f"Kiro usage limits error ({response.status_code}): {response.text}"
                )
            return response.json()

    @staticmethod
    def _extract_kiro_points(usage_data: dict) -> Tuple[int, int]:
        """Extract used and limit counts from Kiro usage API response.

        Args:
            usage_data: Raw response dict from getUsageLimits.

        Returns:
            Tuple of (used, limit) as integers.
        """
        if not usage_data:
            return 0, 0

        used_count = usage_data.get("usedCount")
        limit_count = usage_data.get("limitCount")
        if used_count is not None and limit_count is not None:
            return int(used_count), int(limit_count)

        breakdowns = usage_data.get("usageBreakdownList") or []
        candidate = None
        for item in breakdowns:
            if item.get("resourceType") == "AGENTIC_REQUEST":
                candidate = item
                break
        if not candidate:
            for item in breakdowns:
                if "agent" in (item.get("displayName") or "").lower():
                    candidate = item
                    break
        if not candidate and breakdowns:
            candidate = breakdowns[0]
        if not candidate:
            return 0, 0

        def _safe_float(val: Any) -> float:
            try:
                return float(val) if val is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        monthly_used = _safe_float(
            candidate.get("currentUsageWithPrecision") or candidate.get("currentUsage")
        )
        monthly_limit = _safe_float(
            candidate.get("usageLimitWithPrecision") or candidate.get("usageLimit")
        )

        ft_used = ft_limit = 0.0
        free_trial = candidate.get("freeTrialInfo")
        if free_trial:
            # Only count free trial usage/limit if not expired
            trial_status = free_trial.get("freeTrialStatus", "").upper()
            if trial_status == "ACTIVE":
                ft_used = _safe_float(
                    free_trial.get("currentUsageWithPrecision") or free_trial.get("currentUsage")
                )
                ft_limit = _safe_float(
                    free_trial.get("usageLimitWithPrecision") or free_trial.get("usageLimit")
                )
                logger.debug(f"Free trial active: used={ft_used}, limit={ft_limit}")
            elif trial_status == "EXPIRED":
                logger.info(f"Free trial expired, ignoring trial usage/limit")
            else:
                # Unknown or missing status - be conservative and don't count it
                logger.debug(f"Free trial status unknown or missing ('{trial_status}'), ignoring trial usage/limit")

        return int(monthly_used + ft_used), int(monthly_limit + ft_limit)

    # ------------------------------------------------------------------
    # API Key management
    # ------------------------------------------------------------------

    def generate_api_key(self, name: str = "Default Key") -> ApiKey:
        """Generate a new API key.

        Args:
            name: Human-readable name for the key.

        Returns:
            Newly created ApiKey.
        """
        key = f"sk-{secrets.token_urlsafe(32)}"
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO api_keys (key, name, created_at) VALUES (?, ?, ?)",
                (key, name, created_at),
            )
            conn.commit()
            key_id = cursor.lastrowid

        logger.info(f"Generated API key id={key_id} name={name}")
        return ApiKey(id=key_id, key=key, name=name, created_at=created_at)

    def list_api_keys(self) -> List[ApiKey]:
        """List all API keys.

        Returns:
            List of ApiKey objects.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, key, name, created_at FROM api_keys ORDER BY id DESC"
            ).fetchall()
        return [
            ApiKey(id=r["id"], key=r["key"], name=r["name"], created_at=r["created_at"])
            for r in rows
        ]

    def get_api_key(self, key_id: int) -> ApiKey:
        """Get a single API key by ID.

        Args:
            key_id: API key primary key.

        Returns:
            ApiKey object.

        Raises:
            KeyError: If key not found.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, key, name, created_at FROM api_keys WHERE id = ?", (key_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"API key {key_id} not found")
        return ApiKey(id=row["id"], key=row["key"], name=row["name"], created_at=row["created_at"])

    def delete_api_key(self, key_id: int) -> None:
        """Delete an API key.

        Args:
            key_id: API key primary key.

        Raises:
            KeyError: If key not found.
        """
        self.get_api_key(key_id)  # raises KeyError if missing
        with self._connect() as conn:
            conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            conn.commit()
        logger.info(f"Deleted API key id={key_id}")

    def verify_api_key(self, key: str) -> bool:
        """Check if an API key is valid.

        Args:
            key: API key string to verify.

        Returns:
            True if key exists in database, False otherwise.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM api_keys WHERE key = ?", (key,)
            ).fetchone()
        return row is not None

    
    def get_api_key_by_token(self, key: str) -> Optional[ApiKey]:
        """Get API key object by token string.

        Args:
            key: API key string.

        Returns:
            ApiKey object if found, None otherwise.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key = ?", (key,)
            ).fetchone()
        
        if row:
            return ApiKey(
                id=row["id"],
                key=row["key"],
                name=row["name"],
                created_at=row["created_at"]
            )
        return None

    # ------------------------------------------------------------------
    # Admin User management
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash a password using SHA256.

        Args:
            password: Plain text password.

        Returns:
            Hex digest of SHA256 hash.
        """
        return hashlib.sha256(password.encode()).hexdigest()

    def create_admin_user(self, username: str, password: str) -> AdminUser:
        """Create a new admin user.

        Args:
            username: Login username.
            password: Plain text password (will be hashed).

        Returns:
            Newly created AdminUser.

        Raises:
            ValueError: If username already exists.
        """
        password_hash = self._hash_password(password)
        created_at = datetime.now(timezone.utc).isoformat()

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, password_hash, created_at),
                )
                conn.commit()
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' already exists")

        logger.info(f"Created admin user id={user_id} username={username}")
        return AdminUser(id=user_id, username=username, password_hash=password_hash, created_at=created_at)

    def verify_admin_user(self, username: str, password: str) -> Optional[AdminUser]:
        """Verify admin user credentials.

        Args:
            username: Login username.
            password: Plain text password.

        Returns:
            AdminUser if credentials are valid, None otherwise.
        """
        password_hash = self._hash_password(password)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, created_at FROM admin_users WHERE username = ? AND password_hash = ?",
                (username, password_hash),
            ).fetchone()

        if row is None:
            return None

        return AdminUser(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )

    def list_admin_users(self) -> List[AdminUser]:
        """List all admin users.

        Returns:
            List of AdminUser objects.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, username, password_hash, created_at FROM admin_users ORDER BY id"
            ).fetchall()
        return [
            AdminUser(id=r["id"], username=r["username"], password_hash=r["password_hash"], created_at=r["created_at"])
            for r in rows
        ]

    def delete_admin_user(self, user_id: int) -> None:
        """Delete an admin user.

        Args:
            user_id: Admin user primary key.

        Raises:
            KeyError: If user not found.
        """
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM admin_users WHERE id = ?", (user_id,))
            conn.commit()
            if cursor.rowcount == 0:
                raise KeyError(f"Admin user {user_id} not found")
        logger.info(f"Deleted admin user id={user_id}")



    # ------------------------------------------------------------------
    # Request Logs
    # ------------------------------------------------------------------

    def log_request(
        self,
        api_key_id: Optional[int],
        account_id: Optional[int],
        model: str,
        input_tokens: int,
        output_tokens: int,
        status: str,
        channel: str,
        duration_ms: Optional[int] = None
    ) -> int:
        """Log a request to the database.

        Args:
            api_key_id: API key ID (nullable).
            account_id: Account ID (nullable).
            model: Model name.
            input_tokens: Input token count.
            output_tokens: Output token count.
            status: Request status (success/error).
            channel: Channel type (openai/anthropic).

        Returns:
            ID of the inserted log entry.
        """
        created_at = datetime.utcnow().isoformat() + "Z"
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO request_logs 
                (api_key_id, account_id, model, input_tokens, output_tokens, status, channel, created_at, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (api_key_id, account_id, model, input_tokens, output_tokens, status, channel, created_at, duration_ms)
            )
            conn.commit()
            log_id = cursor.lastrowid
        
        # Keep only the last 10000 records
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM request_logs 
                WHERE id NOT IN (
                    SELECT id FROM request_logs 
                    ORDER BY created_at DESC 
                    LIMIT 10000
                )
                """
            )
            conn.commit()
        
        return log_id

    def list_request_logs(
        self, 
        limit: int = 50, 
        offset: int = 0,
        search_model: Optional[str] = None,
        search_status: Optional[str] = None
    ) -> tuple:
        """List request logs with pagination and search.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            search_model: Filter by model name (partial match).
            search_status: Filter by status (exact match).

        Returns:
            Tuple of (list of log dicts with names, total count).
        """
        # Build WHERE clause
        where_clauses = []
        params = []
        
        if search_model:
            where_clauses.append("rl.model LIKE ?")
            params.append(f"%{search_model}%")
        
        if search_status:
            where_clauses.append("rl.status = ?")
            params.append(search_status)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        with self._connect() as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) as total FROM request_logs rl WHERE {where_sql}"
            total = conn.execute(count_query, params).fetchone()["total"]
            
            # Get logs with account and API key names
            query = f"""
                SELECT 
                    rl.*,
                    a.type as account_type,
                    ak.name as api_key_name
                FROM request_logs rl
                LEFT JOIN accounts a ON rl.account_id = a.id
                LEFT JOIN api_keys ak ON rl.api_key_id = ak.id
                WHERE {where_sql}
                ORDER BY rl.created_at DESC 
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(query, params + [limit, offset]).fetchall()
        
        logs = [
            {
                "id": row["id"],
                "api_key_id": row["api_key_id"],
                "api_key_name": row["api_key_name"] or f"Key #{row['api_key_id']}" if row["api_key_id"] else "N/A",
                "account_id": row["account_id"],
                "account_name": f"{row['account_type']} #{row['account_id']}" if row["account_id"] else "N/A",
                "model": row["model"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "status": row["status"],
                "channel": row["channel"],
                "created_at": row["created_at"],
                "duration_ms": row["duration_ms"] if "duration_ms" in row.keys() else None
            }
            for row in rows
        ]
        
        return logs, total

    def get_hourly_stats(self, hours: int = 24) -> List[dict]:
        """Get hourly usage statistics for the past 24 hours.

        Args:
            hours: Number of hours to look back (default: 24).

        Returns:
            List of dicts with date, requests, input_tokens, output_tokens.
        """
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat() + "Z"
        
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT 
                    strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                    COUNT(*) as requests,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens
                FROM request_logs
                WHERE created_at >= ?
                GROUP BY hour
                ORDER BY hour ASC
                """,
                (cutoff,)
            ).fetchall()
        
        return [
            {
                "hour": row["hour"] + "Z",  # Keep "hour" key for backward compatibility
                "requests": row["requests"],
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0
            }
            for row in rows
        ]

    def get_daily_stats(self, days: int = 30) -> List[dict]:
        """Get daily usage statistics for the past N days.

        Args:
            days: Number of days to look back (default: 30).

        Returns:
            List of dicts with date, requests, input_tokens, output_tokens.
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT 
                    strftime('%Y-%m-%d', created_at) as day,
                    COUNT(*) as requests,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens
                FROM request_logs
                WHERE created_at >= ?
                GROUP BY day
                ORDER BY day ASC
                """,
                (cutoff,)
            ).fetchall()
        
        return [
            {
                "day": row["day"],
                "requests": row["requests"],
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Session Management
    # ------------------------------------------------------------------

    def create_session(self, username: str, session_token: str, expires_in_days: int = 7) -> None:
        """Create a new session in the database.

        Args:
            username: Username for the session.
            session_token: Unique session token.
            expires_in_days: Number of days until session expires (default 7).
        """
        created_at = datetime.utcnow().isoformat() + "Z"
        expires_at = (datetime.utcnow() + timedelta(days=expires_in_days)).isoformat() + "Z"
        
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (session_token, username, created_at, expires_at)
            )
            conn.commit()
        
        logger.debug(f"Created session for user: {username}")

    def get_session(self, session_token: str) -> Optional[str]:
        """Get username from session token if valid.

        Args:
            session_token: Session token to validate.

        Returns:
            Username if session is valid and not expired, None otherwise.
        """
        now = datetime.utcnow().isoformat() + "Z"
        
        with self._connect() as conn:
            row = conn.execute(
                "SELECT username FROM sessions WHERE session_token = ? AND expires_at > ?",
                (session_token, now)
            ).fetchone()
        
        if row:
            return row["username"]
        return None

    def delete_session(self, session_token: str) -> None:
        """Delete a session from the database.

        Args:
            session_token: Session token to delete.
        """
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE session_token = ?",
                (session_token,)
            )
            conn.commit()
        
        logger.debug(f"Deleted session: {session_token[:8]}...")

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions from the database.

        Returns:
            Number of sessions deleted.
        """
        now = datetime.utcnow().isoformat() + "Z"
        
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (now,)
            )
            conn.commit()
            deleted = cursor.rowcount
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired sessions")
        
        return deleted

    # ------------------------------------------------------------------
    # Model Management
    # ------------------------------------------------------------------

    def list_models(
        self, 
        provider_type: Optional[str] = None, 
        enabled_only: bool = True
    ) -> List[dict]:
        """List models with optional filtering.

        Args:
            provider_type: Filter by provider type (e.g., 'kiro', 'glm'). None = all providers.
            enabled_only: If True, only return enabled models.

        Returns:
            List of model dicts with all fields.
        """
        with self._connect() as conn:
            query = "SELECT * FROM models WHERE 1=1"
            params = []
            
            if provider_type:
                query += " AND provider_type = ?"
                params.append(provider_type)
            
            if enabled_only:
                query += " AND enabled = 1"
            
            query += " ORDER BY provider_type, priority DESC, model_id"
            
            rows = conn.execute(query, params).fetchall()
        
        return [
            {
                "id": row["id"],
                "provider_type": row["provider_type"],
                "model_id": row["model_id"],
                "display_name": row["display_name"],
                "enabled": bool(row["enabled"]),
                "priority": row["priority"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_model(self, model_id: int) -> dict:
        """Get a single model by database ID.

        Args:
            model_id: Model primary key.

        Returns:
            Model dict.

        Raises:
            KeyError: If model not found.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM models WHERE id = ?", (model_id,)
            ).fetchone()
        
        if row is None:
            raise KeyError(f"Model {model_id} not found")
        
        return {
            "id": row["id"],
            "provider_type": row["provider_type"],
            "model_id": row["model_id"],
            "display_name": row["display_name"],
            "enabled": bool(row["enabled"]),
            "priority": row["priority"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_model(
        self,
        provider_type: str,
        model_id: str,
        display_name: Optional[str] = None,
        enabled: bool = True,
        priority: int = 0,
    ) -> dict:
        """Create a new model.

        Args:
            provider_type: Provider type (e.g., 'kiro', 'glm').
            model_id: Model identifier.
            display_name: Optional display name.
            enabled: Whether model is enabled.
            priority: Priority for sorting (higher = higher priority).

        Returns:
            Created model dict.

        Raises:
            ValueError: If model already exists for this provider.
        """
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO models 
                    (provider_type, model_id, display_name, enabled, priority, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (provider_type, model_id, display_name, int(enabled), priority, now, now),
                )
                conn.commit()
                db_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(
                f"Model '{model_id}' already exists for provider '{provider_type}'"
            )
        
        logger.info(f"Created model: {provider_type}/{model_id} (id={db_id})")
        return self.get_model(db_id)

    def update_model(self, model_id: int, **kwargs: Any) -> dict:
        """Update model fields.

        Supported kwargs: display_name, enabled, priority.

        Args:
            model_id: Model primary key.
            **kwargs: Fields to update.

        Returns:
            Updated model dict.

        Raises:
            KeyError: If model not found.
            ValueError: If no valid fields provided.
        """
        # Ensure model exists
        self.get_model(model_id)
        
        allowed_fields = {
            "display_name": "display_name",
            "enabled": "enabled",
            "priority": "priority",
        }
        
        sets = []
        values = []
        
        for key, col in allowed_fields.items():
            if key in kwargs:
                val = kwargs[key]
                if key == "enabled":
                    val = int(bool(val))
                sets.append(f"{col} = ?")
                values.append(val)
        
        if not sets:
            raise ValueError("No valid fields provided for update")
        
        # Always update updated_at
        sets.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        
        values.append(model_id)
        sql = f"UPDATE models SET {', '.join(sets)} WHERE id = ?"
        
        with self._connect() as conn:
            conn.execute(sql, values)
            conn.commit()
        
        logger.info(f"Updated model id={model_id} fields={list(kwargs.keys())}")
        return self.get_model(model_id)

    def delete_model(self, model_id: int) -> None:
        """Delete a model.

        Args:
            model_id: Model primary key.

        Raises:
            KeyError: If model not found.
        """
        self.get_model(model_id)  # raises KeyError if missing
        
        with self._connect() as conn:
            conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
            conn.commit()
        
        logger.info(f"Deleted model id={model_id}")

    def get_models_by_provider(self, provider_type: str) -> List[str]:
        """Get list of enabled model IDs for a specific provider.

        Args:
            provider_type: Provider type (e.g., 'kiro', 'glm').

        Returns:
            List of model_id strings (only enabled models).
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT model_id FROM models 
                WHERE provider_type = ? AND enabled = 1
                ORDER BY priority DESC, model_id
                """,
                (provider_type,)
            ).fetchall()
        
        return [row["model_id"] for row in rows]

    def count_models(self) -> int:
        """Count total number of models in database.

        Returns:
            Total model count.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM models").fetchone()
        
        return row["count"] if row else 0
