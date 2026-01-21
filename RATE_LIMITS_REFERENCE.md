# Rate Limits Quick Reference

## Configuration Syntax

```yaml
rate_limits:
  requests_per_minute: 3500
  requests_per_hour: 200000
  requests_per_day: 1000000
  requests_per_month: 10000000
  tokens_per_minute: 90000
  tokens_per_hour: 500000
  tokens_per_day: 2000000
  tokens_per_month: 60000000
```

## Common Limit Types

### Requests Per Time Period
- `requests_per_minute`: Max API calls in 60 seconds
- `requests_per_hour`: Max API calls in 3600 seconds
- `requests_per_day`: Max API calls in 86400 seconds (24 hours)
- `requests_per_month`: Max API calls in 2592000 seconds (30 days)

### Tokens Per Time Period
- `tokens_per_minute`: Max tokens in 60 seconds
- `tokens_per_hour`: Max tokens in 3600 seconds
- `tokens_per_day`: Max tokens in 86400 seconds (24 hours)
- `tokens_per_month`: Max tokens in 2592000 seconds (30 days)

**Token count = input_tokens + output_tokens**

## Preset Configurations

### OpenAI Standard (gpt-4-turbo, gpt-4o)
```yaml
rate_limits:
  requests_per_minute: 3500
  tokens_per_minute: 90000
```

### OpenAI Legacy (gpt-3.5-turbo)
```yaml
rate_limits:
  requests_per_minute: 3500
  tokens_per_minute: 90000
```

### Budget Control (100k tokens/day)
```yaml
rate_limits:
  requests_per_minute: 100
  tokens_per_day: 100000
```

### Budget Control (1M tokens/day)
```yaml
rate_limits:
  requests_per_day: 10000
  tokens_per_day: 1000000
```

### High Volume (Multiple Keys)
```yaml
rate_limits:
  requests_per_minute: 3500
  tokens_per_minute: 90000
  # With 4 keys: 14k req/min, 360k tokens/min effective
```

### Development/Testing
```yaml
rate_limits:
  requests_per_hour: 100
  tokens_per_day: 10000
```

### No Limits
```yaml
rate_limits: {}
# OR omit rate_limits entirely
```

## Multiple Keys Multiplication

When you configure multiple API keys with the same rate limits, they work independently:

```yaml
api_keys:
  - key1
  - key2
  - key3
rate_limits:
  requests_per_minute: 3500
  tokens_per_day: 90000
```

**Effective Limits Across All Keys:**
- 10,500 requests per minute (3500 × 3 keys)
- 270,000 tokens per day (90,000 × 3 keys)

The proxy uses round-robin distribution and smart rotation:
- If key1 hits its per-minute limit, proxy switches to key2
- If key2 also hits limit, switches to key3
- After ~10 minutes, key1 is retried
- Seamless failover with exponential backoff

## Layered Limits Strategy

Use multiple time periods to enforce different policies:

```yaml
rate_limits:
  # Spike protection
  requests_per_minute: 100
  tokens_per_minute: 10000
  
  # Hourly quota
  requests_per_hour: 5000
  tokens_per_hour: 100000
  
  # Daily budget
  requests_per_day: 50000
  tokens_per_day: 500000
```

**How it works:**
- Request 1 with 100 tokens at 12:00:00 → ✓ OK (all limits available)
- Request 2-100 with 100 tokens each → ✓ OK
- Request 101 at 12:00:30 → ✗ BLOCKED (requests_per_minute = 100 hit)
- Request 101 at 12:01:05 → ✓ OK (60 seconds passed, minute resets)
- Requests continue through the day
- At end of day 24:00:00, daily counters reset at 00:00:01

## Monitoring Usage

Check current usage against limits:

```bash
curl http://localhost:8000/v1/providers/stats | jq '.["gpt-4"].providers[0].api_keys'
```

Example response:
```json
{
  "total_keys": 3,
  "available_keys": 3,
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
```

## Configuration Per Provider/Model

### Different Limits for Different Models

```yaml
models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 2000000

  gpt-3.5-turbo:
    providers:
      openai:
        priority: 0
        model_id: gpt-3.5-turbo
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 1000000
```

### Different Limits for Different Providers

```yaml
models:
  gpt-4:
    providers:
      primary_provider:
        priority: 0
        model_id: gpt-4
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 2000000

      backup_provider:
        priority: 1
        model_id: gpt-4
        rate_limits:
          requests_per_day: 1000
          tokens_per_day: 100000
```

### Per-API-Key Overrides

```yaml
models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        api_keys:
          - expensive-key-1
          - cheap-key-2
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 2000000
```

Both keys share the same limits. To set different limits per key, use separate provider instances.

## Rate Limit Behavior

### What Happens When Limit Is Hit

1. API key is temporarily disabled
2. Proxy rotates to next available key (if any)
3. Client request continues with new key
4. After 10 minutes (configurable), disabled key is retried

### What Happens When All Keys Are Limited

1. Proxy returns HTTP 503 Service Unavailable
2. Error message indicates rate limiting
3. Client can retry after waiting (see `time_until_available()`)

### Recovery

- **Per-minute limits**: Reset after 60 seconds
- **Per-hour limits**: Reset after 3600 seconds
- **Per-day limits**: Reset after 86400 seconds
- **Per-month limits**: Reset after 2592000 seconds (30 days)

Resets are based on actual request timestamps, not calendar boundaries.

## Troubleshooting

### "All providers failed" with Rate Limit Messages

Check if you're hitting rate limits:
```bash
curl http://localhost:8000/v1/providers/stats | jq '.["model-name"].providers[0].api_keys.keys[] | select(.rate_limited==true)'
```

### Limits Too Strict

Increase limits in `config/config.yaml`:
```yaml
# Before
requests_per_day: 100

# After
requests_per_day: 1000
```

Restart server for changes to take effect.

### Not Using All Keys

Check round-robin distribution:
```bash
curl http://localhost:8000/v1/providers/stats | jq '.["model-name"].providers[0].api_keys'
```

Verify all keys show `enabled: true` and `rate_limited: false`.

### Keys Getting Disabled Frequently

Indicates you're hitting limits. Options:
1. Add more API keys
2. Increase rate limits
3. Reduce client request rate
4. Use layered limits to enforce different policies per time period

## Best Practices

1. **Start Conservative**: Begin with low limits, monitor usage, increase gradually
2. **Use Multiple Keys**: Distribute load across 2-4 keys for resilience
3. **Layer Limits**: Use minute/hour/day limits to enforce different policies
4. **Monitor Regularly**: Check `/v1/providers/stats` daily
5. **Plan Capacity**: Add keys before you hit limits
6. **Document Decisions**: Comment why each limit is set
7. **Test Limits**: Verify behavior when limits are hit

## Examples in Production

### High-Traffic API
```yaml
api_keys:
  - key1
  - key2
  - key3
  - key4
rate_limits:
  requests_per_minute: 3500    # Per-key limit
  tokens_per_day: 2000000      # Per-key limit
# Effective: 14k req/min, 8M tokens/day
```

### Cost-Conscious
```yaml
api_keys:
  - key1
rate_limits:
  tokens_per_day: 500000       # $5-10/day budget
```

### Testing Environment
```yaml
api_keys:
  - dev-key
rate_limits:
  requests_per_hour: 100
  tokens_per_day: 50000
```

### Fallback Configuration
```yaml
models:
  gpt-4:
    providers:
      fast:
        priority: 0
        rate_limits:
          requests_per_minute: 3500

      reliable:
        priority: 1
        rate_limits:
          requests_per_day: 1000
```

Uses `fast` provider until limits hit, then falls back to `reliable`.