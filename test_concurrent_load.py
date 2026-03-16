"""
Test m2-a8 and m2-a9: Concurrent load and memory stability testing
"""
import asyncio
import httpx
import psutil
import time
import json
from datetime import datetime

API_KEY = "[REDACTED]"
BASE_URL = "http://localhost:8000"
SERVER_PID = 47096

async def send_streaming_request(client: httpx.AsyncClient, request_id: int):
    """Send a single streaming request"""
    try:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": f"Test request {request_id}"}],
            "stream": True
        }
        
        async with client.stream("POST", f"{BASE_URL}/v1/chat/completions", 
                                 json=payload, headers=headers, timeout=30.0) as response:
            async for chunk in response.aiter_bytes():
                pass  # Consume the stream
        
        return {"request_id": request_id, "status": "success"}
    except Exception as e:
        return {"request_id": request_id, "status": "error", "error": str(e)}

def get_connection_count():
    """Get current connection count for the server process"""
    try:
        process = psutil.Process(SERVER_PID)
        connections = process.connections()
        
        # Count by state
        states = {}
        for conn in connections:
            state = conn.status
            states[state] = states.get(state, 0) + 1
        
        return {
            "total": len(connections),
            "by_state": states
        }
    except Exception as e:
        return {"error": str(e)}

def get_memory_usage():
    """Get memory usage for the server process"""
    try:
        process = psutil.Process(SERVER_PID)
        mem_info = process.memory_info()
        return {
            "rss_mb": mem_info.rss / 1024 / 1024,  # Resident Set Size in MB
            "vms_mb": mem_info.vms / 1024 / 1024   # Virtual Memory Size in MB
        }
    except Exception as e:
        return {"error": str(e)}

async def test_m2_a8_connection_leaks():
    """Test m2-a8: No connection leaks under concurrent load"""
    print("\n=== Testing m2-a8: Connection Leak Test ===")
    
    # Get baseline connection count
    print("Getting baseline connection count...")
    baseline = get_connection_count()
    print(f"Baseline connections: {json.dumps(baseline, indent=2)}")
    
    # Wait a moment for any existing connections to stabilize
    await asyncio.sleep(2)
    
    # Send 50 concurrent streaming requests
    print("\nSending 50 concurrent streaming requests...")
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        tasks = [send_streaming_request(client, i) for i in range(50)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    elapsed = time.time() - start_time
    print(f"Completed in {elapsed:.2f} seconds")
    
    # Count successes and failures
    successes = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    failures = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "error")
    exceptions = sum(1 for r in results if isinstance(r, Exception))
    
    print(f"Results: {successes} success, {failures} failures, {exceptions} exceptions")
    
    # Wait for connections to close
    print("\nWaiting 5 seconds for connections to close...")
    await asyncio.sleep(5)
    
    # Get final connection count
    final = get_connection_count()
    print(f"Final connections: {json.dumps(final, indent=2)}")
    
    # Analyze results
    baseline_total = baseline.get("total", 0)
    final_total = final.get("total", 0)
    connection_growth = final_total - baseline_total
    
    # Check for CLOSE_WAIT connections
    close_wait_baseline = baseline.get("by_state", {}).get("CLOSE_WAIT", 0)
    close_wait_final = final.get("by_state", {}).get("CLOSE_WAIT", 0)
    close_wait_growth = close_wait_final - close_wait_baseline
    
    print(f"\nConnection growth: {connection_growth} (baseline: {baseline_total}, final: {final_total})")
    print(f"CLOSE_WAIT growth: {close_wait_growth} (baseline: {close_wait_baseline}, final: {close_wait_final})")
    
    # Determine pass/fail
    # Allow some tolerance for transient connections
    passed = connection_growth <= 5 and close_wait_growth <= 2
    
    return {
        "assertion_id": "m2-a8",
        "status": "pass" if passed else "fail",
        "baseline": baseline,
        "final": final,
        "connection_growth": connection_growth,
        "close_wait_growth": close_wait_growth,
        "requests_sent": 50,
        "successes": successes,
        "failures": failures,
        "exceptions": exceptions,
        "elapsed_seconds": elapsed
    }

