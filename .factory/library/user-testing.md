# User Testing Strategy

## Validation Surface

This mission involves testing the following surfaces:

### 1. Web UI (Browser)
- **Entry point**: http://localhost:8000
- **Pages**: 
  - `/login` - Login page
  - `/admin` - Admin dashboard (requires authentication)
- **Tools**: Manual browser testing (Chrome, Firefox, Edge)
- **Authentication**: Session-based (JWT token in httponly cookie)

### 2. API Endpoints (HTTP)
- **Base URL**: http://localhost:8000
- **Endpoints**:
  - `/v1/chat/completions` - OpenAI-compatible API
  - `/admin/*` - Admin management API
  - `/auth/*` - Authentication API
- **Tools**: pytest + httpx for automated testing
- **Authentication**: API key (Bearer token) or session cookie

### 3. Database (SQLite)
- **File**: E:\kiro-gateway\data\accounts.db
- **Tools**: sqlite3 CLI, Python sqlite3 module
- **Testing**: Direct database queries to verify data integrity

## Validation Concurrency

### Web UI Testing
- **Max concurrent validators**: 1
- **Rationale**: Browser testing is manual and sequential. Each test requires human interaction and observation. Running multiple browser instances would not improve efficiency and could cause confusion.
- **Resource cost**: ~500 MB RAM per browser instance, negligible CPU

### API Testing
- **Max concurrent validators**: 5
- **Rationale**: API tests are automated and lightweight. The FastAPI server can handle multiple concurrent requests. On a machine with 16 GB RAM and 12 CPU cores, with ~6 GB baseline usage, we have 10 GB * 0.7 = 7 GB usable headroom. Each httpx test client uses ~50 MB RAM. 5 concurrent validators = ~250 MB, well within budget.
- **Resource cost**: ~50 MB RAM per validator, minimal CPU

### Database Testing
- **Max concurrent validators**: 1
- **Rationale**: SQLite has limited concurrent write support. While multiple readers are fine, concurrent writes can cause locking issues. Database tests should run sequentially to avoid SQLITE_BUSY errors.
- **Resource cost**: Negligible (~10 MB RAM, minimal CPU)

## Test Setup Requirements

### Prerequisites
1. **Server must be running**: `py main.py` (or already running on port 8000)
2. **Database must exist**: `E:\kiro-gateway\data\accounts.db`
3. **Admin user must exist**: Default admin/admin123 (created on first startup)
4. **Test dependencies installed**: pytest, pytest-asyncio, httpx

### Environment Variables
- Use existing `.env` file configuration
- No additional environment setup needed for testing

### Test Data
- Use existing database for integration tests
- Create temporary in-memory databases for unit tests
- Clean up test data after each test run

## Validation Approach

### Per-Worker Validation
Each worker performs manual verification as part of their work procedure:
- Backend workers: Run pytest, test API endpoints with curl/httpx
- Frontend workers: Test in browser, check console for errors

### End-of-Milestone Validation
After all features in a milestone complete:
1. **Scrutiny validator**: Reviews code quality, test coverage, documentation
2. **User testing validator**: Runs comprehensive end-to-end tests across all surfaces

### Accepted Limitations
- No automated browser testing (Selenium/Playwright not configured)
- Manual testing required for UI changes
- Limited concurrent database testing due to SQLite constraints

---

## Flow Validator Guidance: Database Testing

### Isolation Strategy
Each flow validator should use **in-memory SQLite databases** (`:memory:`) for complete isolation. This allows concurrent testing without file locking issues.

### Testing Approach
1. **Import and instantiate**: Verify the Database class can be imported and instantiated
2. **Execute operations**: Call Database methods directly (no server needed)
3. **Verify results**: Check return values and database state
4. **Test error handling**: Trigger error conditions and verify exceptions

### Shared State to Avoid
- Do NOT use the production database file (`E:\kiro-gateway\data\accounts.db`)
- Do NOT modify any files outside your test scope
- Do NOT start the FastAPI server (not needed for Database class testing)

### Resource Constraints
- Max memory per validator: ~100 MB (in-memory database + test overhead)
- Max concurrent validators: 5 (Database testing is CPU-bound, not I/O-bound)
- Test timeout: 60 seconds per assertion group

### Evidence Collection
- Save test output to evidence files
- Include any error messages or stack traces
- Document which Database methods were tested

### Example Test Pattern
```python
from kiro.core.database import Database

# Create isolated test database
db = Database(":memory:")

# Test operation
result = db.get_account(account_id=1)

# Verify result
assert result is not None
assert result['id'] == 1
```

---

## Flow Validator Guidance: Parser Testing

### Isolation Strategy
Parser testing for m4-tool-limits focuses on the **kiro/utils_pkg/parsers.py** module. Each flow validator should test the parser in isolation without requiring a running server or database.

### Testing Approach
1. **Import parser module**: Verify the parser can be imported
2. **Test with various argument sizes**: Test with arguments from 1KB to 1MB
3. **Verify truncation detection**: Ensure truncation is properly detected and reported
4. **Test error messages**: Verify error messages are clear and actionable
5. **Test TRUNCATION_RECOVERY**: Verify synthetic error generation when enabled

### Shared State to Avoid
- Do NOT modify the parser source code during testing
- Do NOT use production API keys or credentials
- Do NOT start the FastAPI server (not needed for parser testing)
- Each validator should test independently without shared state

### Resource Constraints
- Max memory per validator: ~200 MB (for large argument buffers)
- Max concurrent validators: 3 (parser testing is CPU and memory intensive)
- Test timeout: 120 seconds per assertion group (large arguments take time)

### Evidence Collection
- Save test output showing argument sizes tested
- Include any error messages or truncation warnings
- Document parser buffer size configuration
- Save performance metrics (time, memory usage)

### Example Test Pattern
```python
import sys
sys.path.insert(0, 'E:/kiro-gateway')

from kiro.utils_pkg.parsers import StreamingAnthropicParser

# Test with large argument
large_arg = "x" * (100 * 1024)  # 100KB
parser = StreamingAnthropicParser()

# Simulate streaming chunks
# ... test parser behavior ...
```
