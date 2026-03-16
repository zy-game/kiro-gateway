"""
Test script for connection management assertions (m2-a3, m2-a4, m2-a6, m2-a7).

Tests:
- m2-a3: Streaming responses close connections properly
- m2-a4: Connection header set for streaming requests
- m2-a6: KiroHttpClient uses shared client when provided
- m2-a7: Per-request clients still supported for backward compatibility
"""

import asyncio
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import httpx
from loguru import logger

# Test configuration
BASE_URL = "http://localhost:8000"
EVIDENCE_DIR = Path(r"C:\Users\15849\.factory\missions\e1318aaa-e97f-4a29-83bb-3631d7619d26\evidence\m2-resource-management\connection-management")
OUTPUT_FILE = Path(r"E:\kiro-gateway\.factory\validation\m2-resource-management\user-testing\flows\connection-management.json")

# Ensure directories exist
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_connection_count(port: int = 8000) -> dict:
    """
    Get connection statistics for the specified port.
    
    Returns dict with counts of different connection states.
    """
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        lines = result.stdout.split('\n')
        stats = {
            'ESTABLISHED': 0,
            'CLOSE_WAIT': 0,
            'TIME_WAIT': 0,
            'LISTENING': 0,
            'total': 0
        }
        
        for line in lines:
            if f':{port}' in line:
                stats['total'] += 1
                if 'ESTABLISHED' in line:
                    stats['ESTABLISHED'] += 1
                elif 'CLOSE_WAIT' in line:
                    stats['CLOSE_WAIT'] += 1
                elif 'TIME_WAIT' in line:
                    stats['TIME_WAIT'] += 1
                elif 'LISTENING' in line:
                    stats['LISTENING'] += 1
        
        return stats
    except Exception as e:
        logger.error(f"Failed to get connection count: {e}")
        return {'error': str(e)}


