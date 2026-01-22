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
- `credits_gain_per_minute/hour/day/month` (optional): Credits this provider gains per period (provider-level)
- `credits_max_per_minute/hour/day/month` (optional): Max credits storable per period (defaults to gain amount)

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
- `credits_per_token` (optional): Credit cost per token (model-level pricing)
- `credits_per_million_tokens` (optional): Credit cost per million tokens (model-level pricing)
- `credits_per_request` (optional): Credit cost per request (model-level pricing)
- `max_retries` (optional): Retry attempts on failure, default 3

**Rate Limits (inside `rate_limits`):**
- `requests_per_minute`, `requests_per_hour`, `requests_per_day`, `requests_per_month`
- `tokens_per_minute`, `tokens_per_hour`, `tokens_per_day`, `tokens_per_month`
- `prompt_tokens_per_minute`, `prompt_tokens_per_hour`, `prompt_tokens_per_day`, `prompt_tokens_per_month`
- `completion_tokens_per_minute`, `completion_tokens_per_hour`, `completion_tokens_per_day`, `completion_tokens_per_month`
- `credits_per_minute`, `credits_per_hour`, `credits_per_day`, `credits_per_month`
  - Note: Credit limits reset at calendar boundaries (`:00` for minutes, `:00` for hours, midnight for days, 1st of month for months)

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

**Rate Limits: Global vs Prompt vs Completion**

You can configure rate limits for:
- `tokens_per_*`: Total tokens (prompt + completion) - global limit
- `prompt_tokens_per_*`: Prompt tokens only
- `completion_tokens_per_*`: Completion tokens only

**Example with separate token limits:**
```yaml
providers:
  my_provider:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-proj-key
    rate_limits:
      requests_per_minute: 3500
      tokens_per_day: 2000000           # Global total cap
      prompt_tokens_per_day: 1200000    # Max input tokens
      completion_tokens_per_day: 800000 # Max output tokens
```

All limits work with time windows: `_per_minute`, `_per_hour`, `_per_day`, `_per_month`.

**How it works:**
- Each limit is checked independently (ALL must pass)
- If you set `tokens_per_day: 1000` and `prompt_tokens_per_day: 600`, both apply
- `prompt_tokens + completion_tokens` cannot exceed `tokens_per_day`
- Multipliers work the same way: each token counts multiplied by `token_multiplier`

**Example combining all limits:**
```yaml
rate_limits:
  tokens_per_day: 1000000              # Total budget
  prompt_tokens_per_day: 700000        # Up to 70% can be prompt
  completion_tokens_per_day: 500000    # Up to 50% can be completion
```
- If 600k prompt + 300k completion used, all limits satisfied (600+300=900 ≤ 1000, 600 ≤ 700, 300 ≤ 500)
- If 750k prompt + 100k completion used, fails (750 > 700, violates prompt limit)

## Credit-Based Rate Limiting

Credits are an alternative (or complementary) way to enforce resource budgets. You configure credit costs at the model level and credit budgets at the provider level. Credit limits reset on calendar boundaries (minute, hour, day, month).

### Overview

Provider-level credits represent the budget or rate quota that a provider allocates to you. This is separate from model-level credit rates, which represent the cost of using a specific model.

**Provider-level config** (provider section):
- How many credits you *gain* each period
- Maximum credits you can *store* each period

**Model-level config** (model/provider section):
- How many credits each *token costs*
- How many credits each *request costs*

### Configuration

**Credit Rates (model-provider instance level):**
- `credits_per_token`: Credit cost per token (e.g., 0.001 = 0.001 credits per token)
- `credits_per_million_tokens`: Credit cost per 1M tokens (e.g., 1.0 = 1 credit per million tokens)
- `credits_per_request`: Credit cost per request (e.g., 5.0 = 5 credits per request)

**Credit Accrual (provider level):**
- `credits_gain_per_minute`: Credits gained every minute
- `credits_gain_per_hour`: Credits gained every hour
- `credits_gain_per_day`: Credits gained every 24 hours (midnight UTC)
- `credits_gain_per_month`: Credits gained monthly (1st of month UTC)

**Credit Limits (in `rate_limits`):**
- `credits_per_minute`: Max credits per minute (resets at `:00` seconds each minute)
- `credits_per_hour`: Max credits per hour (resets at `:00` of each hour)
- `credits_per_day`: Max credits per day (resets at midnight UTC)
- `credits_per_month`: Max credits per month (resets on 1st at 00:00 UTC)

**Optional Max Storage:**
- `credits_max_per_minute`: Max credits storable per minute (defaults to gain amount)
- `credits_max_per_hour`: Max credits storable per hour (defaults to gain amount)
- `credits_max_per_day`: Max credits storable per day (defaults to gain amount)
- `credits_max_per_month`: Max credits storable per month (defaults to gain amount)

### How It Works

**Credit Accrual:**
1. Provider starts with a credit balance equal to `credits_max_*` (or `credits_gain_*` if max not specified)
2. At each calendar boundary, balance resets to `credits_gain_*` amount
3. Credits are shared across all API keys for that provider
4. Multiple models using the same provider share the same credit pool

