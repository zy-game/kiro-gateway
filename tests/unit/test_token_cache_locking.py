"""
Tests for token cache locking mechanism in AccountManager.

Verifies that concurrent access to _get_cached_token() and _cache_token()
is properly protected by asyncio.Lock to prevent race conditions.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path

from kiro.core.auth import AccountManager


class TestTokenCacheLocking:
    """Test token cache locking mechanism."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def manager(self, temp_db):
        """Create an AccountManager instance."""
        return AccountManager(db_path=temp_db)

    @pytest.mark.asyncio
    async def test_token_cache_lock_exists(self, manager):
        """Test that _token_cache_lock exists and is an asyncio.Lock."""
        assert hasattr(manager, "_token_cache_lock")
        assert isinstance(manager._token_cache_lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_get_cached_token_is_async(self, manager):
        """Test that _get_cached_token is an async method."""
        import inspect
        assert inspect.iscoroutinefunction(manager._get_cached_token)

    @pytest.mark.asyncio
    async def test_cache_token_is_async(self, manager):
        """Test that _cache_token is an async method."""
        import inspect
        assert inspect.iscoroutinefunction(manager._cache_token)

    @pytest.mark.asyncio
    async def test_concurrent_cache_token_calls(self, manager):
        """Test that concurrent _cache_token calls don't cause race conditions."""
        account_id = 1
        
        # Cache multiple values concurrently
        tasks = []
        for i in range(50):
            value = f"value_{i}"
            expires_in = 3600
            tasks.append(manager._cache_token(account_id, value, expires_in))
        
        await asyncio.gather(*tasks)
        
        # Verify cache has exactly one entry for the account
        assert account_id in manager._token_cache
        cached_value, expiry = manager._token_cache[account_id]
        
        # Value should be one of the cached values
        assert cached_value.startswith("value_")
        assert expiry > 0

    @pytest.mark.asyncio
    async def test_concurrent_get_cached_token_calls(self, manager):
        """Test that concurrent _get_cached_token calls work correctly."""
        account_id = 1
        cached_value = "mock_access_value_for_testing"
        expires_in = 3600
        
        # Cache a token first
        await manager._cache_token(account_id, cached_value, expires_in)
        
        # Read it concurrently from multiple tasks
        tasks = [manager._get_cached_token(account_id) for _ in range(50)]
        results = await asyncio.gather(*tasks)
        
        # All results should be the same token
        assert all(result == cached_value for result in results)

    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(self, manager):
        """Test concurrent reads and writes to token cache."""
        account_id = 1
        
        async def reader():
            """Read from cache."""
            return await manager._get_cached_token(account_id)
        
        async def writer(suffix):
            """Write to cache."""
            await manager._cache_token(account_id, f"value_{suffix}", 3600)
        
        # Mix reads and writes
        tasks = []
        for i in range(25):
            tasks.append(writer(i))
            tasks.append(reader())
        
        # Should complete without errors
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # No exceptions should occur
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0

    @pytest.mark.asyncio
    async def test_cache_token_updates_correctly(self, manager):
        """Test that cache updates work correctly under concurrent access."""
        account_id = 1
        
        # Cache initial value
        await manager._cache_token(account_id, "initial_value", 3600)
        
        # Verify initial value
        cached = await manager._get_cached_token(account_id)
        assert cached == "initial_value"
        
        # Update value
        await manager._cache_token(account_id, "updated_value", 3600)
        
        # Verify updated value
        cached = await manager._get_cached_token(account_id)
        assert cached == "updated_value"

    @pytest.mark.asyncio
    async def test_expired_token_not_returned(self, manager):
        """Test that expired tokens are not returned from cache."""
        account_id = 1
        
        # Cache a value that expires in 0 seconds (already expired)
        await manager._cache_token(account_id, "expired_value", 0)
        
        # Should return None for expired value
        cached = await manager._get_cached_token(account_id)
        assert cached is None

    @pytest.mark.asyncio
    async def test_multiple_accounts_concurrent_access(self, manager):
        """Test concurrent access to cache for multiple accounts."""
        num_accounts = 10
        
        async def cache_for_account(account_id):
            """Cache value for an account."""
            await manager._cache_token(account_id, f"value_for_account_{account_id}", 3600)
        
        async def get_for_account(account_id):
            """Get cached value for an account."""
            return await manager._get_cached_token(account_id)
        
        # Cache values for multiple accounts concurrently
        cache_tasks = [cache_for_account(i) for i in range(num_accounts)]
        await asyncio.gather(*cache_tasks)
        
        # Read values for all accounts concurrently
        get_tasks = [get_for_account(i) for i in range(num_accounts)]
        results = await asyncio.gather(*get_tasks)
        
        # Verify each account has its own value
        for i, cached in enumerate(results):
            assert cached == f"value_for_account_{i}"

    @pytest.mark.asyncio
    async def test_lock_prevents_race_condition(self, manager):
        """Test that lock prevents race conditions in cache updates."""
        account_id = 1
        update_count = 100
        
        # Track the order of updates
        updates = []
        
        async def update_with_tracking(index):
            """Update cache and track the operation."""
            await manager._cache_token(account_id, f"value_{index}", 3600)
            updates.append(index)
        
        # Perform many concurrent updates
        tasks = [update_with_tracking(i) for i in range(update_count)]
        await asyncio.gather(*tasks)
        
        # All updates should have completed
        assert len(updates) == update_count
        
        # Final cached value should be one of the values we set
        cached = await manager._get_cached_token(account_id)
        assert cached is not None
        assert cached.startswith("value_")
