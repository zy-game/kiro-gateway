# -*- coding: utf-8 -*-

"""
Unit tests for truncation recovery system.

Tests m4-a1: Parser accepts large tool arguments and detects truncation
Tests that TRUNCATION_RECOVERY=true correctly generates synthetic error messages
when truncation is detected and verifies model receives appropriate notification.

Verifies that:
- Truncation detection works correctly in parser
- Truncation state is saved when TRUNCATION_RECOVERY=true
- Synthetic messages are generated with appropriate content
- Messages are injected into next request correctly
- Model receives clear notification about truncation
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from kiro.utils_pkg.parsers import AwsEventStreamParser
from kiro.utils_pkg.truncation_recovery import (
    should_inject_recovery,
    generate_truncation_tool_result,
    generate_truncation_user_message
)
from kiro.utils_pkg.truncation_state import (
    save_tool_truncation,
    get_tool_truncation,
    save_content_truncation,
    get_content_truncation,
    get_cache_stats
)
from kiro.providers.kiro_provider import KiroProvider
from kiro.models.api import AnthropicMessage


class TestTruncationDetection:
    """Test that parser correctly detects truncation."""
    
    def test_parser_detects_missing_closing_brace(self):
        """Test that parser detects JSON with missing closing brace."""
        parser = AwsEventStreamParser()
        
        # Simulate the actual AWS event stream format with tool call
        # The parser expects tool calls to come through specific event types
        # We need to simulate the tool_use event properly
        
        # Create a tool call event that will be processed
        tool_event = {
            "name": "Execute",
            "toolUseId": "call_123",
            "input": '{"command": "ls -la"'  # Truncated JSON string
        }
        
        # Simulate processing through the parser's internal methods
        parser.current_tool_call = {
            'id': 'call_123',
            'type': 'function',
            'function': {
                'name': 'Execute',
                'arguments': '{"command": "ls -la"'  # Truncated
            }
        }
        
        # Finalize the tool call (this is where truncation detection happens)
        parser._finalize_tool_call()
        
        # Get tool calls
        tool_calls = parser.get_tool_calls()
        
        # Should have one tool call with truncation marker
        assert len(tool_calls) == 1
        assert tool_calls[0].get('_truncation_detected') == True
        assert 'missing' in tool_calls[0].get('_truncation_info', {}).get('reason', '').lower()
    
    def test_parser_detects_unbalanced_braces(self):
        """Test that parser detects JSON with unbalanced braces."""
        parser = AwsEventStreamParser()
        
        # Simulate tool call with unbalanced braces
        parser.current_tool_call = {
            'id': 'call_456',
            'type': 'function',
            'function': {
                'name': 'Execute',
                'arguments': '{"command": "echo test", "nested": {"data": "value"}'  # Missing closing braces
            }
        }
        
        parser._finalize_tool_call()
        tool_calls = parser.get_tool_calls()
        
        assert len(tool_calls) == 1
        assert tool_calls[0].get('_truncation_detected') == True
        assert 'unbalanced' in tool_calls[0].get('_truncation_info', {}).get('reason', '').lower()
    
    def test_parser_detects_unclosed_string(self):
        """Test that parser detects JSON with unclosed string."""
        parser = AwsEventStreamParser()
        
        # Simulate tool call with unclosed string
        parser.current_tool_call = {
            'id': 'call_789',
            'type': 'function',
            'function': {
                'name': 'Execute',
                'arguments': '{"command": "very long command that gets cut off in the middle of a stri'  # Unclosed string
            }
        }
        
        parser._finalize_tool_call()
        tool_calls = parser.get_tool_calls()
        
        assert len(tool_calls) == 1
        assert tool_calls[0].get('_truncation_detected') == True
    
    def test_parser_does_not_flag_valid_json(self):
        """Test that parser does not flag valid JSON as truncated."""
        parser = AwsEventStreamParser()
        
        # Simulate tool call with valid JSON
        parser.current_tool_call = {
            'id': 'call_valid',
            'type': 'function',
            'function': {
                'name': 'Execute',
                'arguments': '{"command": "ls -la"}'  # Valid JSON
            }
        }
        
        parser._finalize_tool_call()
        tool_calls = parser.get_tool_calls()
        
        assert len(tool_calls) == 1
        assert tool_calls[0].get('_truncation_detected') != True


class TestTruncationRecoveryConfig:
    """Test truncation recovery configuration."""
    
    @patch('kiro.core.config.TRUNCATION_RECOVERY', True)
    def test_should_inject_recovery_when_enabled(self):
        """Test that should_inject_recovery returns True when enabled."""
        assert should_inject_recovery() == True
    
    @patch('kiro.core.config.TRUNCATION_RECOVERY', False)
    def test_should_inject_recovery_when_disabled(self):
        """Test that should_inject_recovery returns False when disabled."""
        assert should_inject_recovery() == False


class TestSyntheticMessageGeneration:
    """Test generation of synthetic error messages."""
    
    def test_generate_truncation_tool_result_format(self):
        """Test that synthetic tool_result has correct format."""
        result = generate_truncation_tool_result(
            tool_name="Execute",
            tool_use_id="call_123",
            truncation_info={"size_bytes": 5000, "reason": "missing 2 closing braces"}
        )
        
        # Check format
        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "call_123"
        assert result["is_error"] == True
        assert isinstance(result["content"], str)
        assert len(result["content"]) > 0
    
    def test_generate_truncation_tool_result_content(self):
        """Test that synthetic tool_result contains appropriate messaging."""
        result = generate_truncation_tool_result(
            tool_name="Write",
            tool_use_id="call_456",
            truncation_info={"size_bytes": 10000, "reason": "missing 1 closing brace"}
        )
        
        content = result["content"]
        
        # Should mention API limitation (not model's fault)
        assert "API Limitation" in content or "API limitation" in content.lower()
        
        # Should warn against repeating
        assert "repeat" in content.lower() or "again" in content.lower()
        
        # Should mention truncation
        assert "truncat" in content.lower()
        
        # Should suggest adaptation
        assert "adapt" in content.lower() or "approach" in content.lower()
    
    def test_generate_truncation_user_message_format(self):
        """Test that synthetic user message has correct format."""
        message = generate_truncation_user_message()
        
        assert isinstance(message, str)
        assert len(message) > 0
    
    def test_generate_truncation_user_message_content(self):
        """Test that synthetic user message contains appropriate messaging."""
        message = generate_truncation_user_message()
        
        # Should mention system notice
        assert "System Notice" in message or "system" in message.lower()
        
        # Should mention truncation
        assert "truncat" in message.lower()
        
        # Should not blame the model
        assert "not an error on your part" in message.lower() or "not your fault" in message.lower()
        
        # Should suggest adaptation
        assert "adapt" in message.lower()


class TestTruncationStateManagement:
    """Test truncation state cache management."""
    
    def test_save_and_retrieve_tool_truncation(self):
        """Test saving and retrieving tool truncation info."""
        # Save truncation info
        save_tool_truncation(
            tool_call_id="call_test_123",
            tool_name="Execute",
            truncation_info={"size_bytes": 5000, "reason": "missing 2 closing braces"}
        )
        
        # Retrieve it
        info = get_tool_truncation("call_test_123")
        
        assert info is not None
        assert info.tool_call_id == "call_test_123"
        assert info.tool_name == "Execute"
        assert info.truncation_info["size_bytes"] == 5000
        assert "missing" in info.truncation_info["reason"]
    
    def test_get_tool_truncation_removes_entry(self):
        """Test that get_tool_truncation removes entry after retrieval."""
        # Save truncation info
        save_tool_truncation(
            tool_call_id="call_test_456",
            tool_name="Write",
            truncation_info={"size_bytes": 3000, "reason": "unclosed string"}
        )
        
        # First retrieval should succeed
        info1 = get_tool_truncation("call_test_456")
        assert info1 is not None
        
        # Second retrieval should return None (already consumed)
        info2 = get_tool_truncation("call_test_456")
        assert info2 is None
    
    def test_get_nonexistent_tool_truncation(self):
        """Test that get_tool_truncation returns None for nonexistent ID."""
        info = get_tool_truncation("call_nonexistent")
        assert info is None
    
    def test_save_and_retrieve_content_truncation(self):
        """Test saving and retrieving content truncation info."""
        content = "This is some truncated content that was cut off by the API..."
        
        # Save truncation info
        content_hash = save_content_truncation(content)
        
        assert isinstance(content_hash, str)
        assert len(content_hash) > 0
        
        # Retrieve it
        info = get_content_truncation(content)
        
        assert info is not None
        assert info.message_hash == content_hash
        assert content[:200] in info.content_preview
    
    def test_get_content_truncation_removes_entry(self):
        """Test that get_content_truncation removes entry after retrieval."""
        content = "Another truncated message for testing..."
        
        # Save truncation info
        save_content_truncation(content)
        
        # First retrieval should succeed
        info1 = get_content_truncation(content)
        assert info1 is not None
        
        # Second retrieval should return None (already consumed)
        info2 = get_content_truncation(content)
        assert info2 is None
    
    def test_cache_stats(self):
        """Test that cache stats are accurate."""
        # Clear any existing state by retrieving all
        stats_before = get_cache_stats()
        
        # Save some truncations
        save_tool_truncation("call_stats_1", "Execute", {"size_bytes": 1000, "reason": "test"})
        save_tool_truncation("call_stats_2", "Write", {"size_bytes": 2000, "reason": "test"})
        save_content_truncation("Some content for stats test")
        
        stats = get_cache_stats()
        
        # Should have at least the ones we just added
        assert stats["tool_truncations"] >= 2
        assert stats["content_truncations"] >= 1
        assert stats["total"] >= 3


class TestTruncationRecoveryInjection:
    """Test that truncation recovery messages are injected correctly."""
    
    def test_apply_truncation_recovery_modifies_tool_result(self):
        """Test that _apply_truncation_recovery modifies tool_result blocks."""
        # Create mock provider
        provider = KiroProvider(auth_manager=MagicMock(), model_cache=MagicMock())
        
        # Save truncation info
        save_tool_truncation(
            tool_call_id="call_inject_123",
            tool_name="Execute",
            truncation_info={"size_bytes": 5000, "reason": "missing 2 closing braces"}
        )
        
        # Create messages with tool_result
        messages = [
            AnthropicMessage(
                role="user",
                content=[
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_inject_123",
                        "content": "Original tool output here"
                    }
                ]
            )
        ]
        
        # Apply truncation recovery
        modified_messages, tool_results_modified, content_notices_added = provider._apply_truncation_recovery(messages)
        
        # Should have modified 1 tool_result
        assert tool_results_modified == 1
        assert content_notices_added == 0
        
        # Check that content was modified
        # Handle both dict and Pydantic model
        first_block = modified_messages[0].content[0]
        if hasattr(first_block, 'content'):
            modified_content = first_block.content
        else:
            modified_content = first_block["content"]
        
        assert "API Limitation" in modified_content or "API limitation" in modified_content.lower()
        assert "Original tool output here" in modified_content
    
    def test_apply_truncation_recovery_adds_user_message(self):
        """Test that _apply_truncation_recovery adds user message after truncated content."""
        # Create mock provider
        provider = KiroProvider(auth_manager=MagicMock(), model_cache=MagicMock())
        
        # Create assistant message with content - use string format which is what the code checks
        assistant_content = "This is some assistant response that was truncated..."
        
        # Save truncation info
        save_content_truncation(assistant_content)
        
        # Create messages with string content (not list)
        messages = [
            AnthropicMessage(
                role="assistant",
                content=assistant_content  # String content, not list
            )
        ]
        
        # Apply truncation recovery
        modified_messages, tool_results_modified, content_notices_added = provider._apply_truncation_recovery(messages)
        
        # Should have added 1 content notice
        assert tool_results_modified == 0
        assert content_notices_added == 1
        
        # Should have 2 messages now (original + synthetic user message)
        assert len(modified_messages) == 2
        assert modified_messages[0].role == "assistant"
        assert modified_messages[1].role == "user"
        
        # Check synthetic user message content
        user_content_block = modified_messages[1].content[0]
        if hasattr(user_content_block, 'text'):
            user_content = user_content_block.text
        else:
            user_content = user_content_block["text"]
        
        assert "System Notice" in user_content or "system" in user_content.lower()
        assert "truncat" in user_content.lower()
    
    def test_apply_truncation_recovery_no_modifications_when_no_truncation(self):
        """Test that _apply_truncation_recovery doesn't modify when no truncation."""
        # Create mock provider
        provider = KiroProvider(auth_manager=MagicMock(), model_cache=MagicMock())
        
        # Create messages without any truncation
        messages = [
            AnthropicMessage(
                role="user",
                content=[{"type": "text", "text": "Hello"}]
            ),
            AnthropicMessage(
                role="assistant",
                content=[{"type": "text", "text": "Hi there!"}]
            )
        ]
        
        # Apply truncation recovery
        modified_messages, tool_results_modified, content_notices_added = provider._apply_truncation_recovery(messages)
        
        # Should have no modifications
        assert tool_results_modified == 0
        assert content_notices_added == 0
        assert len(modified_messages) == len(messages)


