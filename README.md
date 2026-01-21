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
        priority: 0                        # Optional: lower = higher priority, default 0
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
- `model_id` (required): Model name sent to provider; can be string or array (primary ID + aliases)
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

## Model Aliases

Single provider instance with multiple model names (aliases):

```yaml
models:
  gpt-3.5-turbo:
    providers:
      my_provider:
        model_id:
          - gpt-3.5-turbo        # Primary ID
          - gpt-3.5-turbo-16k    # Alias
          - gpt-3.5              # Alias
```

All aliases share the same provider instance, rate limits, and API keys.

## API Endpoints

- `POST /v1/chat/completions` - Chat completion (OpenAI compatible)
- `GET /v1/models` - List available models
- `GET /v1/providers/stats` - Rate limit usage statistics
- `GET /health` - Health check

## IntelliSense Setup

The config file includes `# yaml-language-server: $schema=./schema.json` at the top, which enables IntelliSense in editors that support yaml-language-server.

### Zed

Install yaml-language-server:
```bash
npm install -g yaml-language-server
```

Create or edit `.zed/settings.json`:
```json
{
  "languages": {
    "YAML": {
      "language_servers": ["yaml-language-server"]
    }
  }
}
```

### VS Code

Install "YAML" extension by Red Hat. Schema is auto-detected.

### JetBrains IDEs

Settings → Languages & Frameworks → Schemas and DTDs → JSON Schema Mappings:
- Schema: `./config/schema.json`
- File pattern: `config/config.yaml`

## Architecture

- **Provider abstraction**: OpenAI-compatible API support
- **Model registry**: Routes client requests to provider instances
- **Rate limiting**: Per-key sliding window tracking (see `src/models.py:RateLimitTracker`)
- **Key rotation**: Automatic failover when keys exhausted (see `src/models.py:ApiKeyRotation`)
- **Multipliers**: Scale how much tokens/requests count toward limits (see `src/registry.py:_apply_multiplier`)

## Token Counting

Tokens taken from provider response: `usage.prompt_tokens + usage.completion_tokens`.

Multipliers affect rate-limit accounting only, not response fields.

If provider omits `usage`, tokens default to 0.

## Multiplier Truth (from source code)

See `src/models.py` line 39 and `src/registry.py` line 71:

```python
# models.py:39 - How tokens are counted
counted_tokens = int(tokens * self.token_multiplier)  # 2.0 multiplier = counts as 2x

# registry.py:71 - How limits are adjusted
multiplied[key] = int(value / final_multiplier)  # Divided by multiplier to get effective limit
```

With `tokens_per_day: 100000` and `token_multiplier: 2.0` at instance level:
- Tracked limit: 100000 ÷ 2.0 = 50000
- 25000 actual tokens used → 50000 counted tokens → limit hit

## Development

```bash
python -m py_compile src/*.py     # Check syntax
python test_basic.py              # Run tests
```
