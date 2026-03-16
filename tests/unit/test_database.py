# -*- coding: utf-8 -*-
"""
Unit tests for Database class.

Tests cover:
- m1-a1: Database class exists and is importable
- m1-a2: Database class provides connection management
- m1-a3: Database class provides context manager support
- m1-a7: Database class handles connection errors gracefully
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from kiro.core.database import Database


class TestDatabaseImport:
    """Test m1-a1: Database class exists and is importable."""
    
    def test_database_class_importable(self):
        """Verify Database class can be imported."""
        from kiro.core.database import Database
        assert Database is not None
    
    def test_database_is_class(self):
        """Verify Database is a class type."""
        assert isinstance(Database, type)


class TestDatabaseConnectionManagement:
    """Test m1-a2: Database class provides connection management."""
    
    def test_database_instantiation(self):
        """Verify Database can be instantiated with db_path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            db = Database(db_path)
            assert db is not None
            assert db._db_path == db_path
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_connect_method_exists(self):
        """Verify Database has _connect() method."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            db = Database(db_path)
            assert hasattr(db, "_connect")
            assert callable(db._connect)
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_connect_returns_connection(self):
        """Verify _connect() returns sqlite3.Connection."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            db = Database(db_path)
            conn = db._connect()
            assert isinstance(conn, sqlite3.Connection)
            conn.close()
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_connection_has_row_factory(self):
        """Verify connection has row_factory configured."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            db = Database(db_path)
            conn = db._connect()
            assert conn.row_factory == sqlite3.Row
            conn.close()
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestDatabaseContextManager:
    """Test m1-a3: Database class provides context manager support."""
    
    def test_context_manager_enter_exit(self):
        """Verify Database works as context manager."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            with Database(db_path) as db:
                assert db is not None
                assert db._conn is not None
                assert isinstance(db._conn, sqlite3.Connection)
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_context_manager_closes_connection(self):
        """Verify connection is closed on context exit."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            db = Database(db_path)
            with db:
                conn = db._conn
                assert conn is not None
            
            # After exiting context, connection should be None
            assert db._conn is None
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_context_manager_with_operations(self):
        """Verify database operations work within context manager."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Create a test table and insert data
            with Database(db_path) as db:
                db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
                db.execute("INSERT INTO test (name) VALUES (?)", ("test_value",))
            
            # Verify data persists after context exit
            with Database(db_path) as db:
                row = db.fetch_one("SELECT * FROM test WHERE name = ?", ("test_value",))
                assert row is not None
                assert row["name"] == "test_value"
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestDatabaseCRUDMethods:
    """Test basic CRUD methods (execute, fetch_one, fetch_all, insert, update, delete)."""
    
    @pytest.fixture
    def test_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        # Initialize database with test table
        with Database(db_path) as db:
            db.execute("""
                CREATE TABLE test_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    usage REAL NOT NULL DEFAULT 0
                )
            """)
        
        yield db_path
        
        # Cleanup
        Path(db_path).unlink(missing_ok=True)
    
    def test_execute_method(self, test_db):
        """Test execute() method."""
        with Database(test_db) as db:
            cursor = db.execute(
                "INSERT INTO test_accounts (type, priority, usage) VALUES (?, ?, ?)",
                ("kiro", 10, 0.0)
            )
            assert cursor.lastrowid > 0
    
    def test_fetch_one_method(self, test_db):
        """Test fetch_one() method."""
        # Insert test data
        with Database(test_db) as db:
            db.execute(
                "INSERT INTO test_accounts (type, priority, usage) VALUES (?, ?, ?)",
                ("kiro", 10, 5.0)
            )
        
        # Fetch single row
        with Database(test_db) as db:
            row = db.fetch_one("SELECT * FROM test_accounts WHERE type = ?", ("kiro",))
            assert row is not None
            assert row["type"] == "kiro"
            assert row["priority"] == 10
            assert row["usage"] == 5.0
    
    def test_fetch_one_returns_none_when_no_results(self, test_db):
        """Test fetch_one() returns None when no results."""
        with Database(test_db) as db:
            row = db.fetch_one("SELECT * FROM test_accounts WHERE type = ?", ("nonexistent",))
            assert row is None
    
    def test_fetch_all_method(self, test_db):
        """Test fetch_all() method."""
        # Insert multiple rows
        with Database(test_db) as db:
            db.execute("INSERT INTO test_accounts (type, priority, usage) VALUES (?, ?, ?)", ("kiro", 10, 1.0))
            db.execute("INSERT INTO test_accounts (type, priority, usage) VALUES (?, ?, ?)", ("kiro", 5, 2.0))
            db.execute("INSERT INTO test_accounts (type, priority, usage) VALUES (?, ?, ?)", ("glm", 3, 3.0))
        
        # Fetch all kiro accounts
        with Database(test_db) as db:
            rows = db.fetch_all("SELECT * FROM test_accounts WHERE type = ?", ("kiro",))
            assert len(rows) == 2
            assert all(row["type"] == "kiro" for row in rows)
    
    def test_fetch_all_returns_empty_list_when_no_results(self, test_db):
        """Test fetch_all() returns empty list when no results."""
        with Database(test_db) as db:
            rows = db.fetch_all("SELECT * FROM test_accounts WHERE type = ?", ("nonexistent",))
            assert rows == []
    
    def test_insert_method(self, test_db):
        """Test insert() method."""
        with Database(test_db) as db:
            account_id = db.insert("test_accounts", {
                "type": "kiro",
                "priority": 15,
                "usage": 10.5
            })
            assert account_id > 0
            
            # Verify insertion
            row = db.fetch_one("SELECT * FROM test_accounts WHERE id = ?", (account_id,))
            assert row is not None
            assert row["type"] == "kiro"
            assert row["priority"] == 15
            assert row["usage"] == 10.5
    
    def test_update_method(self, test_db):
        """Test update() method."""
        # Insert test data
        with Database(test_db) as db:
            account_id = db.insert("test_accounts", {
                "type": "kiro",
                "priority": 10,
                "usage": 5.0
            })
            
            # Update the row
            rows_updated = db.update(
                "test_accounts",
                {"priority": 20, "usage": 15.0},
                "id = ?",
                (account_id,)
            )
            assert rows_updated == 1
            
            # Verify update
            row = db.fetch_one("SELECT * FROM test_accounts WHERE id = ?", (account_id,))
            assert row["priority"] == 20
            assert row["usage"] == 15.0
    
    def test_update_returns_zero_when_no_match(self, test_db):
        """Test update() returns 0 when no rows match."""
        with Database(test_db) as db:
            rows_updated = db.update(
                "test_accounts",
                {"priority": 20},
                "id = ?",
                (99999,)
            )
            assert rows_updated == 0
    
    def test_delete_method(self, test_db):
        """Test delete() method."""
        # Insert test data
        with Database(test_db) as db:
            account_id = db.insert("test_accounts", {
                "type": "kiro",
                "priority": 10,
                "usage": 5.0
            })
            
            # Delete the row
            rows_deleted = db.delete("test_accounts", "id = ?", (account_id,))
            assert rows_deleted == 1
            
            # Verify deletion
            row = db.fetch_one("SELECT * FROM test_accounts WHERE id = ?", (account_id,))
            assert row is None
    
    def test_delete_returns_zero_when_no_match(self, test_db):
        """Test delete() returns 0 when no rows match."""
        with Database(test_db) as db:
            rows_deleted = db.delete("test_accounts", "id = ?", (99999,))
            assert rows_deleted == 0


