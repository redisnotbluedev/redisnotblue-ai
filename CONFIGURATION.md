# Configuration Guide

This guide explains how to configure the OpenAI-compatible proxy server, including setting up providers, models, and rate limits.

## Overview

The proxy is configured via a YAML file (`config/config.yaml`) that defines:
1. **Providers**: External API services (OpenAI, custom endpoints, etc.)
2. **Models**: Logical models that can route to one or more providers
3. **Rate Limits**: Per-API-key limits on requests and tokens across different time periods

## Basic Structure

```yaml
providers:
  provider_name:
    type: openai                           # Provider type (currently "openai")
    base_url: https://api.example.com/v1   # API endpoint
    api_keys:
      - sk-your-api-key-1
      - sk-your-api-key-2

models:
  model_id:
    created: 1234567890                    # Unix timestamp (optional)
    owned_by: system                       # Owner name (optional)
    providers:
      provider_name:
        priority: 0                        # Lower = higher priority
        model_id: gpt-4                    # Model name at the provider
        api_keys:                          # Override provider's API keys (optional)
          - sk-specific-key-1
          - sk-specific-key-2
        rate_limits:                       # Rate limits for these API keys
          requests_per_minute: 3500
          tokens_per_day: 90000
```

## Detailed Configuration

### Providers Section

Each provider represents a backend API service.

#### Example: Multiple Providers

```yaml
providers:
  openai_main:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-proj-xxx
      - sk-proj-yyy
    timeout: 60                            # Request timeout in seconds (optional)

  openai_backup:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-proj-backup-xxx

  custom_gateway:
    type: openai                           # Can use openai-compatible servers
    base_url: http://localhost:8000/v1
    api_keys:
      - local-key-123
```

**Provider Configuration Options:**

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `type` | string | Yes | Provider type. Currently only `"openai"` is supported. |
| `base_url` | string | Yes | API endpoint URL (without `/chat/completions` suffix) |
| `api_keys` | list | Yes | List of API keys for this provider |
| `timeout` | int | No | Request timeout in seconds (default: 60) |

### Models Section

Each model represents a logical endpoint that can route to one or more providers.

#### Example: Single Provider with Multiple Keys

```yaml
models:
  gpt-4-turbo:
    providers:
      openai_main:
        priority: 0
        model_id: gpt-4-turbo-preview
        api_keys:                          # Use specific keys for this model
          - sk-proj-xxx
          - sk-proj-yyy
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 90000
```

#### Example: Multiple Providers (Fallback/Load Balancing)

```yaml
models:
  gpt-4:
    providers:
      openai_main:
        priority: 0                        # Primary provider
        model_id: gpt-4
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 90000

      openai_backup:
        priority: 1                        # Fallback provider
        model_id: gpt-4
        rate_limits:
          requests_per_minute: 500
          tokens_per_day: 10000

      custom_gateway:
        priority: 2                        # Last resort
        model_id: local-gpt4
        rate_limits:
          requests_per_minute: 100
```

**Model Configuration Options:**

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `providers` | dict | Yes | Map of provider configurations for this model |
| `created` | int | No | Unix timestamp of model creation |
| `owned_by` | string | No | Model owner name |

**Per-Provider Model Configuration:**

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `priority` | int | No | Lower value = higher priority (default: 0). Used for load balancing. |
| `model_id` | string | Yes | The model name/ID to use when calling this provider |
| `api_keys` | list | No | Override provider's API keys for this specific model |
| `rate_limits` | dict | No | Rate limit configuration for these API keys |
| `max_retries` | int | No | Maximum retry attempts if the provider fails (default: 3) |

## Rate Limits Configuration

Rate limits control how many requests and tokens can be consumed per API key within specified time periods.

### Supported Limit Types

You can configure limits for:
- **Requests**: Count of API calls
- **Tokens**: Total tokens (input + output) consumed

### Supported Time Periods

- `minute`: Per 60 seconds
- `hour`: Per 3600 seconds
- `day`: Per 86400 seconds (24 hours)
- `month`: Per 2592000 seconds (30 days)

### Rate Limit Format

The `rate_limits` dict uses keys in the format: `{type}_per_{period}`

```yaml
rate_limits:
  requests_per_minute: 3500        # Max 3500 requests per minute
  requests_per_hour: 200000        # Max 200000 requests per hour
  tokens_per_minute: 90000         # Max 90000 tokens per minute
  tokens_per_day: 2000000          # Max 2 million tokens per day
```

### Examples

#### Example 1: OpenAI Standard Limits

```yaml
rate_limits:
  requests_per_minute: 3500
  tokens_per_minute: 90000
```

#### Example 2: Stricter Limits (Budget Control)

```yaml
rate_limits:
  requests_per_day: 1000           # Max 1000 requests per day
  tokens_per_day: 100000           # Max 100k tokens per day
```

#### Example 3: Multiple Time Periods (Layered Limits)

```yaml
rate_limits:
  requests_per_minute: 100         # Short-term spike protection
  requests_per_hour: 5000          # Hourly quota
  requests_per_day: 50000          # Daily quota
  tokens_per_minute: 10000         # Short-term token limit
  tokens_per_day: 1000000          # Daily token budget
```

#### Example 4: No Limits (Remove Key/Set to Large Value)

