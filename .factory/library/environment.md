# Environment Configuration

Environment variables, external dependencies, and setup notes for the OpenAI provider integration.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

---

## Environment Variables

### OpenAI API Configuration

OpenAI accounts are configured via the admin dashboard, not environment variables. Each account stores:

```json
{
  "api_key": "clp_...",  // Required: API key from OpenAI or relay service
  "base_url": "https://api.openai.com/v1"  // Optional: defaults to official API
}
```

**For third-party relay services:**
- Set `base_url` to the relay service URL (e.g., "https://api.relay-service.com/v1")
- Use the relay service's API key in `api_key` field
- Example relay: codex-for.me, api2d.com, etc.

### Server Configuration

Server configuration is in `.env` file (see `.env` for full options):

```bash
# Server port (default: 8000)
SERVER_PORT=8000

# Server host (default: 0.0.0.0)
SERVER_HOST=0.0.0.0

# Log level (default: INFO)
LOG_LEVEL=INFO
```

## External Dependencies

### OpenAI API / Relay Services

- **Official API**: https://api.openai.com/v1
- **Relay services**: Various third-party services that proxy OpenAI API
- **Authentication**: API key (Bearer token)
- **Rate limits**: Varies by service and account tier

### Python Dependencies

All dependencies are in `requirements.txt`:

```
fastapi
uvicorn[standard]
httpx
loguru
python-dotenv
tiktoken
PyJWT
pytest
pytest-asyncio
hypothesis
mypy
flake8
```

Install with: `python -m pip install -r requirements.txt`

## Platform-Specific Notes

### Windows

- Use `python` or `py` command (not `python3`)
- Use `taskkill` to stop processes (not `kill`)
- Path separators: backslash `\` (but Python handles forward slash `/` too)

### Database

- SQLite database at `E:\kiro-gateway\data\accounts.db`
- Created automatically on first run
- No external database service needed

## Testing Environment

### Test API Key

For integration tests, use the provided API key:
```
clp_3f1bddc7b9048e0bf7f12da1ab86a0ec473e917a4cda2256902740da82943899
```

This is a third-party relay service API key (not official OpenAI).

### Test Database

- Unit tests: Use in-memory SQLite (`:memory:`)
- Integration tests: Use test database or existing database
- Clean up test data after each test run

## Common Issues

### Import Errors

If you get import errors, ensure you're running from the project root:
```bash
cd E:\kiro-gateway
python -m pytest tests/
```

### Port Already in Use

If port 8000 is already in use:
```bash
# Check what's using the port
netstat -ano | findstr :8000

# Kill the process (replace PID with actual process ID)
taskkill /F /PID <PID>
```

### API Connection Errors

If OpenAI API calls fail:
1. Check API key is correct
2. Check base_url is accessible
3. Check network connectivity
4. Check relay service status (if using relay)