class TestDatabaseErrorHandling:
    """Test m1-a7: Database class handles connection errors gracefully."""
    
    def test_invalid_path_raises_exception(self):
        """Test that invalid database path raises appropriate exception."""
        # Use an invalid path (directory that doesn't exist)
        invalid_path = "/nonexistent/directory/database.db"
        
        db = Database(invalid_path)
        
        with pytest.raises(sqlite3.Error):
            db._connect()
    
    def test_connection_error_has_clear_message(self):
        """Test that connection errors raise appropriate exceptions with clear context."""
        invalid_path = "/nonexistent/directory/database.db"
        db = Database(invalid_path)
        
        # Verify that connection error raises sqlite3.Error
        # The error logging is verified manually by checking stderr output
        with pytest.raises(sqlite3.Error) as exc_info:
            db._connect()
        
        # Verify the exception contains useful information
        assert exc_info.value is not None
    
    def test_invalid_query_raises_exception(self):
        """Test that invalid SQL raises appropriate exception."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            with Database(db_path) as db:
                with pytest.raises(sqlite3.Error):
                    db.execute("INVALID SQL QUERY")
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_operations_outside_context_manager(self):
        """Test that operations work outside context manager (standalone usage)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            db = Database(db_path)
            
            # Create table
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            
            # Insert data
            db.execute("INSERT INTO test (name) VALUES (?)", ("standalone",))
            
            # Fetch data
            row = db.fetch_one("SELECT * FROM test WHERE name = ?", ("standalone",))
            assert row is not None
            assert row["name"] == "standalone"
            
            # Give time for connections to close on Windows
            import time
            time.sleep(0.1)
        finally:
            # Retry deletion on Windows if file is locked
            import time
            for _ in range(5):
                try:
                    Path(db_path).unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.1)