class TestEndToEndTruncationRecovery:
    """Test end-to-end truncation recovery flow."""
    
    @patch('kiro.core.config.TRUNCATION_RECOVERY', True)
    def test_truncation_detected_saved_and_injected(self):
        """Test complete flow: detection -> save -> inject."""
        # Step 1: Parser detects truncation
        parser = AwsEventStreamParser()
        
        # Simulate truncated tool call
        parser.current_tool_call = {
            'id': 'call_e2e_123',
            'type': 'function',
            'function': {
                'name': 'Execute',
                'arguments': '{"command": "ls -la"'  # Truncated
            }
        }
        
        parser._finalize_tool_call()
        tool_calls = parser.get_tool_calls()
        
        assert len(tool_calls) == 1
        assert tool_calls[0].get('_truncation_detected') == True
        
        # Step 2: Truncation info is saved (simulating streaming code)
        truncation_info = tool_calls[0].get('_truncation_info', {})
        save_tool_truncation(
            tool_call_id="call_e2e_123",
            tool_name="Execute",
            truncation_info=truncation_info
        )
        
        # Step 3: Next request injects recovery message
        provider = KiroProvider(auth_manager=MagicMock(), model_cache=MagicMock())
        
        messages = [
            AnthropicMessage(
                role="user",
                content=[
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_e2e_123",
                        "content": "Error: command failed"
                    }
                ]
            )
        ]
        
        modified_messages, tool_results_modified, content_notices_added = provider._apply_truncation_recovery(messages)
        
        # Step 4: Verify model receives notification
        assert tool_results_modified == 1
        
        # Handle both dict and Pydantic model
        first_block = modified_messages[0].content[0]
        if hasattr(first_block, 'content'):
            modified_content = first_block.content
        else:
            modified_content = first_block["content"]
        
        # Model should see:
        # 1. Clear indication it's an API limitation
        assert "API Limitation" in modified_content or "API limitation" in modified_content.lower()
        
        # 2. Warning not to repeat
        assert "repeat" in modified_content.lower() or "again" in modified_content.lower()
        
        # 3. Original error message
        assert "Error: command failed" in modified_content
        
        # 4. Suggestion to adapt
        assert "adapt" in modified_content.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
