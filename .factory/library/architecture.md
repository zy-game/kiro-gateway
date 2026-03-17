# Architecture

Architectural decisions and patterns for the OpenAI provider integration.

**What belongs here:** Design decisions, patterns discovered, integration approaches, trade-offs made.

---

## Provider Architecture

### BaseProvider Interface

All providers implement the `BaseProvider` abstract class defined in `kiro/providers/base.py`:

```python
class BaseProvider(ABC):
    @abstractmethod
    async def chat_openai(self, account, model, messages, ...) -> AsyncIterator[bytes]:
        """Return OpenAI-compatible SSE stream"""
        
    @abstractmethod
    async def chat_anthropic(self, account, model, messages, ...) -> AsyncIterator[bytes]:
        """Return Anthropic-compatible SSE stream"""
        
    @abstractmethod
    def get_supported_models(self, db_manager=None) -> List[str]:
        """Return list of supported model names"""
```

### OpenAI Provider Design

The OpenAI provider follows the same pattern as GLMProvider:

**File structure:**
```
kiro/providers/openai_provider.py  # Main provider class
kiro/converters/openai.py          # Format converters (if needed)
```

**Key design decisions:**

1. **Simple API Key Authentication**
   - No OAuth or refresh tokens (unlike Kiro provider)
   - API key stored in `account.config.api_key`
   - Follows GLM pattern for simplicity

2. **Configurable Base URL**
   - Supports third-party relay services
   - `account.config.base_url` defaults to official API
   - Enables users in restricted regions to use relay services

3. **Format Conversion**
   - OpenAI → OpenAI: Pass-through (no conversion needed)
   - Anthropic → OpenAI: Convert in `chat_anthropic` method
   - OpenAI → Anthropic: Convert response format

4. **Streaming Implementation**
   - Use `httpx.stream()` for streaming requests
   - Parse SSE format: `data: {...}\n\n`
   - Yield chunks as bytes
   - Handle `[DONE]` marker

5. **Error Handling**
   - Map HTTP status codes to user-friendly messages
   - 401 → "Authentication failed"
   - 429 → "Rate limit exceeded" + trigger cooldown
   - 5xx → "Server error"
   - Network errors → "Connection failed"

## Account Management Integration

### Account Config Schema

```python
{
    "api_key": str,      # Required: API key
    "base_url": str      # Optional: defaults to "https://api.openai.com/v1"
}
```

### Account Selection

The `AccountManager` selects accounts based on:
1. Account type matches provider
2. Account is not in cooldown
3. Account has not exceeded usage limit
4. Higher priority accounts selected first

### Cooldown Mechanism

When an account hits rate limit (429):
1. `AccountManager.mark_rate_limited(account_id)` is called
2. Account enters cooldown (exponential backoff: 30s, 60s, 120s, ...)
3. Subsequent requests skip cooling accounts
4. Cooldown clears after timeout or successful request

## Model Management

### Model Storage

Models are stored in the `models` table:

```sql
CREATE TABLE models (
    id INTEGER PRIMARY KEY,
    provider_type TEXT NOT NULL,
    model_id TEXT NOT NULL,
    display_name TEXT,
    enabled INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 0,
    UNIQUE(provider_type, model_id)
)
```

### Default Models

OpenAI provider includes these default models:
- gpt-4
- gpt-4-turbo
- gpt-4-turbo-preview
- gpt-3.5-turbo
- gpt-3.5-turbo-16k

Models can be synced via: `POST /admin/models/sync/openai`

## Request Flow

### OpenAI Format Request

```
Client → POST /v1/chat/completions
    ↓
OpenAI Routes (kiro/routes/openai.py)
    ↓
Provider Router (kiro/core/provider_router.py)
    ↓
OpenAI Provider (kiro/providers/openai_provider.py)
    ↓
OpenAI API (via httpx)
    ↓
Response → Client
```

### Anthropic Format Request

```
Client → POST /v1/messages
    ↓
Anthropic Routes (kiro/routes/auth.py or similar)
    ↓
Provider Router
    ↓
OpenAI Provider.chat_anthropic()
    ↓
Convert Anthropic → OpenAI format
    ↓
OpenAI Provider.chat_openai()
    ↓
OpenAI API
    ↓
Convert OpenAI → Anthropic format
    ↓
Response → Client
```

## Testing Strategy

### Unit Tests

- Mock httpx calls to avoid real API requests
- Test format conversion logic
- Test error handling paths
- Test model support checking

### Integration Tests

- Use real API calls with test API key
- Test streaming responses
- Test function calling
- Test error scenarios (invalid key, rate limits)

### Manual Testing

- Use curl to test endpoints
- Use admin dashboard to manage accounts
- Verify streaming in real-time
- Test with different relay services

## Performance Considerations

### Connection Pooling

- Use shared httpx client for connection reuse
- Accept `shared_client` parameter in chat methods
- Reduces connection overhead for multiple requests

### Streaming Efficiency

- Stream responses immediately (don't buffer)
- Use async/await for non-blocking I/O
- Yield chunks as they arrive

### Error Recovery

- Retry on transient errors (network issues)
- Don't retry on auth errors (401)
- Implement exponential backoff for rate limits

## Security Considerations

### API Key Storage

- Store in database (encrypted at rest)
- Never log API keys
- Never commit API keys to git
- Mask API keys in admin UI (show last 8 chars only)

### Input Validation

- Validate all user inputs
- Sanitize error messages (don't leak sensitive info)
- Rate limit API requests per user

### HTTPS

- Use HTTPS for production deployments
- Validate SSL certificates
- Don't disable SSL verification
