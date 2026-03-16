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
