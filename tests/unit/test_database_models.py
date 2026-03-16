# -*- coding: utf-8 -*-
"""
Unit tests for Database model management methods.

Tests the following methods:
- get_model()
- list_models()
- create_model()
- update_model()
- delete_model()
- count_models()
"""

import pytest
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import os

from kiro.core.database import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Create the models table
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE models (
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
    """)
    conn.commit()
    conn.close()
    
    yield path
    
    # Cleanup
    try:
        os.unlink(path)
    except:
        pass


class TestGetModel:
    """Tests for get_model() method."""
    
    def test_get_model_by_id_only(self, temp_db):
        """Test fetching a model by model_id only."""
        with Database(temp_db) as db:
            # Create a test model
            model_id = db.create_model(
                provider_type="kiro",
                model_id="claude-sonnet-4",
                display_name="Claude Sonnet 4"
            )
            
            # Fetch it back
            model = db.get_model("claude-sonnet-4")
            
            assert model is not None
            assert model["model_id"] == "claude-sonnet-4"
            assert model["provider_type"] == "kiro"
            assert model["display_name"] == "Claude Sonnet 4"
    
    def test_get_model_by_id_and_provider(self, temp_db):
        """Test fetching a model by model_id and provider_type."""
        with Database(temp_db) as db:
            # Create two models with same model_id but different providers
            db.create_model("kiro", "claude-sonnet-4", "Kiro Sonnet")
            db.create_model("glm", "claude-sonnet-4", "GLM Sonnet")
            
            # Fetch kiro version
            model = db.get_model("claude-sonnet-4", provider_type="kiro")
            assert model["provider_type"] == "kiro"
            assert model["display_name"] == "Kiro Sonnet"
            
            # Fetch glm version
            model = db.get_model("claude-sonnet-4", provider_type="glm")
            assert model["provider_type"] == "glm"
            assert model["display_name"] == "GLM Sonnet"
    
    def test_get_model_not_found(self, temp_db):
        """Test fetching a non-existent model returns None."""
        with Database(temp_db) as db:
            model = db.get_model("non-existent-model")
            assert model is None


class TestListModels:
    """Tests for list_models() method."""
    
    def test_list_all_models(self, temp_db):
        """Test listing all models."""
        with Database(temp_db) as db:
            # Create test models
            db.create_model("kiro", "claude-sonnet-4", priority=10)
            db.create_model("kiro", "claude-haiku-4", priority=5)
            db.create_model("glm", "glm-4", priority=8)
            
            # List all models
            models = db.list_models(enabled_only=False)
            
            assert len(models) == 3
            # Should be sorted by priority DESC
            assert models[0]["model_id"] == "claude-sonnet-4"
            assert models[1]["model_id"] == "glm-4"
            assert models[2]["model_id"] == "claude-haiku-4"
    
    def test_list_models_by_provider(self, temp_db):
        """Test listing models filtered by provider."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4")
            db.create_model("kiro", "claude-haiku-4")
            db.create_model("glm", "glm-4")
            
            # List only kiro models
            models = db.list_models(provider_type="kiro", enabled_only=False)
            
            assert len(models) == 2
            assert all(m["provider_type"] == "kiro" for m in models)
    
    def test_list_enabled_only(self, temp_db):
        """Test listing only enabled models."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4", enabled=True)
            db.create_model("kiro", "claude-haiku-4", enabled=False)
            db.create_model("kiro", "claude-opus-4", enabled=True)
            
            # List only enabled models
            models = db.list_models(enabled_only=True)
            
            assert len(models) == 2
            assert all(m["enabled"] == 1 for m in models)
            model_ids = [m["model_id"] for m in models]
            assert "claude-haiku-4" not in model_ids
    
    def test_list_models_empty(self, temp_db):
        """Test listing models when none exist."""
        with Database(temp_db) as db:
            models = db.list_models()
            assert len(models) == 0


class TestCreateModel:
    """Tests for create_model() method."""
    
    def test_create_model_minimal(self, temp_db):
        """Test creating a model with minimal parameters."""
        with Database(temp_db) as db:
            model_id = db.create_model(
                provider_type="kiro",
                model_id="claude-sonnet-4"
            )
            
            assert model_id > 0
            
            # Verify it was created
            model = db.get_model("claude-sonnet-4")
            assert model is not None
            assert model["provider_type"] == "kiro"
            assert model["model_id"] == "claude-sonnet-4"
            assert model["enabled"] == 1
            assert model["priority"] == 0
            assert model["display_name"] is None
    
    def test_create_model_full(self, temp_db):
        """Test creating a model with all parameters."""
        with Database(temp_db) as db:
            model_id = db.create_model(
                provider_type="kiro",
                model_id="claude-sonnet-4",
                display_name="Claude Sonnet 4",
                enabled=True,
                priority=10
            )
            
            assert model_id > 0
            
            # Verify all fields
            model = db.get_model("claude-sonnet-4")
            assert model["display_name"] == "Claude Sonnet 4"
            assert model["enabled"] == 1
            assert model["priority"] == 10
            assert model["created_at"] is not None
            assert model["updated_at"] is not None
    
    def test_create_model_disabled(self, temp_db):
        """Test creating a disabled model."""
        with Database(temp_db) as db:
            db.create_model(
                provider_type="kiro",
                model_id="claude-sonnet-4",
                enabled=False
            )
            
            model = db.get_model("claude-sonnet-4")
            assert model["enabled"] == 0
    
    def test_create_model_duplicate_fails(self, temp_db):
        """Test that creating a duplicate model raises IntegrityError."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4")
            
            # Try to create the same model again
            with pytest.raises(sqlite3.IntegrityError):
                db.create_model("kiro", "claude-sonnet-4")
    
    def test_create_model_same_id_different_provider(self, temp_db):
        """Test creating models with same ID but different providers."""
        with Database(temp_db) as db:
            id1 = db.create_model("kiro", "claude-sonnet-4")
            id2 = db.create_model("glm", "claude-sonnet-4")
            
            assert id1 != id2
            
            # Both should exist
            assert db.get_model("claude-sonnet-4", "kiro") is not None
            assert db.get_model("claude-sonnet-4", "glm") is not None


