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
