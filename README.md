# OpenAI Proxy

Minimal OpenAI-compatible proxy with flexible per-key rate limiting, key rotation, and provider failover.

## Quick Start

```bash
pip install -r requirements.txt
python -m uvicorn src.app:app --reload
```

Server at `http://localhost:8000`.

## Configuration

Edit `config/config.yaml`. The file includes a schema directive for IDE IntelliSense:

```yaml
# yaml-language-server: $schema=./schema.json
providers:
  my_provider:
    type: openai                           # Required: "openai"
    base_url: https://api.openai.com/v1    # Required: API endpoint URL
    api_keys:                              # Required: list of API keys (or api_key)
      - sk-proj-key1
      - sk-proj-key2
    api_key: sk-proj-single-key            # Alternative: single API key
    rate_limits:                           # Optional: provider-level defaults
      requests_per_minute: 3500
      tokens_per_day: 2000000
    timeout: 60                            # Optional: default 60s

models:
  gpt-4:
    created: 1700000000                    # Optional: unix timestamp
    owned_by: openai                       # Optional: owner name
    providers:
      my_provider:
        priority: 0                        # Optional: lower value = higher priority (boosts score), default 0
        model_id: gpt-4                    # Required: model name sent to provider
        api_keys:                          # Optional: override provider's keys
          - sk-proj-override-key
        api_key: sk-proj-single-key        # Optional: single key override
        rate_limits:                       # Optional: override provider defaults
          requests_per_minute: 3500
          tokens_per_day: 2000000
        multiplier: 1.5                    # Optional: how much each item counts (1.5 = counts as 1.5x)
        token_multiplier: 2.0              # Optional: how much each token counts (2.0 = counts as 2x)
        request_multiplier: 1.5            # Optional: how much each request counts (1.5 = counts as 1.5x)
        max_retries: 3                     # Optional: default 3
```

## All Config Options

**Root:**
- `providers` (required): Map of provider configs
- `models` (required): Map of model configs

**Provider:**
- `type` (required): "openai"
- `base_url` (required): API endpoint URL
- `api_keys` (required if no `api_key`): Array of API keys
- `api_key` (required if no `api_keys`): Single API key
- `rate_limits` (optional): Default rate limits for all models
- `timeout` (optional): Request timeout in seconds, default 60

**Model:**
- `providers` (required): Map of provider instances
- `created` (optional): Unix timestamp
- `owned_by` (optional): Owner name

**Model-Provider Instance:**
- `priority` (optional): Load balancing priority, default 0 (lower = higher)
- `model_id` (required): Model name(s) sent to provider
  - String: Single model ID (e.g., `gpt-4`)
  - Array: Multiple model IDs for round-robin (e.g., `[gpt-4, gpt-4-turbo]`)
- `api_keys` (optional): Override provider's API keys
- `api_key` (optional): Single API key override
- `rate_limits` (optional): Override provider's rate limits
- `multiplier` (optional): How much each item counts toward limits (2.0 = counts as 2x)
- `token_multiplier` (optional): How much each token counts toward token limits
- `request_multiplier` (optional): How much each request counts toward request limits
- `max_retries` (optional): Retry attempts on failure, default 3

**Rate Limits (inside `rate_limits`):**
- `requests_per_minute`, `requests_per_hour`, `requests_per_day`, `requests_per_month`
- `tokens_per_minute`, `tokens_per_hour`, `tokens_per_day`, `tokens_per_month`

## Rate Limiting

Rate limits track usage per API key with sliding windows.

**Example with multipliers:**
```yaml
providers:
  my_provider:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-proj-key

models:
  gpt-4:
    providers:
      my_provider:
        model_id: gpt-4
        rate_limits:
          tokens_per_day: 100000
        token_multiplier: 2.0
```
- Each actual token counts as 2x toward the limit
- Effective limit: 50,000 actual tokens per day
- Tracked limit: 100,000 ÷ 2.0 = 50,000

**Behavior:**
- Per-key tracking: Each key has independent counters
- Global per-key: Usage on any model/provider counts toward that key's limits
- Key rotation: When a key hits a limit, rotates to next available key
- Recovery: Disabled keys retried after 10 minutes
- Multiple limits: ALL configured limits must be satisfied