**Credit Spending:**
1. When a request is made, credits are calculated:
   ```
   request_credits = (total_tokens * credits_per_token) 
                   + (total_tokens / 1_000_000 * credits_per_million_tokens)
                   + credits_per_request
   ```

2. If insufficient credits are available, the request is rate-limited

3. Credits are spent from the balance after the request succeeds

**Calendar Resets:**

Credits reset at these boundaries (UTC):
- **Minute**: At :00 seconds (every minute)
- **Hour**: At :00 minutes (hourly)
- **Day**: At 00:00 (midnight UTC daily)
- **Month**: 1st of month at 00:00 UTC

Each period is tracked independently. You can set limits on any combination of periods.

### Configuration Examples

**Basic Configuration:**

```yaml
providers:
  openai:
    type: openai
    api_keys:
      - "sk-key-1"
      - "sk-key-2"
    
    # Provider-level: credits this provider gives us
    credits_gain_per_minute: 100.0
    credits_gain_per_hour: 1000.0
    credits_gain_per_day: 10000.0
    credits_gain_per_month: 100000.0
    
    # Optional: max storage (defaults to gain amount)
    credits_max_per_day: 15000.0    # Can store more than daily gain

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: "gpt-4"
        
        # Model-level: how much using this model costs
        credits_per_token: 0.001        # 1 credit per 1000 tokens
        credits_per_request: 1.0        # 1 credit per request
        
        # Alternative: credits per million tokens
        # credits_per_million_tokens: 1000.0
```

**High-Frequency API:**

```yaml
providers:
  custom_api:
    type: openai
    api_keys: ["key1"]
    
    # High frequency with per-minute caps
    credits_gain_per_minute: 500.0
    credits_gain_per_hour: 20000.0     # 500 * 60
    
models:
  fast-model:
    providers:
      custom_api:
        model_id: "fast"
        credits_per_token: 0.0001       # Very cheap
        credits_per_request: 0.1        # Minimal overhead
```

**Daily Budget:**

```yaml
providers:
  budget_provider:
    type: openai
    api_keys: ["key1", "key2"]
    
    # Daily allowance, no per-minute throttling
    credits_gain_per_day: 5000.0
    # No minute/hour limits

models:
  standard:
    providers:
      budget_provider:
        model_id: "gpt-3.5"
        credits_per_token: 0.0005
        credits_per_request: 1.0
```

**Tiered Pricing:**

```yaml
providers:
  openai:
    type: openai
    api_keys: ["key1"]
    credits_gain_per_day: 10000.0

models:
  gpt-4-expensive:
    providers:
      openai:
        model_id: "gpt-4"
        credits_per_million_tokens: 30.0    # $0.03 per 1M tokens
        credits_per_request: 2.0

  gpt-3.5-cheap:
    providers:
      openai:
        model_id: "gpt-3.5-turbo"
        credits_per_million_tokens: 0.5     # $0.0005 per 1M tokens
        credits_per_request: 0.1
```

### Behavior When Credits Exhausted

When a model instance runs out of credits:

1. The system attempts to rotate to the next API key
2. If all keys are exhausted, the request fails with rate limit error
3. Credits replenish at the next calendar boundary
4. Different time periods reset independently

### Monitoring

Check current credit balance for an API key:
```python
# After creating registry
tracker = api_key_rotation.rate_limiters[api_key]
balance = tracker.get_credit_balance()
# Returns: {"minute": 450.0, "hour": 18000.0, "day": 8750.0}
```

### Best Practices

1. **Set all periods you care about**: If you only set `credits_gain_per_day`, minute/hour tracking is disabled.

2. **Match provider limits**: Set `credits_max_*` to allow buffer capacity if needed.

3. **Budget for burst**: Use `credits_max_per_minute` higher than `credits_gain_per_minute` to allow brief bursts.

4. **Use multiple keys**: Configure different API keys with the same provider to distribute load.

5. **Set model costs accurately**: Ensure `credits_per_token/request` match your actual costs.

### Troubleshooting

**Problem**: Requests frequently rate-limited despite high daily limit
- **Solution**: Check per-minute/hour limits. May need to increase `credits_gain_per_minute`.

**Problem**: Different models have different credit costs
- **Solution**: Configure separate API keys for each pricing tier. Global tracker can't distinguish between models sharing same keys.

**Problem**: Credits not replenishing
- **Solution**: Verify calendar boundary has passed. Check system time is UTC-correct.

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
- **Rate limiting**: Per-key calendar-based tracking (see `src/models.py:RateLimitTracker`)
- **Key rotation**: Automatic failover when keys exhausted (see `src/models.py:ApiKeyRotation`)
- **Multipliers**: Scale how much tokens/requests count toward limits (see `src/registry.py:_apply_multiplier`)
- **Model round-robin**: Automatically rotate through multiple provider model IDs per request
- **Credit-based budgeting**: Provider-level credit accrual and model-level pricing (see `src/models.py:RateLimitTracker`)

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
