"""
Tests for enhanced error messages in parser truncation handling.

Verifies that _finalize_tool_call() provides detailed, actionable error
messages when tool call arguments are truncated.

Note: These tests verify that truncation detection and metadata storage work correctly.
The actual error message formatting is tested by inspecting the truncation_info structure.
"""

import json
import pytest

from kiro.utils_pkg.parsers import AwsEventStreamParser


class TestParserErrorMessages:
    """Test enhanced error messages for truncated tool calls."""
    
    def test_truncation_info_stored_in_tool_call(self):
        """Truncation metadata should be stored in tool call for recovery system."""
        parser = AwsEventStreamParser()
        
        parser.current_tool_call = {
            "id": "exec-333",
            "type": "function",
            "function": {
                "name": "Execute",
                "arguments": '{"cmd": "test'  # Truncated
            }
        }
        
        parser._finalize_tool_call()
        tool_calls = parser.tool_calls
        
        assert len(tool_calls) == 1
        tool_call = tool_calls[0]
        
        # Check that truncation metadata is attached
        assert tool_call.get('_truncation_detected') is True, \
            "Tool call should be marked as truncated"
        assert '_truncation_info' in tool_call, \
            "Tool call should include truncation diagnostic info"
        
        truncation_info = tool_call['_truncation_info']
        assert truncation_info['is_truncated'] is True
        assert 'reason' in truncation_info
        assert 'size_bytes' in truncation_info
    
    def test_truncation_info_includes_details(self):
        """Truncation info should include size and reason details."""
        parser = AwsEventStreamParser()
        
        parser.current_tool_call = {
            "id": "read-456",
            "type": "function",
            "function": {
                "name": "Read",
                "arguments": '{"file": "test.py", "nested": {'  # Unbalanced braces
            }
        }
        
        parser._finalize_tool_call()
        tool_call = parser.tool_calls[0]
        
        truncation_info = tool_call['_truncation_info']
        assert truncation_info['size_bytes'] > 0, "Should report size in bytes"
        assert 'brace' in truncation_info['reason'].lower(), "Should explain truncation reason"
    
    def test_non_truncated_json_has_no_truncation_info(self):
        """Non-truncated malformed JSON should not have truncation metadata."""
        parser = AwsEventStreamParser()
        
        # Malformed but balanced JSON
        parser.current_tool_call = {
            "id": "test-222",
            "type": "function",
            "function": {
                "name": "Test",
                "arguments": '{invalid json but balanced}'
            }
        }
        
        parser._finalize_tool_call()
        tool_call = parser.tool_calls[0]
        
        # Should not be marked as truncated
        assert tool_call.get('_truncation_detected') is not True, \
            "Non-truncated errors should not be marked as truncated"
    
    def test_truncation_detection_for_large_arguments(self):
        """Large truncated arguments should be detected."""
        parser = AwsEventStreamParser(buffer_size_limit=10000)
        
        large_content = "y" * 500
        parser.current_tool_call = {
            "id": "long-444",
            "type": "function",
            "function": {
                "name": "LongCommand",
                "arguments": '{"data": "' + large_content  # Truncated
            }
        }
        
        parser._finalize_tool_call()
        tool_call = parser.tool_calls[0]
        
        assert tool_call.get('_truncation_detected') is True
        truncation_info = tool_call['_truncation_info']
        assert truncation_info['size_bytes'] > 500, "Should report actual size"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
