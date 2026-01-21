# OpenAI-Compatible Proxy with Flexible Rate Limiting

A high-performance, resilient proxy server that routes requests to multiple OpenAI-compatible API providers with sophisticated rate limiting, automatic failover, and intelligent load balancing.

## Key Features

### 🎯 OpenAI-Compatible API
- Standard OpenAI API endpoints (`/v1/chat/completions`, `/v1/models`)
- Drop-in replacement for OpenAI SDK clients
- No client-side changes required

### 🔄 Multi-Provider Support
- Route to multiple providers (OpenAI, custom endpoints, local LLMs)
- Automatic failover between providers
- Health-based provider selection
- Priority-based routing

### ⚡ Flexible Rate Limiting
- Configure limits per time period: minute, hour, day, month
- Support for both request counts and token budgets
- Multiple simultaneous limits (e.g., 100 req/min AND 1M tokens/day)
- Per-API-key, per-model, per-provider configuration
- Automatic key rotation when limits are hit

### 🛡️ Resilience Features
- Circuit breaker pattern for failing providers
- Exponential backoff for retries
- Automatic API key rotation across multiple keys
- Round-robin distribution with failure awareness
- 10-minute cooldown recovery for disabled keys

### 📊 Monitoring & Observability
- Real-time provider health scoring
- Per-key usage tracking against limits
- Response time tracking (average, P95)
- Detailed stats endpoint for integration with monitoring systems

## Quick Start

### 1. Installation

```bash
pip install -r requirements.txt
```

### 2. Configure Providers and Models

Edit `config/config.yaml`:

```yaml
providers:
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-proj-your-key-1
      - sk-proj-your-key-2

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 90000
```

### 3. Start the Server

```bash
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000
```

### 4. Make Requests

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Configuration

### Rate Limits

Configure any combination of these limits:

| Limit Type | Example | Description |
|-----------|---------|-------------|
| `requests_per_minute` | 3500 | Max API calls per 60 seconds |
| `requests_per_hour` | 200000 | Max API calls per 3600 seconds |
| `requests_per_day` | 1000000 | Max API calls per 24 hours |
| `requests_per_month` | 10000000 | Max API calls per 30 days |
| `tokens_per_minute` | 90000 | Max tokens per 60 seconds |
| `tokens_per_hour` | 500000 | Max tokens per 3600 seconds |
| `tokens_per_day` | 2000000 | Max tokens per 24 hours |
| `tokens_per_month` | 60000000 | Max tokens per 30 days |

### Example: Multiple Providers with Fallback

```yaml
models:
  gpt-4:
    providers:
      primary:
        priority: 0
        model_id: gpt-4
        api_keys:
          - primary-key-1
          - primary-key-2
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 2000000

      backup:
        priority: 1
        model_id: gpt-4
        rate_limits:
          requests_per_day: 1000
          tokens_per_day: 100000
```

### Example: Budget-Limited Setup

```yaml
models:
  chat:
    providers:
      openai:
        priority: 0
        model_id: gpt-3.5-turbo
        rate_limits:
          requests_per_minute: 100
          tokens_per_day: 100000  # ~$5-10/day
```

## How Rate Limiting Works

1. **Per-API-Key Tracking**: Each key maintains independent counters for requests and tokens
2. **Time Windows**: Tracks actual request timestamps, not calendar boundaries
3. **Multiple Limits**: ALL configured limits must be satisfied
4. **Automatic Rotation**: When a key hits a limit, rotates to the next available key
5. **Recovery**: After 10 minutes, a limited key is retried

### Example with Multiple Keys

```yaml
api_keys:
  - key1
  - key2
  - key3
rate_limits:
  requests_per_minute: 3500
  tokens_per_day: 90000
```

**Effective limits across all keys:**
- 10,500 requests per minute
- 270,000 tokens per day

The proxy automatically distributes load and handles limits transparently.

## API Endpoints

### Chat Completions (OpenAI-Compatible)
```
POST /v1/chat/completions
```