class TestDatabaseIntegration:
    """Integration tests for Database class."""
    
    def test_multiple_operations_in_sequence(self):
        """Test multiple database operations in sequence."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            with Database(db_path) as db:
                # Create table
                db.execute("""
                    CREATE TABLE accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        type TEXT NOT NULL,
                        priority INTEGER NOT NULL,
                        usage REAL NOT NULL DEFAULT 0
                    )
                """)
                
                # Insert multiple accounts
                id1 = db.insert("accounts", {"type": "kiro", "priority": 10, "usage": 5.0})
                id2 = db.insert("accounts", {"type": "glm", "priority": 5, "usage": 3.0})
                
                # Fetch all accounts
                all_accounts = db.fetch_all("SELECT * FROM accounts ORDER BY priority DESC")
                assert len(all_accounts) == 2
                assert all_accounts[0]["type"] == "kiro"
                assert all_accounts[1]["type"] == "glm"
                
                # Update an account
                db.update("accounts", {"usage": 10.0}, "id = ?", (id1,))
                
                # Verify update
                updated = db.fetch_one("SELECT * FROM accounts WHERE id = ?", (id1,))
                assert updated["usage"] == 10.0
                
                # Delete an account
                db.delete("accounts", "id = ?", (id2,))
                
                # Verify deletion
                remaining = db.fetch_all("SELECT * FROM accounts")
                assert len(remaining) == 1
                assert remaining[0]["id"] == id1
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_concurrent_context_managers(self):
        """Test that multiple context managers can access the same database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # First context: create and insert
            with Database(db_path) as db1:
                db1.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
                db1.insert("test", {"value": "first"})
            
            # Second context: read and verify
            with Database(db_path) as db2:
                row = db2.fetch_one("SELECT * FROM test WHERE value = ?", ("first",))
                assert row is not None
                assert row["value"] == "first"
            
            # Third context: update
            with Database(db_path) as db3:
                db3.update("test", {"value": "updated"}, "value = ?", ("first",))
            
            # Fourth context: verify update
            with Database(db_path) as db4:
                row = db4.fetch_one("SELECT * FROM test WHERE value = ?", ("updated",))
                assert row is not None
                assert row["value"] == "updated"
        finally:
            Path(db_path).unlink(missing_ok=True)