**Example with multiple keys:**
```yaml
api_keys:
  - key-1
  - key-2
rate_limits:
  tokens_per_day: 100000
```
- Each key: 100k tokens/day independently
- Total capacity: 200k tokens/day across both keys
- If key-1 exhausted, proxy rotates to key-2

## Model ID Round-Robin

When a provider has multiple model IDs configured, requests rotate through them:

```yaml
models:
  claude:
    providers:
      my_provider:
        model_id:
          - claude-3-opus    # First request uses this
          - claude-3-sonnet  # Second request uses this
          - claude-3-opus    # Third request cycles back
```

- All model IDs share the same rate limits and API keys
- Only one model name appears in `/v1/models` (the config key, e.g., `claude`)
- Each request automatically rotates to the next model ID in the list

## Provider Failover

When a request fails, the proxy attempts the next available provider:

- **Max attempts**: 2 providers per request
- **Retry logic**: Each provider gets `max_retries` attempts before moving to the next
- **Error response**: If all attempts fail, returns 503 with error detail

Example with 3 providers configured:
```yaml
models:
  gpt-4:
    providers:
      provider_a:
        priority: 0
      provider_b:
        priority: 1
      provider_c:
        priority: 2
```
Request tries `provider_a` (priority 0), then `provider_b` (priority 1). If both fail, returns error without trying `provider_c`.

## API Endpoints

- `POST /v1/chat/completions` - Chat completion (OpenAI compatible)
  - Returns JSON with `provider` field indicating which provider handled the request
- `GET /v1/models` - List available models
- `GET /v1/providers/stats` - Rate limit usage statistics
- `GET /health` - Health check

## Response Format

All responses are standard OpenAI format with an additional `provider` field:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gpt-4",
  "provider": "my_provider",
  "choices": [...],
  "usage": {...}
}
```

The `provider` field contains the provider instance name from config (e.g., `openai`, `anthropic`, `xai`).

## Provider Prioritization & Scoring

Providers are automatically selected based on a health score that considers:
- **Circuit breaker state**: Open (0), half-open (-50), or closed (0 penalty)
- **Failure rate**: -10 points per consecutive failure, capped at -40
- **Response speed**: -10 points per second of avg response time, capped at -30
- **Priority multiplier**: Each priority level reduces score by 10%
  - Priority 0: 1.0x (full score)
  - Priority 1: 0.9x (10% reduction)
  - Priority 2: 0.8x (20% reduction)

Example: Provider A (priority 0, health 85) vs Provider B (priority 0, health 70):
- Score A: 85 × 1.0 = 85
- Score B: 70 × 1.0 = 70
- Result: Provider A selected

Example with priority: Provider A (priority 1, health 95) vs Provider B (priority 0, health 85):
- Score A: 95 × 0.9 = 85.5
- Score B: 85 × 1.0 = 85
- Result: Provider A still selected (healthy enough to overcome priority penalty)

## Metrics Persistence

Provider metrics are automatically saved to disk on shutdown and restored on startup:

**Saved metrics:**
- Consecutive failures
- Last failure timestamp
- Circuit breaker state
- Average response time
- P95 response time

**Location:** `metrics/provider_metrics.json`

This allows the proxy to "remember" provider health across restarts, avoiding repeatedly trying broken providers.

## Architecture

- **Provider abstraction**: OpenAI-compatible API support with minimal overhead
- **Model registry**: Routes client requests to provider instances by health score
- **Health scoring**: Priority-aware scoring with dynamic provider selection
- **Metrics persistence**: Automatic save/restore of provider performance metrics
- **Rate limiting**: Per-key sliding window tracking (see `src/models.py:RateLimitTracker`)
- **Key rotation**: Automatic failover when keys exhausted (see `src/models.py:ApiKeyRotation`)
- **Multipliers**: Scale how much tokens/requests count toward limits (see `src/registry.py:_apply_multiplier`)
- **Model round-robin**: Automatically rotate through multiple provider model IDs per request

## Token Counting

Tokens taken from provider response: `usage.prompt_tokens + usage.completion_tokens`.

Multipliers affect rate-limit accounting only, not response fields.

If provider omits `usage`, tokens default to 0.

## Creating Custom Providers

See [PROVIDERS.md](./PROVIDERS.md) for in-depth guide on implementing new provider types.

## Development

```bash
python -m py_compile src/*.py     # Check syntax
python test_basic.py              # Run tests
```