async def test_m2_a9_memory_stability():
    """Test m2-a9: Memory usage stable under load"""
    print("\n=== Testing m2-a9: Memory Stability Test ===")
    
    # Get baseline memory
    print("Getting baseline memory usage...")
    baseline_mem = get_memory_usage()
    print(f"Baseline memory: {json.dumps(baseline_mem, indent=2)}")
    
    # Wait a moment
    await asyncio.sleep(2)
    
    # Send 100 requests
    print("\nSending 100 requests...")
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        tasks = [send_streaming_request(client, i) for i in range(100)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    elapsed = time.time() - start_time
    print(f"Completed in {elapsed:.2f} seconds")
    
    # Count successes and failures
    successes = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    failures = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "error")
    exceptions = sum(1 for r in results if isinstance(r, Exception))
    
    print(f"Results: {successes} success, {failures} failures, {exceptions} exceptions")
    
    # Wait for cleanup and GC
    print("\nWaiting 5 seconds for cleanup and GC...")
    await asyncio.sleep(5)
    
    # Get final memory
    final_mem = get_memory_usage()
    print(f"Final memory: {json.dumps(final_mem, indent=2)}")
    
    # Calculate memory growth
    baseline_rss = baseline_mem.get("rss_mb", 0)
    final_rss = final_mem.get("rss_mb", 0)
    memory_growth_mb = final_rss - baseline_rss
    memory_growth_percent = (memory_growth_mb / baseline_rss * 100) if baseline_rss > 0 else 0
    
    print(f"\nMemory growth: {memory_growth_mb:.2f} MB ({memory_growth_percent:.2f}%)")
    print(f"Baseline RSS: {baseline_rss:.2f} MB, Final RSS: {final_rss:.2f} MB")
    
    # Determine pass/fail (success criteria: <10% growth)
    passed = memory_growth_percent < 10.0
    
    return {
        "assertion_id": "m2-a9",
        "status": "pass" if passed else "fail",
        "baseline_memory_mb": baseline_rss,
        "final_memory_mb": final_rss,
        "memory_growth_mb": memory_growth_mb,
        "memory_growth_percent": memory_growth_percent,
        "requests_sent": 100,
        "successes": successes,
        "failures": failures,
        "exceptions": exceptions,
        "elapsed_seconds": elapsed
    }

async def main():
    print(f"Starting concurrent load tests at {datetime.now().isoformat()}")
    print(f"Server PID: {SERVER_PID}")
    print(f"Server URL: {BASE_URL}")
    
    # Verify server is running
    try:
        process = psutil.Process(SERVER_PID)
        print(f"Server process found: {process.name()}")
    except psutil.NoSuchProcess:
        print(f"ERROR: Server process {SERVER_PID} not found!")
        return
    
    # Run tests
    results = {}
    
    try:
        results["m2-a8"] = await test_m2_a8_connection_leaks()
    except Exception as e:
        print(f"ERROR in m2-a8: {e}")
        results["m2-a8"] = {"assertion_id": "m2-a8", "status": "blocked", "error": str(e)}
    
    try:
        results["m2-a9"] = await test_m2_a9_memory_stability()
    except Exception as e:
        print(f"ERROR in m2-a9: {e}")
        results["m2-a9"] = {"assertion_id": "m2-a9", "status": "blocked", "error": str(e)}
    
    # Save results
    output_file = "C:/Users/15849/.factory/missions/e1318aaa-e97f-4a29-83bb-3631d7619d26/evidence/m2-resource-management/concurrent-load-retry/test_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n=== Test Results ===")
    print(json.dumps(results, indent=2))
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
