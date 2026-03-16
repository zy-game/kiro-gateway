# -*- coding: utf-8 -*-
"""
Database abstraction layer for Kiro Gateway.

Provides a unified interface for all database operations, eliminating
direct SQLite calls scattered throughout the codebase.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

from loguru import logger


class Database:
    """Database abstraction layer with connection management and CRUD operations.
    
    Provides:
    - Connection management with automatic cleanup
    - Context manager support for safe resource handling
    - Basic CRUD methods (execute, fetch_one, fetch_all, insert, update, delete)
    - Transaction support
    - Error handling for connection issues
    
    Args:
        db_path: Path to the SQLite database file.
        timeout: Connection timeout in seconds (default: 5.0).
    
    Example:
        # Using context manager
        with Database("accounts.db") as db:
            result = db.fetch_one("SELECT * FROM accounts WHERE id = ?", (1,))
        
        # Direct usage
        db = Database("accounts.db")
        results = db.fetch_all("SELECT * FROM accounts")
    """
    
    def __init__(self, db_path: str, timeout: float = 5.0) -> None:
        """Initialize database connection manager.
        
        Args:
            db_path: Path to the SQLite database file.
            timeout: Connection timeout in seconds.
        """
        self._db_path = str(Path(db_path).expanduser())
        self._timeout = timeout
        self._conn: Optional[sqlite3.Connection] = None
        self._in_transaction: bool = False
    
    def _connect(self) -> sqlite3.Connection:
        """Create a new database connection.
        
        Returns:
            SQLite connection with row factory configured.
        
        Raises:
            sqlite3.Error: If connection fails.
        """
        try:
            conn = sqlite3.connect(self._db_path, timeout=self._timeout)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database at {self._db_path}: {e}")
            raise
    
    def __enter__(self) -> "Database":
        """Enter context manager - establish connection.
        
        Returns:
            Self for use in with statement.
        """
        self._conn = self._connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager - close connection.
        
        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception value if an error occurred.
            exc_tb: Exception traceback if an error occurred.
        """
        if self._conn:
            self._conn.close()
            self._conn = None
    
    # ------------------------------------------------------------------
    # Basic CRUD methods
    # ------------------------------------------------------------------
    
    def execute(
        self, 
        query: str, 
        params: Optional[Tuple[Any, ...]] = None,
        commit: bool = True
    ) -> sqlite3.Cursor:
        """Execute a SQL query with optional parameters.
        
        Args:
            query: SQL query string.
            params: Query parameters tuple.
            commit: Whether to commit after execution (default: True).
                   Note: Commits are skipped when inside a transaction() block.
        
        Returns:
            Cursor object with query results.
        
        Raises:
            sqlite3.Error: If query execution fails.
            RuntimeError: If called outside context manager without connection.
        """
        params = params or ()
        
        # Use existing connection if in context manager, otherwise create temporary one
        if self._conn:
            cursor = self._conn.execute(query, params)
            # Only commit if requested AND not inside a transaction
            # (transaction() will handle commit/rollback)
            if commit and not self._in_transaction:
                self._conn.commit()
            return cursor
        else:
            # Temporary connection for standalone usage
            with self._connect() as conn:
                cursor = conn.execute(query, params)
                if commit:
                    conn.commit()
                return cursor
    
    def fetch_one(
        self, 
        query: str, 
        params: Optional[Tuple[Any, ...]] = None
    ) -> Optional[sqlite3.Row]:
        """Fetch a single row from the database.
        
        Args:
            query: SQL query string.
            params: Query parameters tuple.
        
        Returns:
            Single row as sqlite3.Row, or None if no results.
        
        Example:
            row = db.fetch_one("SELECT * FROM accounts WHERE id = ?", (1,))
            if row:
                print(row["type"], row["priority"])
        """
        params = params or ()
        
        if self._conn:
            return self._conn.execute(query, params).fetchone()
        else:
            with self._connect() as conn:
                return conn.execute(query, params).fetchone()
    
    def fetch_all(
        self, 
        query: str, 
        params: Optional[Tuple[Any, ...]] = None
    ) -> List[sqlite3.Row]:
        """Fetch all rows from the database.
        
        Args:
            query: SQL query string.
            params: Query parameters tuple.
        
        Returns:
            List of rows as sqlite3.Row objects.
        
        Example:
            rows = db.fetch_all("SELECT * FROM accounts WHERE type = ?", ("kiro",))
            for row in rows:
                print(row["id"], row["priority"])
        """
        params = params or ()
        
        if self._conn:
            return self._conn.execute(query, params).fetchall()
        else:
            with self._connect() as conn:
                return conn.execute(query, params).fetchall()
    
    def insert(
        self, 
        table: str, 
        data: Dict[str, Any]
    ) -> int:
        """Insert a row into a table.
        
        Args:
            table: Table name.
            data: Dictionary of column names to values.
        
        Returns:
            ID of the inserted row (lastrowid).
        
        Example:
            account_id = db.insert("accounts", {
                "type": "kiro",
                "priority": 10,
                "config": "{}",
                "limit_": 0,
                "usage": 0.0
            })
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        cursor = self.execute(query, tuple(data.values()), commit=True)
        return cursor.lastrowid
    
    def update(
        self, 
        table: str, 
        data: Dict[str, Any], 
        where: str, 
        where_params: Optional[Tuple[Any, ...]] = None
    ) -> int:
        """Update rows in a table.
        
        Args:
            table: Table name.
            data: Dictionary of column names to new values.
            where: WHERE clause (without "WHERE" keyword).
            where_params: Parameters for WHERE clause.
        
        Returns:
            Number of rows affected.
        
        Example:
            rows_updated = db.update(
                "accounts",
                {"usage": 100.0, "priority": 5},
                "id = ?",
                (1,)
            )
        """
        where_params = where_params or ()
        
        set_clause = ", ".join(f"{col} = ?" for col in data.keys())
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"
        
        params = tuple(data.values()) + where_params
        cursor = self.execute(query, params, commit=True)
        return cursor.rowcount
    
    def delete(
        self, 
        table: str, 
        where: str, 
        where_params: Optional[Tuple[Any, ...]] = None
    ) -> int:
        """Delete rows from a table.
        
        Args:
            table: Table name.
            where: WHERE clause (without "WHERE" keyword).
            where_params: Parameters for WHERE clause.
        
        Returns:
            Number of rows deleted.
        
        Example:
            rows_deleted = db.delete("accounts", "id = ?", (1,))
        """
        where_params = where_params or ()
        
        query = f"DELETE FROM {table} WHERE {where}"
        cursor = self.execute(query, where_params, commit=True)
        return cursor.rowcount
    
    # ------------------------------------------------------------------
    # Transaction support
    # ------------------------------------------------------------------
    
    @contextmanager
    def transaction(self):
        """Context manager for atomic database transactions.
        
        Provides transaction support with automatic commit on success
        and rollback on exception. All operations within the transaction
        block are executed atomically.
        
        Yields:
            Database instance for chaining operations.
        
        Raises:
            RuntimeError: If called outside context manager without connection.
            sqlite3.Error: If transaction operations fail.
        
        Example:
            with Database("accounts.db") as db:
                with db.transaction():
                    db.insert("accounts", {"type": "kiro", "priority": 10})
                    db.update("accounts", {"usage": 5.0}, "id = ?", (1,))
                    # Both operations commit together, or both rollback on error
        """
        if not self._conn:
            raise RuntimeError(
                "transaction() must be called within Database context manager. "
                "Use: with Database(path) as db: with db.transaction(): ..."
            )
        
        # Mark that we're in a transaction to prevent auto-commits
        self._in_transaction = True
        
        try:
            # Begin transaction (SQLite uses autocommit by default, so we need to explicitly begin)
            self._conn.execute("BEGIN")
            logger.debug("Transaction started")
            
            yield self
            
            # Commit transaction on success
            self._conn.commit()
            logger.debug("Transaction committed")
            
        except Exception as e:
            # Rollback transaction on any exception
            self._conn.rollback()
            logger.warning(f"Transaction rolled back due to error: {e}")
            raise
        
        finally:
            # Reset transaction flag
            self._in_transaction = False
    
    # ------------------------------------------------------------------
    # Account management methods
    # ------------------------------------------------------------------
    
    def get_account(self, account_id: int) -> Optional[sqlite3.Row]:
        """Fetch a single account by ID.
        
        Args:
            account_id: Account primary key.
        
        Returns:
            Account row or None if not found.
        
        Example:
            account = db.get_account(1)
            if account:
                print(account["type"], account["priority"])
        """
        return self.fetch_one(
            "SELECT * FROM accounts WHERE id = ?",
            (account_id,)
        )
    
    def list_accounts(
        self, 
        account_type: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[sqlite3.Row]:
        """List accounts with optional filtering.
        
        Args:
            account_type: Filter by account type (e.g., "kiro", "glm").
            enabled_only: If True, only return accounts with usage < limit.
        
        Returns:
            List of account rows sorted by priority DESC.
        
        Example:
            # Get all kiro accounts
            accounts = db.list_accounts(account_type="kiro")
            
            # Get all available accounts
            accounts = db.list_accounts(enabled_only=True)
        """
        query = "SELECT * FROM accounts"
        params = []
        conditions = []
        
        if account_type:
            conditions.append("type = ?")
            params.append(account_type)
        
        if enabled_only:
            conditions.append("(limit_ = 0 OR usage < limit_)")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY priority DESC"
        
        return self.fetch_all(query, tuple(params) if params else None)
    
    def create_account(
        self,
        account_type: str,
        config: str,
        priority: int = 0,
        limit: int = 0,
        usage: float = 0.0,
        email: Optional[str] = None,
        expires_at: Optional[str] = None,
        next_reset_at: Optional[int] = None
    ) -> int:
        """Create a new account.
        
        Args:
            account_type: Account type (e.g., "kiro", "glm").
            config: JSON string of account configuration/credentials.
            priority: Scheduling priority (higher = preferred).
            limit: Total usage limit (0 = unlimited).
            usage: Initial usage value.
            email: Optional email address.
            expires_at: Optional expiration timestamp.
            next_reset_at: Optional next reset timestamp.
        
        Returns:
            ID of the newly created account.
        
        Example:
            account_id = db.create_account(
                account_type="kiro",
                config='{"accessToken": "..."}',
                priority=10,
                limit=1000
            )
        """
        data = {
            "type": account_type,
            "config": config,
            "priority": priority,
            "limit_": limit,
            "usage": usage
        }
        
        if email is not None:
            data["email"] = email
        if expires_at is not None:
            data["expires_at"] = expires_at
        if next_reset_at is not None:
            data["next_reset_at"] = next_reset_at
        
        return self.insert("accounts", data)
    
    def update_account(
        self,
        account_id: int,
        **kwargs: Any
    ) -> int:
        """Update account fields.
        
        Supported kwargs: type, priority, config, limit, usage, email, 
        expires_at, next_reset_at.
        
        Args:
            account_id: Account primary key.
            **kwargs: Fields to update.
        
        Returns:
            Number of rows updated (should be 1 if account exists).
        
        Example:
            db.update_account(1, priority=20, usage=50.0)
        """
        # Map public field names to database column names
        field_map = {
            "type": "type",
            "priority": "priority",
            "config": "config",
            "limit": "limit_",
            "usage": "usage",
            "email": "email",
            "expires_at": "expires_at",
            "next_reset_at": "next_reset_at"
        }
        
        data = {}
        for key, value in kwargs.items():
            if key in field_map:
                data[field_map[key]] = value
        
        if not data:
            return 0
        
        return self.update("accounts", data, "id = ?", (account_id,))
    
    def delete_account(self, account_id: int) -> int:
        """Delete an account.
        
        Args:
            account_id: Account primary key.
        
        Returns:
            Number of rows deleted (1 if account existed, 0 otherwise).
        
        Example:
            deleted = db.delete_account(1)
        """
        return self.delete("accounts", "id = ?", (account_id,))
    
    def increment_usage(self, account_id: int, amount: float) -> None:
        """Atomically increment the usage field for an account.
        
        This operation is atomic at the SQL level, preventing race conditions
        when multiple requests update usage concurrently.
        
        Args:
            account_id: Account primary key.
            amount: Amount to add to current usage.
        
        Example:
            db.increment_usage(1, 10.5)
        """
        self.execute(
            "UPDATE accounts SET usage = usage + ? WHERE id = ?",
            (amount, account_id),
            commit=True
        )
    
    def refresh_usage(self, account_id: int, new_usage: float) -> int:
        """Refresh (reset) the usage field for an account.
        
        Args:
            account_id: Account primary key.
            new_usage: New usage value (typically 0.0 for reset).
        
        Returns:
            Number of rows updated.
        
        Example:
            db.refresh_usage(1, 0.0)  # Reset usage to 0
        """
        return self.update("accounts", {"usage": new_usage}, "id = ?", (account_id,))
    
    # ------------------------------------------------------------------
    # API Key management methods
    # ------------------------------------------------------------------
    
    def get_api_key(self, key_id: int) -> Optional[sqlite3.Row]:
        """Fetch a single API key by ID.
        
        Args:
            key_id: API key primary key.
        
        Returns:
            API key row or None if not found.
        
        Example:
            api_key = db.get_api_key(1)
            if api_key:
                print(api_key["key"], api_key["name"])
        """
        return self.fetch_one(
            "SELECT * FROM api_keys WHERE id = ?",
            (key_id,)
        )
    
    def list_api_keys(self) -> List[sqlite3.Row]:
        """List all API keys.
        
        Returns:
            List of API key rows ordered by ID DESC.
        
        Example:
            api_keys = db.list_api_keys()
            for key in api_keys:
                print(key["id"], key["name"], key["created_at"])
        """
        return self.fetch_all(
            "SELECT * FROM api_keys ORDER BY id DESC"
        )
    
    def create_api_key(
        self,
        name: str,
        key: str,
        created_at: Optional[str] = None
    ) -> int:
        """Create a new API key.
        
        Args:
            name: Human-readable name/description for the key.
            key: The actual API key string (should be unique).
            created_at: Optional ISO 8601 timestamp. If None, uses current time.
        
        Returns:
            ID of the newly created API key.
        
        Example:
            from datetime import datetime, timezone
            
            key_id = db.create_api_key(
                name="Production Key",
                key="sk-YOUR_API_KEY_HERE",
                created_at=datetime.now(timezone.utc).isoformat()
            )
        """
        if created_at is None:
            from datetime import datetime, timezone
            created_at = datetime.now(timezone.utc).isoformat()
        
        data = {
            "key": key,
            "name": name,
            "created_at": created_at
        }
        
        return self.insert("api_keys", data)
    
    def delete_api_key(self, key_id: int) -> int:
        """Delete an API key.
        
        Args:
            key_id: API key primary key.
        
        Returns:
            Number of rows deleted (1 if key existed, 0 otherwise).
        
        Example:
            deleted = db.delete_api_key(1)
            if deleted:
                print("API key deleted successfully")
        """
        return self.delete("api_keys", "id = ?", (key_id,))
    
    def verify_api_key(self, key: str) -> bool:
        """Verify if an API key exists in the database.
        
        Args:
            key: The API key string to verify.
        
        Returns:
            True if the key exists, False otherwise.
        
        Example:
            if db.verify_api_key("sk-YOUR_API_KEY_HERE"):
                print("Valid API key")
            else:
                print("Invalid API key")
        """
        row = self.fetch_one(
            "SELECT 1 FROM api_keys WHERE key = ?",
            (key,)
        )
        return row is not None
    
    # ------------------------------------------------------------------
    # Admin User management methods
    # ------------------------------------------------------------------
    
    def get_admin_user(self, username: str) -> Optional[sqlite3.Row]:
        """Fetch a single admin user by username.
        
        Args:
            username: Admin username (unique identifier).
        
        Returns:
            Admin user row or None if not found.
        
        Example:
            user = db.get_admin_user("admin")
            if user:
                print(user["id"], user["username"], user["created_at"])
        """
        return self.fetch_one(
            "SELECT * FROM admin_users WHERE username = ?",
            (username,)
        )
    
    def list_admin_users(self) -> List[sqlite3.Row]:
        """List all admin users.
        
        Returns:
            List of admin user rows ordered by ID.
        
        Example:
            users = db.list_admin_users()
            for user in users:
                print(user["id"], user["username"], user["created_at"])
        """
        return self.fetch_all(
            "SELECT * FROM admin_users ORDER BY id"
        )
    
    def create_admin_user(
        self,
        username: str,
        password_hash: str,
        created_at: Optional[str] = None
    ) -> int:
        """Create a new admin user.
        
        Args:
            username: Unique username for the admin.
            password_hash: Hashed password (should be pre-hashed by caller).
            created_at: Optional ISO 8601 timestamp. If None, uses current time.
        
        Returns:
            ID of the newly created admin user.
        
        Raises:
            sqlite3.IntegrityError: If username already exists.
        
        Example:
            from datetime import datetime, timezone
            
            user_id = db.create_admin_user(
                username="admin",
                password_hash="hashed_password_here",
                created_at=datetime.now(timezone.utc).isoformat()
            )
        """
        if created_at is None:
            from datetime import datetime, timezone
            created_at = datetime.now(timezone.utc).isoformat()
        
        data = {
            "username": username,
            "password_hash": password_hash,
            "created_at": created_at
        }
        
        return self.insert("admin_users", data)
    
    def update_admin_password(
        self,
        username: str,
        password_hash: str
    ) -> int:
        """Update an admin user's password.
        
        Args:
            username: Admin username to update.
            password_hash: New hashed password (should be pre-hashed by caller).
        
        Returns:
            Number of rows updated (1 if user exists, 0 otherwise).
        
        Example:
            rows_updated = db.update_admin_password("admin", "new_hashed_password")
            if rows_updated:
                print("Password updated successfully")
        """
        return self.update(
            "admin_users",
            {"password_hash": password_hash},
            "username = ?",
            (username,)
        )
    
    def delete_admin_user(self, username: str) -> int:
        """Delete an admin user by username.
        
        Args:
            username: Admin username to delete.
        
        Returns:
            Number of rows deleted (1 if user existed, 0 otherwise).
        
        Example:
            deleted = db.delete_admin_user("old_admin")
            if deleted:
                print("Admin user deleted successfully")
        """
        return self.delete("admin_users", "username = ?", (username,))
    
    # ------------------------------------------------------------------
    # Model management methods
    # ------------------------------------------------------------------
    
    def get_model(self, model_id: str, provider_type: Optional[str] = None) -> Optional[sqlite3.Row]:
        """Fetch a single model by model_id and optional provider_type.
        
        Args:
            model_id: Model identifier (e.g., "claude-sonnet-4").
            provider_type: Optional provider type filter (e.g., "kiro", "glm").
        
        Returns:
            Model row or None if not found.
        
        Example:
            model = db.get_model("claude-sonnet-4", "kiro")
            if model:
                print(model["display_name"], model["enabled"])
        """
        if provider_type:
            return self.fetch_one(
                "SELECT * FROM models WHERE model_id = ? AND provider_type = ?",
                (model_id, provider_type)
            )
        else:
            return self.fetch_one(
                "SELECT * FROM models WHERE model_id = ?",
                (model_id,)
            )
    
    def list_models(
        self,
        provider_type: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[sqlite3.Row]:
        """List models with optional filtering.
        
        Args:
            provider_type: Filter by provider type (e.g., "kiro", "glm").
            enabled_only: If True, only return enabled models (enabled=1).
        
        Returns:
            List of model rows sorted by priority DESC, then model_id ASC.
        
        Example:
            # Get all enabled kiro models
            models = db.list_models(provider_type="kiro")
            
            # Get all models regardless of enabled status
            models = db.list_models(enabled_only=False)
        """
        query = "SELECT * FROM models"
        params = []
        conditions = []
        
        if provider_type:
            conditions.append("provider_type = ?")
            params.append(provider_type)
        
        if enabled_only:
            conditions.append("enabled = 1")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY priority DESC, model_id ASC"
        
        return self.fetch_all(query, tuple(params) if params else None)
    
    def create_model(
        self,
        provider_type: str,
        model_id: str,
        display_name: Optional[str] = None,
        enabled: bool = True,
        priority: int = 0
    ) -> int:
        """Create a new model.
        
        Args:
            provider_type: Provider type (e.g., "kiro", "glm").
            model_id: Model identifier (e.g., "claude-sonnet-4").
            display_name: Optional human-readable display name.
            enabled: Whether the model is enabled (default: True).
            priority: Scheduling priority (higher = preferred, default: 0).
        
        Returns:
            ID of the newly created model.
        
        Raises:
            sqlite3.IntegrityError: If (provider_type, model_id) already exists.
        
        Example:
            model_id = db.create_model(
                provider_type="kiro",
                model_id="claude-sonnet-4",
                display_name="Claude Sonnet 4",
                enabled=True,
                priority=10
            )
        """
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc).isoformat()
        
        data = {
            "provider_type": provider_type,
            "model_id": model_id,
            "display_name": display_name,
            "enabled": 1 if enabled else 0,
            "priority": priority,
            "created_at": now,
            "updated_at": now
        }
        
        return self.insert("models", data)
    
    def update_model(
        self,
        model_id: str,
        provider_type: Optional[str] = None,
        **kwargs: Any
    ) -> int:
        """Update model fields.
        
        Supported kwargs: display_name, enabled, priority.
        
        Args:
            model_id: Model identifier to update.
            provider_type: Optional provider type for disambiguation.
            **kwargs: Fields to update.
        
        Returns:
            Number of rows updated (should be 1 if model exists).
        
        Example:
            # Update priority and enabled status
            db.update_model("claude-sonnet-4", provider_type="kiro", 
                          priority=20, enabled=True)
            
            # Update display name only
            db.update_model("claude-sonnet-4", display_name="Claude Sonnet 4 (Latest)")
        """
        from datetime import datetime, timezone
        
        # Map public field names to database column names
        field_map = {
            "display_name": "display_name",
            "enabled": "enabled",
            "priority": "priority"
        }
        
        data = {}
        for key, value in kwargs.items():
            if key in field_map:
                # Convert boolean to integer for enabled field
                if key == "enabled" and isinstance(value, bool):
                    value = 1 if value else 0
                data[field_map[key]] = value
        
        if not data:
            return 0
        
        # Always update the updated_at timestamp
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Build WHERE clause
        if provider_type:
            where = "model_id = ? AND provider_type = ?"
            where_params = (model_id, provider_type)
        else:
            where = "model_id = ?"
            where_params = (model_id,)
        
        return self.update("models", data, where, where_params)
    
    def delete_model(
        self,
        model_id: str,
        provider_type: Optional[str] = None
    ) -> int:
        """Delete a model.
        
        Args:
            model_id: Model identifier to delete.
            provider_type: Optional provider type for disambiguation.
        
        Returns:
            Number of rows deleted (1 if model existed, 0 otherwise).
        
        Example:
            # Delete specific model for a provider
            deleted = db.delete_model("claude-sonnet-4", provider_type="kiro")
            
            # Delete all models with this model_id (across all providers)
            deleted = db.delete_model("claude-sonnet-4")
        """
        if provider_type:
            return self.delete(
                "models",
                "model_id = ? AND provider_type = ?",
                (model_id, provider_type)
            )
        else:
            return self.delete("models", "model_id = ?", (model_id,))
    
    def count_models(
        self,
        provider_type: Optional[str] = None,
        enabled_only: bool = False
    ) -> int:
        """Count models with optional filtering.
        
        Args:
            provider_type: Filter by provider type (e.g., "kiro", "glm").
            enabled_only: If True, only count enabled models.
        
        Returns:
            Number of models matching the criteria.
        
        Example:
            # Count all models
            total = db.count_models()
            
            # Count enabled kiro models
            kiro_count = db.count_models(provider_type="kiro", enabled_only=True)
        """
        query = "SELECT COUNT(*) FROM models"
        params = []
        conditions = []
        
        if provider_type:
            conditions.append("provider_type = ?")
            params.append(provider_type)
        
        if enabled_only:
            conditions.append("enabled = 1")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        row = self.fetch_one(query, tuple(params) if params else None)
        return row[0] if row else 0
    
    # ------------------------------------------------------------------
    # Request Log management methods
    # ------------------------------------------------------------------
    
    def create_request_log(
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
        """Create a new request log entry.
        
        Args:
            api_key_id: API key ID (nullable).
            account_id: Account ID (nullable).
            model: Model identifier (e.g., "claude-sonnet-4").
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            status: Request status (e.g., "success", "error").
            channel: Channel type (e.g., "openai", "anthropic").
            duration_ms: Optional request duration in milliseconds.
        
        Returns:
            ID of the newly created log entry.
        
        Example:
            log_id = db.create_request_log(
                api_key_id=1,
                account_id=2,
                model="claude-sonnet-4",
                input_tokens=100,
                output_tokens=200,
                status="success",
                channel="openai",
                duration_ms=1500
            )
        """
        from datetime import datetime, timezone
        
        created_at = datetime.now(timezone.utc).isoformat()
        
        data = {
            "api_key_id": api_key_id,
            "account_id": account_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "status": status,
            "channel": channel,
            "created_at": created_at,
            "duration_ms": duration_ms
        }
        
        log_id = self.insert("request_logs", data)
        
        # Keep only the last 10000 records (cleanup old logs)
        self.execute(
            """
            DELETE FROM request_logs 
            WHERE id NOT IN (
                SELECT id FROM request_logs 
                ORDER BY created_at DESC 
                LIMIT 10000
            )
            """,
            commit=True
        )
        
        return log_id
    
    def list_request_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        search_model: Optional[str] = None,
        search_status: Optional[str] = None,
        search_channel: Optional[str] = None,
        api_key_id: Optional[int] = None,
        account_id: Optional[int] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List request logs with pagination and complex filtering.
        
        This method performs a JOIN with accounts and api_keys tables to
        enrich the log data with account type and API key name.
        
        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            search_model: Filter by model name (partial match).
            search_status: Filter by status (exact match).
            search_channel: Filter by channel (exact match).
            api_key_id: Filter by specific API key ID.
            account_id: Filter by specific account ID.
        
        Returns:
            Tuple of (list of log dicts with enriched data, total count).
        
        Example:
            # Get first 50 logs
            logs, total = db.list_request_logs(limit=50, offset=0)
            
            # Filter by model and status
            logs, total = db.list_request_logs(
                search_model="claude",
                search_status="success"
            )
            
            # Get logs for specific account
            logs, total = db.list_request_logs(account_id=1)
        """
        # Build WHERE clause with multiple filters
        where_clauses = []
        params = []
        
        if search_model:
            where_clauses.append("rl.model LIKE ?")
            params.append(f"%{search_model}%")
        
        if search_status:
            where_clauses.append("rl.status = ?")
            params.append(search_status)
        
        if search_channel:
            where_clauses.append("rl.channel = ?")
            params.append(search_channel)
        
        if api_key_id is not None:
            where_clauses.append("rl.api_key_id = ?")
            params.append(api_key_id)
        
        if account_id is not None:
            where_clauses.append("rl.account_id = ?")
            params.append(account_id)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM request_logs rl WHERE {where_sql}"
        count_row = self.fetch_one(count_query, tuple(params) if params else None)
        total = count_row[0] if count_row else 0
        
        # Get logs with JOIN to enrich data
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
        
        rows = self.fetch_all(query, tuple(params + [limit, offset]))
        
        # Convert rows to dictionaries with enriched data
        logs = []
        for row in rows:
            log_dict = {
                "id": row["id"],
                "api_key_id": row["api_key_id"],
                "api_key_name": row["api_key_name"] or f"Key #{row['api_key_id']}" if row["api_key_id"] else "N/A",
                "account_id": row["account_id"],
                "account_name": f"{row['account_type']} #{row['account_id']}" if row["account_id"] and row["account_type"] else "N/A",
                "model": row["model"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "status": row["status"],
                "channel": row["channel"],
                "created_at": row["created_at"],
                "duration_ms": row["duration_ms"] if "duration_ms" in row.keys() else None
            }
            logs.append(log_dict)
        
        return logs, total
    
    def get_daily_stats(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily usage statistics with aggregation.
        
        This method performs GROUP BY aggregation to calculate daily statistics
        including request count, total input tokens, and total output tokens.
        
        Args:
            days: Number of days to look back (default: 30).
        
        Returns:
            List of dicts with day, requests, input_tokens, output_tokens.
            Results are ordered by day ascending (oldest first).
        
        Example:
            # Get last 30 days of stats
            stats = db.get_daily_stats(days=30)
            for stat in stats:
                print(f"{stat['day']}: {stat['requests']} requests, "
                      f"{stat['input_tokens']} input tokens")
            
            # Get last 7 days
            stats = db.get_daily_stats(days=7)
        """
        from datetime import datetime, timedelta, timezone
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        query = """
            SELECT 
                strftime('%Y-%m-%d', created_at) as day,
                COUNT(*) as requests,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens
            FROM request_logs
            WHERE created_at >= ?
            GROUP BY day
            ORDER BY day ASC
        """
        
        rows = self.fetch_all(query, (cutoff,))
        
        return [
            {
                "day": row["day"],
                "requests": row["requests"],
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0
            }
            for row in rows
        ]
    
    def get_hourly_stats(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get hourly usage statistics with time-based grouping.
        
        This method performs GROUP BY with time truncation to calculate
        hourly statistics including request count, total input tokens,
        and total output tokens.
        
        Args:
            hours: Number of hours to look back (default: 24).
        
        Returns:
            List of dicts with hour, requests, input_tokens, output_tokens.
            Results are ordered by hour ascending (oldest first).
        
        Example:
            # Get last 24 hours of stats
            stats = db.get_hourly_stats(hours=24)
            for stat in stats:
                print(f"{stat['hour']}: {stat['requests']} requests")
            
            # Get last 12 hours
            stats = db.get_hourly_stats(hours=12)
        """
        from datetime import datetime, timedelta, timezone
        
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        
        query = """
            SELECT 
                strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                COUNT(*) as requests,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens
            FROM request_logs
            WHERE created_at >= ?
            GROUP BY hour
            ORDER BY hour ASC
        """
        
        rows = self.fetch_all(query, (cutoff,))
        
        return [
            {
                "hour": row["hour"],
                "requests": row["requests"],
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0
            }
            for row in rows
        ]
    
    # ------------------------------------------------------------------
    # Session management methods
    # ------------------------------------------------------------------
    
    def create_session(
        self,
        username: str,
        token: str,
        expires_at: str
    ) -> str:
        """Create a new session for a user.
        
        Args:
            username: Username associated with the session.
            token: Session token (should be unique, e.g., UUID).
            expires_at: ISO 8601 timestamp when the session expires.
        
        Returns:
            The session token that was created.
        
        Raises:
            sqlite3.IntegrityError: If token already exists.
        
        Example:
            from datetime import datetime, timedelta, timezone
            
            token = str(uuid.uuid4())
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            
            session_token = db.create_session(
                username="admin",
                token=token,
                expires_at=expires_at
            )
        """
        from datetime import datetime, timezone
        
        created_at = datetime.now(timezone.utc).isoformat()
        
        data = {
            "session_token": token,
            "username": username,
            "created_at": created_at,
            "expires_at": expires_at
        }
        
        self.insert("sessions", data)
        return token
    
    def get_session(self, token: str) -> Optional[sqlite3.Row]:
        """Fetch a session by token.
        
        Args:
            token: Session token to look up.
        
        Returns:
            Session row or None if not found.
        
        Example:
            session = db.get_session("some-token-uuid")
            if session:
                print(f"User: {session['username']}, Expires: {session['expires_at']}")
        """
        return self.fetch_one(
            "SELECT * FROM sessions WHERE session_token = ?",
            (token,)
        )
    
    def delete_session(self, token: str) -> int:
        """Delete a session by token.
        
        Args:
            token: Session token to delete.
        
        Returns:
            Number of rows deleted (1 if session existed, 0 otherwise).
        
        Example:
            deleted = db.delete_session("some-token-uuid")
            if deleted:
                print("Session deleted successfully")
        """
        return self.delete("sessions", "session_token = ?", (token,))
    
    def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions from the database.
        
        Compares the expires_at timestamp with the current time and
        removes all sessions that have expired.
        
        Returns:
            Number of expired sessions deleted.
        
        Example:
            # Run periodically to clean up old sessions
            deleted = db.cleanup_expired_sessions()
            logger.info(f"Cleaned up {deleted} expired sessions")
        """
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc).isoformat()
        
        return self.delete("sessions", "expires_at < ?", (now,))
