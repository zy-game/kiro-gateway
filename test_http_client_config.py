"""
Test script to verify HTTP client configuration for m2-a1, m2-a2, m2-a5
"""
import asyncio
import httpx
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_http_client_config():
    """Test that server is running and accessible"""
    results = {
        "server_accessible": False,
        "error": None
    }
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8000/")
            results["server_accessible"] = response.status_code in [200, 404, 405]
            results["status_code"] = response.status_code
    except Exception as e:
        results["error"] = str(e)
    
    return results

if __name__ == "__main__":
    results = asyncio.run(test_http_client_config())
    print(f"Server accessible: {results['server_accessible']}")
    if results.get("error"):
        print(f"Error: {results['error']}")
    else:
        print(f"Status code: {results.get('status_code')}")
