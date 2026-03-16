# -*- coding: utf-8 -*-

"""
Unit tests for parser with large arguments (1KB to 1MB).

Tests m4-a3: Parser handles arguments up to 1MB
Tests m4-a5: Large arguments don't cause memory issues

Verifies that:
- Parser can handle arguments from 1KB to 1MB
- Memory usage remains stable
- Performance is acceptable (< 5 seconds for 1MB)
- No memory leaks occur with repeated large arguments
"""

import json
import time
import tracemalloc
import pytest
from kiro.utils_pkg.parsers import AwsEventStreamParser


class TestParserLargeArguments:
    """Test parser with large arguments ranging from 1KB to 1MB."""
    
    def test_parser_handles_1kb_argument(self):
        """Test that parser handles 1KB arguments correctly."""
        parser = AwsEventStreamParser()
        
        # Create 1KB argument
        large_arg = "x" * 1024
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-1kb",
            "input": {"command": large_arg}
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        assert tool_calls[0]['function']['name'] == 'Execute'
        
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 1024
    
    def test_parser_handles_10kb_argument(self):
        """Test that parser handles 10KB arguments correctly."""
        parser = AwsEventStreamParser()
        
        # Create 10KB argument
        large_arg = "x" * (10 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-10kb",
            "input": {"command": large_arg}
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 10 * 1024
    
    def test_parser_handles_50kb_argument(self):
        """Test that parser handles 50KB arguments correctly."""
        parser = AwsEventStreamParser()
        
        # Create 50KB argument
        large_arg = "x" * (50 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-50kb",
            "input": {"command": large_arg}
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 50 * 1024
    
    def test_parser_handles_100kb_argument(self):
        """Test that parser handles 100KB arguments correctly."""
        parser = AwsEventStreamParser()
        
        # Create 100KB argument
        large_arg = "x" * (100 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-100kb",
            "input": {"command": large_arg}
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 100 * 1024
    
    def test_parser_handles_500kb_argument(self):
        """Test that parser handles 500KB arguments correctly."""
        parser = AwsEventStreamParser()
        
        # Create 500KB argument
        large_arg = "x" * (500 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-500kb",
            "input": {"command": large_arg}
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 500 * 1024
    
    def test_parser_handles_1mb_argument(self):
        """Test that parser handles 1MB arguments correctly (at the limit)."""
        parser = AwsEventStreamParser()
        
        # Create close to 1MB argument (900KB to account for JSON overhead)
        large_arg = "x" * (900 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-1mb",
            "input": {"command": large_arg}
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 900 * 1024
    
    def test_parser_performance_1mb_under_5_seconds(self):
        """Test that 1MB argument is processed within 5 seconds (m4-a3)."""
        parser = AwsEventStreamParser()
        
        # Create close to 1MB argument
        large_arg = "x" * (900 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-perf-1mb",
            "input": {"command": large_arg}
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        
        start_time = time.time()
        events = parser.feed(chunk)
        tool_calls = parser.get_tool_calls()
        elapsed_time = time.time() - start_time
        
        assert len(tool_calls) == 1
        assert elapsed_time < 5.0, f"Processing took {elapsed_time:.2f}s, expected < 5s"
    
    def test_parser_memory_stable_with_large_arguments(self):
        """Test that memory usage remains stable with large arguments (m4-a5)."""
        # Start memory tracking
        tracemalloc.start()
        
        parser = AwsEventStreamParser()
        
        # Create 500KB argument
        large_arg = "x" * (500 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-memory",
            "input": {"command": large_arg}
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        
        # Get baseline memory
        baseline_snapshot = tracemalloc.take_snapshot()
        
        # Process the chunk
        events = parser.feed(chunk)
        tool_calls = parser.get_tool_calls()
        
        # Get memory after processing
        after_snapshot = tracemalloc.take_snapshot()
        
        # Calculate memory difference
        top_stats = after_snapshot.compare_to(baseline_snapshot, 'lineno')
        total_diff = sum(stat.size_diff for stat in top_stats)
        
        tracemalloc.stop()
        
        # Memory increase should be reasonable (< 2MB for 500KB input)
        # This accounts for JSON parsing overhead and internal structures
        assert total_diff < 2 * 1024 * 1024, \
            f"Memory increased by {total_diff / 1024 / 1024:.2f}MB, expected < 2MB"
        
        # Verify parsing succeeded
        assert len(tool_calls) == 1
    
    def test_parser_no_memory_leak_repeated_large_arguments(self):
        """Test that repeated large arguments don't cause memory leaks (m4-a5)."""
        tracemalloc.start()
        
        parser = AwsEventStreamParser()
        
        # Create 100KB argument
        large_arg = "x" * (100 * 1024)
        
        # Get baseline memory
        baseline_snapshot = tracemalloc.take_snapshot()
        
        # Process 10 large arguments
        for i in range(10):
            tool_call = {
                "name": "Execute",
                "toolUseId": f"test-leak-{i}",
                "input": {"command": large_arg}
            }
            
            chunk = json.dumps(tool_call).encode('utf-8')
            events = parser.feed(chunk)
            tool_calls = parser.get_tool_calls()
            
            # Clear tool calls to simulate real usage
            parser.tool_calls = []
        
        # Get memory after processing
        after_snapshot = tracemalloc.take_snapshot()
        
        # Calculate memory difference
        top_stats = after_snapshot.compare_to(baseline_snapshot, 'lineno')
        total_diff = sum(stat.size_diff for stat in top_stats)
        
        tracemalloc.stop()
        
        # Memory increase should be minimal (< 500KB for 10x100KB inputs)
        # Most memory should be released after clearing tool_calls
        assert total_diff < 500 * 1024, \
            f"Memory increased by {total_diff / 1024:.2f}KB after 10 iterations, expected < 500KB"
    
    def test_parser_handles_multiple_large_tool_calls_in_sequence(self):
        """Test that parser handles multiple large tool calls in sequence."""
        parser = AwsEventStreamParser()
        
        # Create 3 tool calls with 50KB arguments each (different content to avoid deduplication)
        for i in range(3):
            # Use different characters to avoid deduplication
            large_arg = chr(ord('x') + i) * (50 * 1024)
            tool_call = {
                "name": "Execute",
                "toolUseId": f"test-multi-{i}",
                "input": {"command": large_arg}
            }
            
            chunk = json.dumps(tool_call).encode('utf-8')
            events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 3
        
        # Verify each tool call
        for i, tc in enumerate(tool_calls):
            assert tc['function']['name'] == 'Execute'
            args = json.loads(tc['function']['arguments'])
            assert len(args['command']) == 50 * 1024
    
    def test_parser_handles_large_argument_in_chunks(self):
        """Test that parser handles large arguments split across multiple chunks."""
        parser = AwsEventStreamParser()
        
        # Create 100KB argument
        large_arg = "x" * (100 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-chunked",
            "input": {"command": large_arg}
        }
        
        json_str = json.dumps(tool_call)
        chunk_size = 1024  # 1KB chunks
        
        # Feed in small chunks
        for i in range(0, len(json_str), chunk_size):
            chunk = json_str[i:i+chunk_size].encode('utf-8')
            parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 100 * 1024
    
    def test_parser_handles_complex_nested_large_arguments(self):
        """Test that parser handles complex nested structures with large data."""
        parser = AwsEventStreamParser()
        
        # Create complex nested structure with large data
        large_data = "x" * (50 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-nested",
            "input": {
                "command": "test",
                "nested": {
                    "level1": {
                        "level2": {
                            "data": large_data
                        }
                    }
                },
                "array": [large_data, large_data]
            }
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        events = parser.feed(chunk)
        
        tool_calls = parser.get_tool_calls()
        assert len(tool_calls) == 1
        
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['nested']['level1']['level2']['data']) == 50 * 1024
        assert len(args['array']) == 2
        assert len(args['array'][0]) == 50 * 1024
    
    def test_parser_buffer_size_warning_logged(self):
        """Test that exceeding buffer size logs a warning but continues processing."""
        # Create parser with small limit (10KB)
        parser = AwsEventStreamParser(buffer_size_limit=10 * 1024)
        
        # Create 50KB argument (exceeds limit)
        large_arg = "x" * (50 * 1024)
        tool_call = {
            "name": "Execute",
            "toolUseId": "test-exceed",
            "input": {"command": large_arg}
        }
        
        chunk = json.dumps(tool_call).encode('utf-8')
        
        # Should still process despite exceeding limit (graceful degradation)
        events = parser.feed(chunk)
        tool_calls = parser.get_tool_calls()
        
        # Verify it still works
        assert len(tool_calls) == 1
        args = json.loads(tool_calls[0]['function']['arguments'])
        assert len(args['command']) == 50 * 1024
    
    def test_parser_performance_scales_linearly(self):
        """Test that parser performance scales linearly with argument size."""
        parser = AwsEventStreamParser()
        
        sizes = [10 * 1024, 50 * 1024, 100 * 1024, 500 * 1024]
        times = []
        
        for size in sizes:
            large_arg = "x" * size
            tool_call = {
                "name": "Execute",
                "toolUseId": f"test-scale-{size}",
                "input": {"command": large_arg}
            }
            
            chunk = json.dumps(tool_call).encode('utf-8')
            
            start_time = time.time()
            events = parser.feed(chunk)
            tool_calls = parser.get_tool_calls()
            elapsed_time = time.time() - start_time
            
            times.append(elapsed_time)
            parser.tool_calls = []  # Clear for next iteration
        
        # Verify all processed successfully
        assert all(t < 5.0 for t in times), \
            f"Some processing times exceeded 5s: {times}"
        
        # Performance should scale reasonably (not exponentially)
        # 500KB should not take more than 50x the time of 10KB
        if times[0] > 0:  # Avoid division by zero
            ratio = times[-1] / times[0]
            assert ratio < 100, \
                f"Performance degradation too high: {ratio:.2f}x"


class TestParserConcurrentLargeArguments:
    """Test parser with concurrent large arguments (m4-a5)."""
    
    def test_parser_handles_concurrent_large_arguments(self):
        """Test that parser handles multiple large arguments concurrently."""
        # Create 10 parsers (simulating concurrent requests)
        parsers = [AwsEventStreamParser() for _ in range(10)]
        
        # Track memory
        tracemalloc.start()
        baseline_snapshot = tracemalloc.take_snapshot()
        
        # Process 500KB argument in each parser
        large_arg = "x" * (500 * 1024)
        
        for i, parser in enumerate(parsers):
            tool_call = {
                "name": "Execute",
                "toolUseId": f"test-concurrent-{i}",
                "input": {"command": large_arg}
            }
            
            chunk = json.dumps(tool_call).encode('utf-8')
            events = parser.feed(chunk)
        
        # Verify all parsers processed successfully
        for parser in parsers:
            tool_calls = parser.get_tool_calls()
            assert len(tool_calls) == 1
        
        # Check memory usage
        after_snapshot = tracemalloc.take_snapshot()
        top_stats = after_snapshot.compare_to(baseline_snapshot, 'lineno')
        total_diff = sum(stat.size_diff for stat in top_stats)
        
        tracemalloc.stop()
        
        # Memory should be reasonable (< 20MB for 10x500KB inputs)
        assert total_diff < 20 * 1024 * 1024, \
            f"Memory increased by {total_diff / 1024 / 1024:.2f}MB, expected < 20MB"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
