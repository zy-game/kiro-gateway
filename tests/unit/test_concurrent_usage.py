# -*- coding: utf-8 -*-
"""
Test concurrent usage tracking to verify transaction isolation.

This test verifies that Database.increment_usage() properly handles
concurrent updates without race conditions.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from kiro.core.database import Database


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database with accounts table."""
    db_path = tmp_path / "test.db"
    
    # Create schema (matching actual database schema)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL DEFAULT 'kiro',
            priority INTEGER NOT NULL DEFAULT 0,
            config TEXT NOT NULL,
            limit_ INTEGER NOT NULL DEFAULT 0,
            usage REAL NOT NULL DEFAULT 0,
            email TEXT,
            expires_at TEXT,
            next_reset_at INTEGER
        )
    """)
    conn.commit()
    conn.close()
    
    return str(db_path)


class TestConcurrentUsageTracking:
    """Test concurrent usage tracking with proper isolation."""
    
    def test_concurrent_increment_usage_no_race_condition(self, temp_db):
        """Test that concurrent increment_usage calls don't lose updates.
        
        This test simulates the real-world scenario where multiple requests
        try to increment usage for the same account simultaneously.
        """
        # Create an account
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config, usage=0.0)
        
        # Number of concurrent threads and increments per thread
        num_threads = 10
        increments_per_thread = 10
        increment_amount = 1.0
        
        # Expected final usage
        expected_usage = num_threads * increments_per_thread * increment_amount
        
        # Barrier to synchronize thread start (maximize concurrency)
        barrier = threading.Barrier(num_threads)
        errors = []
        
        def increment_worker():
            """Worker function that increments usage multiple times."""
            try:
                # Wait for all threads to be ready
                barrier.wait()
                
                # Perform increments
                for _ in range(increments_per_thread):
                    with Database(temp_db) as db:
                        db.increment_usage(account_id, increment_amount)
            except Exception as e:
                errors.append(e)
        
        # Create and start threads
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=increment_worker)
            threads.append(t)
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Check for errors
        assert not errors, f"Errors occurred during concurrent updates: {errors}"
        
        # Verify final usage is correct (no lost updates)
        with Database(temp_db) as db:
            account = db.get_account(account_id)
            assert account is not None
            actual_usage = account["usage"]
            
            # The usage should be exactly the expected value
            # If there are race conditions, some updates will be lost
            assert actual_usage == expected_usage, (
                f"Race condition detected: expected {expected_usage}, "
                f"got {actual_usage}. Lost {expected_usage - actual_usage} updates."
            )
    
    def test_concurrent_increment_different_accounts(self, temp_db):
        """Test that concurrent updates to different accounts don't interfere."""
        # Create multiple accounts
        with Database(temp_db) as db:
            config = json.dumps({})
            account_ids = [
                db.create_account("kiro", config, usage=0.0)
                for _ in range(5)
            ]
        
        num_increments = 20
        increment_amount = 2.5
        expected_usage = num_increments * increment_amount
        
        def increment_account(account_id):
            """Increment a specific account multiple times."""
            for _ in range(num_increments):
                with Database(temp_db) as db:
                    db.increment_usage(account_id, increment_amount)
        
        # Create threads for each account
        threads = []
        for account_id in account_ids:
            t = threading.Thread(target=increment_account, args=(account_id,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Verify each account has correct usage
        with Database(temp_db) as db:
            for account_id in account_ids:
                account = db.get_account(account_id)
                assert account["usage"] == expected_usage
    
    def test_increment_usage_with_explicit_transaction(self, temp_db):
        """Test that increment_usage works correctly within explicit transactions."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config, usage=0.0)
            
            # Use explicit transaction
            with db.transaction():
                db.increment_usage(account_id, 10.0)
                db.increment_usage(account_id, 5.0)
            
            account = db.get_account(account_id)
            assert account["usage"] == 15.0
    
    def test_increment_usage_rollback_on_error(self, temp_db):
        """Test that increment_usage rolls back on error within transaction."""
        with Database(temp_db) as db:
            config = json.dumps({})
            account_id = db.create_account("kiro", config, usage=0.0)
            
            try:
                with db.transaction():
                    db.increment_usage(account_id, 10.0)
                    # Force an error
                    raise ValueError("Test error")
            except ValueError:
                pass
            
            # Usage should still be 0.0 (rolled back)
            account = db.get_account(account_id)
            assert account["usage"] == 0.0