class TestUpdateModel:
    """Tests for update_model() method."""
    
    def test_update_model_priority(self, temp_db):
        """Test updating model priority."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4", priority=5)
            
            # Update priority
            rows = db.update_model("claude-sonnet-4", priority=10)
            
            assert rows == 1
            model = db.get_model("claude-sonnet-4")
            assert model["priority"] == 10
    
    def test_update_model_enabled(self, temp_db):
        """Test updating model enabled status."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4", enabled=True)
            
            # Disable the model
            rows = db.update_model("claude-sonnet-4", enabled=False)
            
            assert rows == 1
            model = db.get_model("claude-sonnet-4")
            assert model["enabled"] == 0
            
            # Re-enable it
            db.update_model("claude-sonnet-4", enabled=True)
            model = db.get_model("claude-sonnet-4")
            assert model["enabled"] == 1
    
    def test_update_model_display_name(self, temp_db):
        """Test updating model display name."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4", display_name="Old Name")
            
            # Update display name
            db.update_model("claude-sonnet-4", display_name="New Name")
            
            model = db.get_model("claude-sonnet-4")
            assert model["display_name"] == "New Name"
    
    def test_update_model_multiple_fields(self, temp_db):
        """Test updating multiple fields at once."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4", priority=5, enabled=True)
            
            # Update multiple fields
            db.update_model(
                "claude-sonnet-4",
                priority=10,
                enabled=False,
                display_name="Updated Model"
            )
            
            model = db.get_model("claude-sonnet-4")
            assert model["priority"] == 10
            assert model["enabled"] == 0
            assert model["display_name"] == "Updated Model"
    
    def test_update_model_with_provider_type(self, temp_db):
        """Test updating a specific model when multiple providers exist."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4", priority=5)
            db.create_model("glm", "claude-sonnet-4", priority=5)
            
            # Update only the kiro version
            rows = db.update_model(
                "claude-sonnet-4",
                provider_type="kiro",
                priority=10
            )
            
            assert rows == 1
            kiro_model = db.get_model("claude-sonnet-4", "kiro")
            glm_model = db.get_model("claude-sonnet-4", "glm")
            
            assert kiro_model["priority"] == 10
            assert glm_model["priority"] == 5  # Unchanged
    
    def test_update_model_not_found(self, temp_db):
        """Test updating a non-existent model returns 0."""
        with Database(temp_db) as db:
            rows = db.update_model("non-existent", priority=10)
            assert rows == 0
    
    def test_update_model_no_fields(self, temp_db):
        """Test updating with no fields returns 0."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4")
            
            # Update with no valid fields
            rows = db.update_model("claude-sonnet-4")
            assert rows == 0
    
    def test_update_model_updates_timestamp(self, temp_db):
        """Test that update_model updates the updated_at timestamp."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4")
            
            model_before = db.get_model("claude-sonnet-4")
            created_at = model_before["created_at"]
            updated_at_before = model_before["updated_at"]
            
            # Small delay to ensure timestamp difference
            import time
            time.sleep(0.01)
            
            # Update the model
            db.update_model("claude-sonnet-4", priority=10)
            
            model_after = db.get_model("claude-sonnet-4")
            updated_at_after = model_after["updated_at"]
            
            # created_at should not change
            assert model_after["created_at"] == created_at
            # updated_at should change
            assert updated_at_after > updated_at_before


class TestDeleteModel:
    """Tests for delete_model() method."""
    
    def test_delete_model_by_id_only(self, temp_db):
        """Test deleting a model by model_id only."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4")
            
            # Delete it
            rows = db.delete_model("claude-sonnet-4")
            
            assert rows == 1
            assert db.get_model("claude-sonnet-4") is None
    
    def test_delete_model_by_id_and_provider(self, temp_db):
        """Test deleting a specific model when multiple providers exist."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4")
            db.create_model("glm", "claude-sonnet-4")
            
            # Delete only the kiro version
            rows = db.delete_model("claude-sonnet-4", provider_type="kiro")
            
            assert rows == 1
            assert db.get_model("claude-sonnet-4", "kiro") is None
            assert db.get_model("claude-sonnet-4", "glm") is not None
    
    def test_delete_model_not_found(self, temp_db):
        """Test deleting a non-existent model returns 0."""
        with Database(temp_db) as db:
            rows = db.delete_model("non-existent")
            assert rows == 0
    
    def test_delete_all_models_with_same_id(self, temp_db):
        """Test deleting all models with the same model_id across providers."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4")
            db.create_model("glm", "claude-sonnet-4")
            db.create_model("openai", "claude-sonnet-4")
            
            # Delete all without specifying provider
            rows = db.delete_model("claude-sonnet-4")
            
            assert rows == 3
            assert db.get_model("claude-sonnet-4") is None