```yaml
rate_limits: {}  # No limits configured
# OR omit the rate_limits section entirely
```

## Complete Example Configuration

```yaml
providers:
  openai_prod:
    type: openai
    base_url: https://api.openai.com/v1
    timeout: 60
    api_keys:
      - sk-proj-production-key-1
      - sk-proj-production-key-2

  openai_dev:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-proj-dev-key

  local_llm:
    type: openai
    base_url: http://localhost:8000/v1
    api_keys:
      - local-key

models:
  gpt-4-turbo:
    created: 1700000000
    owned_by: production
    providers:
      openai_prod:
        priority: 0
        model_id: gpt-4-turbo-preview
        api_keys:
          - sk-proj-production-key-1
        rate_limits:
          requests_per_minute: 3500
          tokens_per_minute: 90000
          tokens_per_day: 2000000

      openai_dev:
        priority: 1
        model_id: gpt-4-turbo-preview
        rate_limits:
          requests_per_day: 100
          tokens_per_day: 50000

  gpt-4o:
    providers:
      openai_prod:
        priority: 0
        model_id: gpt-4o
        rate_limits:
          requests_per_minute: 5000
          tokens_per_minute: 200000

  local-gpt:
    providers:
      local_llm:
        priority: 0
        model_id: local-gpt-7b
        rate_limits:
          requests_per_minute: 50
          tokens_per_minute: 50000
```

## How Rate Limiting Works

1. **Per-API-Key Tracking**: Each API key maintains its own request/token counters
2. **Time Window Calculation**: The proxy tracks when requests occurred and calculates usage within each time period
3. **Multiple Limits**: If multiple limits are configured, ALL must be satisfied. If any limit is exceeded, the key is rate-limited
4. **Round-Robin Rotation**: When one key is rate-limited, the proxy automatically rotates to the next available key
5. **Disabled Key Recovery**: After 10 minutes (configurable), a disabled/failed key is retried

## Example Usage Scenarios

### Scenario 1: Budget Control with Multiple Keys

You want to limit daily token usage to stay within budget:

```yaml
models:
  gpt-4:
    providers:
      openai_main:
        priority: 0
        model_id: gpt-4
        api_keys:
          - key-1
          - key-2
          - key-3
        rate_limits:
          tokens_per_day: 500000          # 500k tokens/day budget
          requests_per_minute: 100        # Prevent burst overload
```

### Scenario 2: High-Traffic Endpoint with Rate Limiting

You want to handle high throughput while respecting OpenAI's rate limits:

```yaml
models:
  chat:
    providers:
      openai_primary:
        priority: 0
        model_id: gpt-3.5-turbo
        api_keys:
          - key-1
          - key-2
          - key-3
          - key-4
        rate_limits:
          requests_per_minute: 3500       # OpenAI limit per key
          tokens_per_minute: 90000        # OpenAI token limit
```

With 4 keys, you effectively get 14,000 requests/minute and 360,000 tokens/minute across all keys.

### Scenario 3: Graceful Degradation with Fallbacks

Primary provider for speed, backup for reliability:

```yaml
models:
  production-model:
    providers:
      fast_provider:
        priority: 0
        model_id: fast-gpt
        rate_limits:
          requests_per_minute: 1000

      reliable_provider:
        priority: 1
        model_id: standard-gpt
        rate_limits:
          requests_per_minute: 500
```

## Monitoring Rate Limits

Check current rate limit usage via the `/v1/providers/stats` endpoint:

```bash
curl http://localhost:8000/v1/providers/stats
```

Response includes per-API-key usage:

```json
{
  "gpt-4": {
    "model_id": "gpt-4",
    "providers": [
      {
        "api_keys": {
          "keys": [
            {
              "index": 0,
              "usage": {
                "requests_per_minute": {"used": 45, "limit": 3500},
                "tokens_per_day": {"used": 125000, "limit": 2000000}
              }
            }
          ]
        }
      }
    ]
  }
}
```

## Security Best Practices

1. **Environment Variables**: Store API keys in environment variables, not in the YAML file
   ```yaml
   api_keys:
     - ${OPENAI_KEY_1}
     - ${OPENAI_KEY_2}
   ```

2. **Restrict Access**: Run the proxy behind authentication/authorization
3. **File Permissions**: Restrict read access to `config/config.yaml`
4. **Rotate Keys**: Periodically rotate API keys and update the configuration
5. **Monitor Usage**: Regularly check the stats endpoint to detect anomalies

## Troubleshooting

### "All providers failed" Error

- Check that at least one provider has available API keys
- Verify rate limits aren't too restrictive
- Check network connectivity to provider endpoints

### Rate Limiting Too Aggressive

- Review current usage in `/v1/providers/stats`
- Increase rate limits if they're below actual provider limits
- Add more API keys for round-robin distribution

### Provider Not Being Used

- Check `priority` values (lower = higher priority)
- Verify provider is enabled and not circuit-breaker open
- Check rate limits aren't fully exhausted

## Default Configuration

If no rate limits are specified, the key operates without rate limiting. This is useful for testing or unlimited endpoints.

```yaml
models:
  unlimited-model:
    providers:
      some_provider:
        priority: 0
        model_id: gpt-4
        # No rate_limits specified = no rate limiting
```