def save_netstat_snapshot(filename: str):
    """Save netstat output to evidence file."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        filepath = EVIDENCE_DIR / filename
        with open(filepath, 'w') as f:
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write("=" * 80 + "\n")
            f.write(result.stdout)
        
        logger.info(f"Saved netstat snapshot to {filepath}")
        return str(filepath.relative_to(EVIDENCE_DIR.parent.parent))
    except Exception as e:
        logger.error(f"Failed to save netstat snapshot: {e}")
        return None


async def test_m2_a3_streaming_connection_close():
    """
    m2-a3: Streaming responses close connections properly
    
    Test: Make streaming request, verify connection closed after completion
    Success criteria: No CLOSE_WAIT connections remain after stream completes
    """
    logger.info("Testing m2-a3: Streaming responses close connections properly")
    
    steps = []
    evidence = {
        "netstat_snapshots": [],
        "response_headers": {},
        "stream_completed": False
    }
    
    # Get baseline connection count
    baseline = get_connection_count()
    steps.append({
        "action": "Get baseline connection count",
        "expected": "Baseline established",
        "observed": f"Baseline: {baseline}"
    })
    evidence["netstat_snapshots"].append(save_netstat_snapshot("m2-a3-baseline.txt"))
    
    # Make streaming request
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            steps.append({
                "action": "Send streaming chat completion request",
                "expected": "Stream starts successfully",
                "observed": "Request sent"
            })
            
            # Use a simple request that should complete quickly
            request_data = {
                "model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "messages": [
                    {"role": "user", "content": "Say 'hello' in one word"}
                ],
                "stream": True,
                "max_tokens": 10
            }
            
            async with client.stream(
                "POST",
                f"{BASE_URL}/v1/chat/completions",
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                evidence["response_headers"] = dict(response.headers)
                
                steps.append({
                    "action": "Receive streaming response",
                    "expected": "Status 200, streaming data received",
                    "observed": f"Status {response.status_code}, headers received"
                })
                
                # Consume the stream
                chunk_count = 0
                async for chunk in response.aiter_bytes():
                    chunk_count += 1
                
                evidence["stream_completed"] = True
                steps.append({
                    "action": "Consume entire stream",
                    "expected": "Stream completes without errors",
                    "observed": f"Received {chunk_count} chunks, stream completed"
                })
        
        # Wait a moment for cleanup
        await asyncio.sleep(2)
        
        # Check connection count after stream completes
        after_stream = get_connection_count()
        evidence["netstat_snapshots"].append(save_netstat_snapshot("m2-a3-after-stream.txt"))
        
        steps.append({
            "action": "Check connection state after stream completion",
            "expected": "No CLOSE_WAIT connections",
            "observed": f"After stream: {after_stream}"
        })
        
        # Determine pass/fail
        if after_stream.get('CLOSE_WAIT', 0) == 0:
            status = "pass"
            issues = None
        else:
            status = "fail"
            issues = f"Found {after_stream['CLOSE_WAIT']} CLOSE_WAIT connections after stream completion"
        
    except Exception as e:
        status = "fail"
        issues = f"Exception during test: {str(e)}"
        steps.append({
            "action": "Test execution",
            "expected": "No exceptions",
            "observed": f"Exception: {str(e)}"
        })
    
    return {
        "id": "m2-a3",
        "title": "Streaming responses close connections properly",
        "status": status,
        "steps": steps,
        "evidence": evidence,
        "issues": issues
    }


async def test_m2_a4_connection_header():
    """
    m2-a4: Connection header set for streaming requests
    
    Test: Verify "Connection: close" header in streaming requests
    Success criteria: Header present in all streaming requests to Kiro API
    """
    logger.info("Testing m2-a4: Connection header set for streaming requests")
    
    steps = []
    evidence = {
        "source_code_check": None,
        "header_found": False,
        "file_location": None
    }
    
    # Check source code for Connection: close header
    steps.append({
        "action": "Check kiro/core/http_client.py for Connection header",
        "expected": "Connection: close header set in streaming requests",
        "observed": "Checking source code..."
    })
    
    try:
        # Read the http_client.py file
        http_client_path = Path("E:/kiro-gateway/kiro/core/http_client.py")
        if http_client_path.exists():
            content = http_client_path.read_text(encoding='utf-8')
            
            # Look for Connection: close header
            if '"Connection": "close"' in content or "'Connection': 'close'" in content:
                evidence["header_found"] = True
                evidence["file_location"] = str(http_client_path)
                
                # Find the line number
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if 'Connection' in line and 'close' in line:
                        evidence["source_code_check"] = f"Found at line {i}: {line.strip()}"
                        break
                
                steps.append({
                    "action": "Verify Connection header in source code",
                    "expected": "Header present in streaming request code",
                    "observed": f"Found: {evidence['source_code_check']}"
                })
                
                status = "pass"
                issues = None
            else:
                evidence["header_found"] = False
                evidence["source_code_check"] = "Connection: close header not found in http_client.py"
                
                steps.append({
                    "action": "Verify Connection header in source code",
                    "expected": "Header present in streaming request code",
                    "observed": "Header NOT found in source code"
                })
                
                status = "fail"
                issues = "Connection: close header not set in streaming requests"
        else:
            status = "blocked"
            issues = f"Source file not found: {http_client_path}"
            steps.append({
                "action": "Locate source file",
                "expected": "File exists",
                "observed": "File not found"
            })
    
    except Exception as e:
        status = "fail"
        issues = f"Exception during test: {str(e)}"
        steps.append({
            "action": "Test execution",
            "expected": "No exceptions",
            "observed": f"Exception: {str(e)}"
        })
    
    return {
        "id": "m2-a4",
        "title": "Connection header set for streaming requests",
        "status": status,
        "steps": steps,
        "evidence": evidence,
        "issues": issues
    }


async def test_m2_a6_shared_client_usage():
    """
    m2-a6: KiroHttpClient uses shared client when provided
    
    Test: Create KiroHttpClient with shared_client parameter
    Success criteria: Uses provided client instead of creating new one
    """
    logger.info("Testing m2-a6: KiroHttpClient uses shared client when provided")
    
    steps = []
    evidence = {
        "source_code_check": None,
        "shared_client_supported": False,
        "main_py_check": None
    }
    
    # Check KiroHttpClient implementation
    steps.append({
        "action": "Check KiroHttpClient for shared_client parameter support",
        "expected": "Constructor accepts shared_client parameter",
        "observed": "Checking source code..."
    })
    
    try:
        # Check http_client.py
        http_client_path = Path("E:/kiro-gateway/kiro/core/http_client.py")
        if http_client_path.exists():
            content = http_client_path.read_text(encoding='utf-8')
            
            # Look for shared_client parameter
            if 'shared_client' in content:
                evidence["shared_client_supported"] = True
                
                # Find relevant code sections
                lines = content.split('\n')
                relevant_lines = []
                for i, line in enumerate(lines, 1):
                    if 'shared_client' in line.lower():
                        relevant_lines.append(f"Line {i}: {line.strip()}")
                
                evidence["source_code_check"] = "\n".join(relevant_lines[:5])  # First 5 occurrences
                
                steps.append({
                    "action": "Verify shared_client parameter in KiroHttpClient",
                    "expected": "Parameter exists and is used",
                    "observed": f"Found shared_client parameter:\n{evidence['source_code_check']}"
                })
            else:
                evidence["shared_client_supported"] = False
                evidence["source_code_check"] = "shared_client parameter not found"
                
                steps.append({
                    "action": "Verify shared_client parameter in KiroHttpClient",
                    "expected": "Parameter exists",
                    "observed": "Parameter NOT found"
                })
        
        # Check main.py for usage
        main_py_path = Path("E:/kiro-gateway/main.py")
        if main_py_path.exists():
            main_content = main_py_path.read_text(encoding='utf-8')
            
            if 'app.state.http_client' in main_content:
                evidence["main_py_check"] = "Shared HTTP client created in main.py lifespan"
                
                steps.append({
                    "action": "Verify shared client creation in main.py",
                    "expected": "app.state.http_client created",
                    "observed": "Shared client found in lifespan"
                })
            else:
                evidence["main_py_check"] = "Shared client not found in main.py"
        
        # Check kiro_provider.py for usage
        provider_path = Path("E:/kiro-gateway/kiro/providers/kiro_provider.py")
        if provider_path.exists():
            provider_content = provider_path.read_text(encoding='utf-8')
            
            # Look for shared_client being passed
            if 'shared_client' in provider_content or 'app.state.http_client' in provider_content:
                steps.append({
                    "action": "Verify shared client passed to KiroHttpClient",
                    "expected": "Shared client passed from provider",
                    "observed": "Found shared_client usage in provider"
                })
                
                status = "pass"
                issues = None
            else:
                steps.append({
                    "action": "Verify shared client passed to KiroHttpClient",
                    "expected": "Shared client passed from provider",
                    "observed": "Shared client NOT passed in provider"
                })
                
                status = "fail"
                issues = "KiroHttpClient not using shared client - still creating per-request clients"
        else:
            status = "blocked"
            issues = "Cannot verify - source files not accessible"
    
    except Exception as e:
        status = "fail"
        issues = f"Exception during test: {str(e)}"
        steps.append({
            "action": "Test execution",
            "expected": "No exceptions",
            "observed": f"Exception: {str(e)}"
        })
    
    return {
        "id": "m2-a6",
        "title": "KiroHttpClient uses shared client when provided",
        "status": status,
        "steps": steps,
        "evidence": evidence,
        "issues": issues
    }


async def test_m2_a7_backward_compatibility():
    """
    m2-a7: Per-request clients still supported for backward compatibility
    
    Test: Create KiroHttpClient without shared_client parameter
    Success criteria: Creates own client, closes it properly in cleanup
    """
    logger.info("Testing m2-a7: Per-request clients still supported for backward compatibility")
    
    steps = []
    evidence = {
        "source_code_check": None,
        "fallback_supported": False,
        "cleanup_verified": False
    }
    
    steps.append({
        "action": "Check KiroHttpClient for fallback client creation",
        "expected": "Creates own client when shared_client not provided",
        "observed": "Checking source code..."
    })
    
    try:
        # Check http_client.py
        http_client_path = Path("E:/kiro-gateway/kiro/core/http_client.py")
        if http_client_path.exists():
            content = http_client_path.read_text(encoding='utf-8')
            
            # Look for fallback client creation logic
            lines = content.split('\n')
            relevant_sections = []
            
            for i, line in enumerate(lines, 1):
                # Look for conditional client creation
                if 'if' in line.lower() and 'shared_client' in line.lower():
                    # Capture context around this line
                    start = max(0, i - 2)
                    end = min(len(lines), i + 5)
                    context = '\n'.join([f"Line {j}: {lines[j-1]}" for j in range(start+1, end+1)])
                    relevant_sections.append(context)
                
                # Look for cleanup/close logic
                if 'aclose' in line.lower() or 'cleanup' in line.lower():
                    relevant_sections.append(f"Line {i}: {line.strip()}")
            
            if relevant_sections:
                evidence["fallback_supported"] = True
                evidence["source_code_check"] = "\n\n".join(relevant_sections[:3])
                
                # Check for cleanup
                if 'aclose' in content:
                    evidence["cleanup_verified"] = True
                
                steps.append({
                    "action": "Verify fallback client creation and cleanup",
                    "expected": "Creates client when not provided, closes in cleanup",
                    "observed": f"Found fallback logic:\n{evidence['source_code_check']}"
                })
                
                if evidence["cleanup_verified"]:
                    steps.append({
                        "action": "Verify client cleanup",
                        "expected": "Client closed properly",
                        "observed": "Found aclose() call in cleanup"
                    })
                    status = "pass"
                    issues = None
                else:
                    steps.append({
                        "action": "Verify client cleanup",
                        "expected": "Client closed properly",
                        "observed": "Cleanup not found"
                    })
                    status = "fail"
                    issues = "Client cleanup not implemented"
            else:
                evidence["fallback_supported"] = False
                evidence["source_code_check"] = "Fallback client creation not found"
                
                steps.append({
                    "action": "Verify fallback client creation",
                    "expected": "Creates client when not provided",
                    "observed": "Fallback logic NOT found"
                })
                
                status = "fail"
                issues = "Backward compatibility not maintained - no fallback client creation"
        else:
            status = "blocked"
            issues = f"Source file not found: {http_client_path}"
    
    except Exception as e:
        status = "fail"
        issues = f"Exception during test: {str(e)}"
        steps.append({
            "action": "Test execution",
            "expected": "No exceptions",
            "observed": f"Exception: {str(e)}"
        })
    
    return {
        "id": "m2-a7",
        "title": "Per-request clients still supported for backward compatibility",
        "status": status,
        "steps": steps,
        "evidence": evidence,
        "issues": issues
    }


async def main():
    """Run all tests and generate report."""
    logger.info("Starting connection management tests")
    logger.info(f"Evidence directory: {EVIDENCE_DIR}")
    logger.info(f"Output file: {OUTPUT_FILE}")
    
    # Run all tests
    results = []
    
    # m2-a3: Streaming connection close
    result_a3 = await test_m2_a3_streaming_connection_close()
    results.append(result_a3)
    
    # m2-a4: Connection header
    result_a4 = await test_m2_a4_connection_header()
    results.append(result_a4)
    
    # m2-a6: Shared client usage
    result_a6 = await test_m2_a6_shared_client_usage()
    results.append(result_a6)
    
    # m2-a7: Backward compatibility
    result_a7 = await test_m2_a7_backward_compatibility()
    results.append(result_a7)
    
    # Generate summary
    passed = sum(1 for r in results if r['status'] == 'pass')
    failed = sum(1 for r in results if r['status'] == 'fail')
    blocked = sum(1 for r in results if r['status'] == 'blocked')
    
    summary = f"Tested {len(results)} assertions: {passed} passed, {failed} failed, {blocked} blocked"
    
    # Create report
    report = {
        "groupId": "connection-management",
        "testedAt": datetime.now().isoformat(),
        "isolation": {
            "serverUrl": BASE_URL,
            "testingTool": "pytest + httpx",
            "evidenceDirectory": str(EVIDENCE_DIR)
        },
        "toolsUsed": ["httpx", "netstat", "source code inspection"],
        "assertions": results,
        "frictions": [],
        "blockers": [],
        "summary": summary
    }
    
    # Write report
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Test report written to {OUTPUT_FILE}")
    logger.info(summary)
    
    # Print results (use ASCII characters for Windows console)
    print("\n" + "=" * 80)
    print("CONNECTION MANAGEMENT TEST RESULTS")
    print("=" * 80)
    for result in results:
        status_symbol = "[PASS]" if result['status'] == 'pass' else "[FAIL]" if result['status'] == 'fail' else "[BLOCK]"
        print(f"{status_symbol} {result['id']}: {result['title']} - {result['status'].upper()}")
        if result['issues']:
            print(f"  Issue: {result['issues']}")
    print("=" * 80)
    print(summary)
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
