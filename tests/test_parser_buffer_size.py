# -*- coding: utf-8 -*-

"""
Tests for parser buffer size configuration.

Tests that the AwsEventStreamParser can handle large tool arguments
up to the configured buffer size limit (default 1MB).
"""

import json
import pytest
from kiro.utils_pkg.parsers import AwsEventStreamParser
from kiro.core.config import TOOL_ARGUMENT_BUFFER_SIZE


class TestParserBufferSize:
    """Test parser buffer size handling."""
    
    def test_small_arguments_work(self):
        """Test that small arguments (< 1KB) work correctly."""
        parser = AwsEventStreamParser()
        
        # Create a small tool call
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-123",
            "input": {"command": "echo hello"}
        }
        
        # Simulate AWS event stream format
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        # Should parse successfully
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        assert tool_calls[0]['function']['name'] == 'Execute'
    
    def test_large_arguments_100kb(self):
        """Test that 100KB arguments work correctly."""
        parser = AwsEventStreamParser()
        
        # Create a large argument (100KB)
        large_arg = "x" * (100 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-large-100kb",
            "input": {"command": large_arg}
        }
        
        # Simulate AWS event stream format
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        # Should parse successfully
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        assert tool_calls[0]['function']['name'] == 'Execute'
        
        # Verify argument size
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 100 * 1024
    
    def test_large_arguments_1mb(self):
        """Test that 1MB arguments work correctly (at the limit)."""
        parser = AwsEventStreamParser()
        
        # Create a large argument (close to 1MB, accounting for JSON overhead)
        # Use 900KB to leave room for JSON structure
        large_arg = "x" * (900 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-large-1mb",
            "input": {"command": large_arg}
        }
        
        # Simulate AWS event stream format
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        # Should parse successfully (with warning logged)
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        assert tool_calls[0]['function']['name'] == 'Execute'
        
        # Verify argument size
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 900 * 1024
    
    def test_buffer_size_limit_configurable(self):
        """Test that buffer size limit can be configured."""
        # Create parser with custom limit (10KB)
        parser = AwsEventStreamParser(buffer_size_limit=10 * 1024)
        
        # Create a small argument (5KB)
        small_arg = "x" * (5 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-custom-limit",
            "input": {"command": small_arg}
        }
        
        # Should work fine
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
    
    def test_buffer_size_limit_exceeded_warning(self):
        """Test that exceeding buffer size limit still processes data gracefully."""
        # Create parser with small limit (1KB)
        parser = AwsEventStreamParser(buffer_size_limit=1024)
        
        # Create a large argument (10KB)
        large_arg = "x" * (10 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-exceed-limit",
            "input": {"command": large_arg}
        }
        
        # Should still process despite exceeding limit (graceful degradation)
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        # Should still parse successfully (warning is logged but processing continues)
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        assert tool_calls[0]['function']['name'] == 'Execute'
    
    def test_buffer_size_limit_disabled(self):
        """Test that buffer size limit can be disabled (set to 0)."""
        # Create parser with no limit
        parser = AwsEventStreamParser(buffer_size_limit=0)
        
        # Create a very large argument (2MB, exceeds default limit)
        large_arg = "x" * (2 * 1024 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-no-limit",
            "input": {"command": large_arg}
        }
        
        # Should work without warning
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
    
    def test_default_buffer_size_from_config(self):
        """Test that parser uses default buffer size from config."""
        parser = AwsEventStreamParser()
        
        # Should use TOOL_ARGUMENT_BUFFER_SIZE from config
        assert parser.buffer_size_limit == TOOL_ARGUMENT_BUFFER_SIZE
        assert parser.buffer_size_limit == 1048576  # 1MB
    
    def test_multiple_chunks_accumulate(self):
        """Test that multiple chunks accumulate in buffer correctly."""
        parser = AwsEventStreamParser()
        
        # Split a tool call across multiple chunks
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-multi-chunk",
            "input": {"command": "x" * 1000}
        }
        
        json_str = json.dumps(tool_call)
        chunk_size = 100
        
        # Feed in small chunks
        for i in range(0, len(json_str), chunk_size):
            chunk = json_str[i:i+chunk_size].encode('utf-8')
            parser.feed(chunk)
        
        # Should parse successfully after all chunks
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        assert tool_calls[0]['function']['name'] == 'Execute'
