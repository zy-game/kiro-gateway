# Flow Validator Guidance: API Testing (m2-resource-management)

## Testing Surface
HTTP API endpoints testing via pytest + httpx

## Isolation Strategy

### Shared Resources
- **FastAPI server**: Single instance running on localhost:8000 (shared across all validators)
- **SQLite database**: E:\kiro-gateway\data\accounts.db (shared, read-only for testing)
- **HTTP connection pool**: Managed by app.state.http_client (shared)

### Isolation Boundaries
Each flow validator operates independently by:
1. **Using separate httpx test clients**: Each validator creates its own httpx.AsyncClient for making requests
2. **Testing different assertion groups**: Validators test non-overlapping sets of assertions
3. **Read-only operations**: Validators only observe system behavior, don't modify shared state
4. **Separate evidence directories**: Each validator writes to its own evidence subdirectory

### What NOT to Modify
- Do NOT restart the FastAPI server
- Do NOT modify the database file
- Do NOT modify application code
- Do NOT change environment variables
- Do NOT kill or interfere with other validators' processes

## Concurrency Limits
- **Max concurrent validators**: 3
- **Rationale**: API testing is I/O-bound. The server can handle concurrent requests. Each validator uses ~50 MB RAM. With 3 validators = ~150 MB, well within available resources.

## Testing Approach

### For HTTP Client Configuration Assertions (m2-a1, m2-a2, m2-a5)
1. Read main.py source code to verify http_client setup
2. Make test requests and observe connection behavior
3. Check that shared client is properly configured with limits

### For Connection Management Assertions (m2-a3, m2-a4, m2-a6, m2-a7)
1. Make streaming requests to /v1/chat/completions
2. Monitor connection state during and after requests
3. Verify connections are properly closed (no CLOSE_WAIT)

### For Load Testing Assertions (m2-a8, m2-a9)
1. Send concurrent requests (50-100) to the API
2. Monitor connection count and memory usage
3. Verify no resource leaks after requests complete

## Evidence Collection
Save to: C:\Users\15849\.factory\missions\e1318aaa-e97f-4a29-83bb-3631d7619d26\evidence\m2-resource-management\<group-id>\

Include:
- Test output logs
- Connection state snapshots (netstat output)
- Memory usage measurements
- Any error messages or stack traces
- Code snippets showing configuration

## Resource Constraints
- Max memory per validator: ~100 MB
- Max test duration: 5 minutes per assertion group
- Network timeout: 30 seconds per request
