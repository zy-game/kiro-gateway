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
