# Quick Start Guide

Get the OpenAI-compatible proxy running with rate limiting in 5 minutes.

## 1. Installation

```bash
cd redisnotblue-ai
pip install -r requirements.txt
```

## 2. Basic Configuration

Edit `config/config.yaml` with your API keys and providers:

```yaml
providers:
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-your-api-key-here

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

## 3. Start the Server

```bash
python -m uvicorn src.app:app --host 0.0.0.0 --port 8000
```

The server will start at `http://localhost:8000`

## 4. Test It

```bash
curl http://localhost:8000/v1/models
```

You should see your configured models.

## 5. Make a Request

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

## Common Configuration Patterns

### Pattern 1: Single Provider with Multiple Keys

Use multiple API keys for load distribution and rate limit avoidance:

```yaml
models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        api_keys:
          - sk-key-1
          - sk-key-2
          - sk-key-3
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 90000
```

### Pattern 2: Multiple Providers (Fallback)

Primary provider for speed, backup for reliability:

```yaml
models:
  gpt-4:
    providers:
      openai_primary:
        priority: 0
        model_id: gpt-4
        rate_limits:
          requests_per_minute: 3500
          tokens_per_day: 90000

      openai_backup:
        priority: 1
        model_id: gpt-4
        rate_limits:
          requests_per_day: 1000
```

### Pattern 3: Budget-Limited Requests

Enforce daily token limits:

```yaml
models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        rate_limits:
          requests_per_minute: 100
          tokens_per_day: 100000
```

## Rate Limit Options

Configure any combination of these limits:

| Limit | Example | Description |
|-------|---------|-------------|
| `requests_per_minute` | 3500 | Max requests per 60 seconds |
| `requests_per_hour` | 200000 | Max requests per 3600 seconds |
| `requests_per_day` | 1000000 | Max requests per 24 hours |
| `requests_per_month` | 10000000 | Max requests per 30 days |
| `tokens_per_minute` | 90000 | Max tokens per 60 seconds |
| `tokens_per_hour` | 500000 | Max tokens per 3600 seconds |
| `tokens_per_day` | 2000000 | Max tokens per 24 hours |
| `tokens_per_month` | 60000000 | Max tokens per 30 days |

## Monitoring

Check current rate limit usage:

```bash
curl http://localhost:8000/v1/providers/stats | jq
```

Output shows per-API-key usage against configured limits.

## Environment Variables for Security

Instead of hardcoding keys in `config.yaml`, use environment variables (requires YAML parser that supports this):

```yaml
providers:
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - ${OPENAI_KEY_1}
      - ${OPENAI_KEY_2}
```

Then set:
```bash
export OPENAI_KEY_1=sk-...
export OPENAI_KEY_2=sk-...
```

## Endpoints

### Chat Completions (OpenAI-compatible)
```
POST /v1/chat/completions
```

### List Models
```
GET /v1/models
```

### Provider Statistics
```
GET /v1/providers/stats
```

### Health Check
```
GET /health
```

## What Happens When Rate Limited?

1. Proxy tracks each API key's usage across configured time periods
2. When a key hits a limit, it's automatically disabled
3. Proxy rotates to the next available key
4. After 10 minutes, the disabled key is retried
5. If all keys are rate-limited, request gets HTTP 503 error

With multiple keys, you rarely see rate limit errors.

## Troubleshooting

**Q: "No available providers" error**
- Verify at least one provider has active API keys
- Check `/v1/providers/stats` to see key status
- Verify rate limits aren't too restrictive

**Q: Requests taking a long time**
- Check `/v1/providers/stats` for response times
- Verify network connectivity to provider
- Consider adjusting timeout in provider config

**Q: Provider not being used**
- Check priority value (lower = higher priority)
- Verify provider is not in circuit-breaker "open" state
- Check rate limits aren't exhausted

## Next Steps

- Read [CONFIGURATION.md](CONFIGURATION.md) for detailed options
- Read [LOAD_BALANCING.md](LOAD_BALANCING.md) for advanced features
- Check examples in [examples/](examples/) directory

## Production Deployment

For production use:

1. **Secure API Keys**: Use secrets management (AWS Secrets Manager, HashiCorp Vault, etc.)
2. **Enable HTTPS**: Run behind reverse proxy with TLS
3. **Add Authentication**: Protect the proxy with API keys or OAuth
4. **Monitor Metrics**: Export stats to monitoring system (Prometheus, Datadog, etc.)
5. **Set Up Alerts**: Alert on rate limit exhaustion or provider failures
6. **Use Multiple Instances**: Run multiple proxy instances behind load balancer
7. **Database Persistence**: Store metrics in database for long-term analysis