class TestCountModels:
    """Tests for count_models() method."""
    
    def test_count_all_models(self, temp_db):
        """Test counting all models."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4")
            db.create_model("kiro", "claude-haiku-4")
            db.create_model("glm", "glm-4")
            
            count = db.count_models()
            assert count == 3
    
    def test_count_models_by_provider(self, temp_db):
        """Test counting models filtered by provider."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4")
            db.create_model("kiro", "claude-haiku-4")
            db.create_model("glm", "glm-4")
            
            count = db.count_models(provider_type="kiro")
            assert count == 2
            
            count = db.count_models(provider_type="glm")
            assert count == 1
    
    def test_count_enabled_only(self, temp_db):
        """Test counting only enabled models."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4", enabled=True)
            db.create_model("kiro", "claude-haiku-4", enabled=False)
            db.create_model("kiro", "claude-opus-4", enabled=True)
            
            count = db.count_models(enabled_only=True)
            assert count == 2
    
    def test_count_models_empty(self, temp_db):
        """Test counting when no models exist."""
        with Database(temp_db) as db:
            count = db.count_models()
            assert count == 0
    
    def test_count_models_combined_filters(self, temp_db):
        """Test counting with multiple filters."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4", enabled=True)
            db.create_model("kiro", "claude-haiku-4", enabled=False)
            db.create_model("glm", "glm-4", enabled=True)
            
            # Count enabled kiro models
            count = db.count_models(provider_type="kiro", enabled_only=True)
            assert count == 1


class TestModelMethodsIntegration:
    """Integration tests for model methods working together."""
    
    def test_full_crud_cycle(self, temp_db):
        """Test complete CRUD cycle for a model."""
        with Database(temp_db) as db:
            # Create
            model_id = db.create_model(
                provider_type="kiro",
                model_id="claude-sonnet-4",
                display_name="Claude Sonnet 4",
                enabled=True,
                priority=10
            )
            assert model_id > 0
            
            # Read
            model = db.get_model("claude-sonnet-4")
            assert model is not None
            assert model["display_name"] == "Claude Sonnet 4"
            
            # Update
            db.update_model("claude-sonnet-4", priority=20, enabled=False)
            model = db.get_model("claude-sonnet-4")
            assert model["priority"] == 20
            assert model["enabled"] == 0
            
            # Delete
            rows = db.delete_model("claude-sonnet-4")
            assert rows == 1
            assert db.get_model("claude-sonnet-4") is None
    
    def test_list_and_count_consistency(self, temp_db):
        """Test that list_models and count_models return consistent results."""
        with Database(temp_db) as db:
            db.create_model("kiro", "claude-sonnet-4", enabled=True)
            db.create_model("kiro", "claude-haiku-4", enabled=False)
            db.create_model("glm", "glm-4", enabled=True)
            
            # Test all models
            models = db.list_models(enabled_only=False)
            count = db.count_models(enabled_only=False)
            assert len(models) == count
            
            # Test enabled only
            models = db.list_models(enabled_only=True)
            count = db.count_models(enabled_only=True)
            assert len(models) == count
            
            # Test by provider
            models = db.list_models(provider_type="kiro", enabled_only=False)
            count = db.count_models(provider_type="kiro", enabled_only=False)
            assert len(models) == count