Same format as OpenAI API. See [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat/create).

### List Models
```
GET /v1/models
```

Returns all configured models.

### Provider Statistics
```
GET /v1/providers/stats
```

Returns detailed stats about provider health, rate limit usage, and API key status:

```json
{
  "gpt-4": {
    "model_id": "gpt-4",
    "providers": [
      {
        "enabled": true,
        "priority": 0,
        "circuit_breaker": "closed",
        "health_score": 85.5,
        "avg_response_time": 0.45,
        "p95_response_time": 1.2,
        "api_keys": {
          "keys": [
            {
              "index": 0,
              "failures": 0,
              "enabled": true,
              "rate_limited": false,
              "usage": {
                "requests_per_minute": {"used": 45, "limit": 3500},
                "tokens_per_day": {"used": 125000, "limit": 90000000}
              }
            }
          ]
        }
      }
    ]
  }
}
```

### Health Check
```
GET /health
```

Returns `{"status": "ok"}` if server is running.

## Architecture

### Core Components

- **ModelRegistry**: Loads configuration, manages providers and models
- **RateLimitTracker**: Enforces per-key rate limits with flexible time windows
- **ApiKeyRotation**: Manages multiple keys with round-robin distribution
- **ProviderInstance**: Wraps provider with health tracking and retry logic
- **CircuitBreaker**: Prevents cascading failures
- **ExponentialBackoff**: Intelligent retry delays

### Request Flow

```
Client Request
    ↓
Validate & find model
    ↓
Get available providers (sorted by health)
    ↓
For each provider (with retry):
  - Get next API key (respecting rate limits)
  - Check circuit breaker
  - Make request with exponential backoff
  - Record metrics (speed, tokens)
  - Return on success
    ↓
On failure:
  - Mark key/provider as failed
  - Retry next provider/key
  - Exponential backoff between attempts
    ↓
Return response or HTTP 503 if all fail
```

## Resilience Features

### Circuit Breaker
Prevents cascading failures by stopping requests to failing providers:
- **Closed**: Normal operation
- **Open**: Provider failing, reject requests
- **Half-Open**: Testing recovery

Configuration (defaults):
- Failure threshold: 5 consecutive failures → open
- Success threshold: 2 consecutive successes → closed
- Timeout: 60 seconds before retry

### Exponential Backoff
Delays increase exponentially with each retry attempt:
- Attempt 0: 1 second
- Attempt 1: 2 seconds
- Attempt 2: 4 seconds
- Attempt 3: 8 seconds
- ... up to 300 second maximum

### Health Scoring
Providers are ranked by health (0-100):
- Circuit breaker state
- Consecutive failure count
- Average response time
- Availability

## Monitoring

### Check Rate Limit Usage

```bash
curl http://localhost:8000/v1/providers/stats | jq '.["gpt-4"].providers[0].api_keys'
```

### Identify Rate-Limited Keys

```bash
curl http://localhost:8000/v1/providers/stats | \
  jq '.[] | select(.rate_limited==true)'
```

### Monitor Provider Health

```bash
curl http://localhost:8000/v1/providers/stats | \
  jq '.[] | .providers[] | {health_score, circuit_breaker, enabled}'
```

## Configuration Guide

See `CONFIGURATION.md` for:
- Detailed configuration options
- Multiple provider examples
- Per-model rate limit setup
- Advanced load balancing patterns

## Quick Reference

See `RATE_LIMITS_REFERENCE.md` for:
- Common rate limit presets
- Configuration examples
- Multiple key multiplication
- Best practices

## Deep Dive

See `HOW_IT_WORKS.md` for:
- Detailed architecture explanation
- Rate limiting algorithm details
- Request lifecycle with examples
- Customization guide for new providers

## Getting Started

1. **Quick Setup**: Read `QUICKSTART.md` (5 minutes)
2. **Configure**: Read `CONFIGURATION.md` and edit `config/config.yaml`
3. **Understand**: Read `HOW_IT_WORKS.md` for deeper understanding
4. **Reference**: Use `RATE_LIMITS_REFERENCE.md` for common patterns
5. **Deploy**: Follow security best practices below

## Security Best Practices

### API Keys
- Store keys in environment variables or secrets manager
- Never commit keys to version control
- Rotate keys periodically
- Use different keys for different environments (dev, staging, prod)

### Server Security
- Run behind HTTPS (reverse proxy with TLS)
- Add authentication layer (API keys, OAuth, mTLS)
- Implement rate limiting at proxy level to prevent abuse
- Restrict network access (firewall rules, VPC)
- Monitor for suspicious patterns

### Configuration
- Restrict read access to `config/config.yaml` (chmod 600)
- Audit configuration changes
- Separate configs per environment
- Use secrets management for sensitive data

## Production Deployment

For production deployments, consider:

1. **High Availability**
   - Run multiple proxy instances
   - Load balance across instances
   - Shared state for circuit breakers (Redis/DB optional)

2. **Monitoring**
   - Export metrics to Prometheus/Datadog
   - Alert on rate limit exhaustion
   - Alert on provider failures
   - Track latency percentiles

3. **Logging**
   - Structured logging (JSON)
   - Log all errors and failures
   - Track API key usage
   - Correlate requests across instances

4. **Scaling**
   - Cache rate limit state (optional)
   - Use distributed circuit breaker (optional)
   - Horizontal scaling behind load balancer
   - Database for long-term metrics (optional)

## Troubleshooting

### "All providers failed" Error
- Check at least one provider has active API keys in config
- Verify API keys are valid (check provider account)
- Check `/v1/providers/stats` for key/provider status
- Verify rate limits aren't too restrictive
- Check network connectivity to provider endpoints

### Rate Limiting Too Aggressive
- Review current usage: `curl http://localhost:8000/v1/providers/stats`
- Increase limits in `config/config.yaml` if below provider SLAs
- Add more API keys for higher throughput
- Use layered limits for different policies per time period

### Provider Not Being Used
- Check `priority` value (lower = higher priority)
- Verify in stats endpoint provider is not "open" circuit breaker
- Verify rate limits aren't fully exhausted
- Check provider is enabled in config

### Requests Taking Too Long
- Check average/P95 response times in stats
- Verify network connectivity to provider
- Increase timeout if needed: add `timeout: 120` to provider config
- Consider adding more providers

## What's Changed

**Latest Update**: Cost tracking removed, flexible rate limiting added.

See `CHANGES_SUMMARY.md` for details on:
- What was removed (cost tracking)
- What was added (flexible rate limits)
- Migration guide (if upgrading)
- Breaking changes (none - fully backward compatible)

## Examples

### Example 1: Single Provider, Single Key
```yaml
providers:
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-proj-xxx

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
```

### Example 2: Single Provider, Multiple Keys
```yaml
providers:
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-proj-key1
      - sk-proj-key2
      - sk-proj-key3

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 90000
```

### Example 3: Multiple Providers (Fallback)
```yaml
providers:
  primary:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - key1

  backup:
    type: openai
    base_url: https://api.backup-provider.com/v1
    api_keys:
      - backup-key

models:
  gpt-4:
    providers:
      primary:
        priority: 0
        model_id: gpt-4
        rate_limits:
          requests_per_minute: 3500

      backup:
        priority: 1
        model_id: gpt-4
        rate_limits:
          requests_per_day: 1000
```

## License

MIT

## Contributing

Contributions welcome! Please:
1. Write tests for new features
2. Update documentation
3. Follow existing code style
4. Verify all Python files compile

## Support

For questions or issues:
- Check `CONFIGURATION.md` for config examples
- Check `HOW_IT_WORKS.md` for technical details
- Check `QUICKSTART.md` for quick setup
- Check `RATE_LIMITS_REFERENCE.md` for rate limit patterns