# Round-Robin API Keys & Retry Logic

## Overview

The LLM Provider Proxy now supports **multiple API keys per provider** with **round-robin load balancing** and **intelligent retry logic**. This enables:

- **Load Distribution**: Spread requests across multiple API keys to avoid rate limits
- **Failover**: Automatically switch to backup keys if one is rate-limited or fails
- **Cost Optimization**: Use cheaper keys first, expensive keys as backup
- **High Availability**: Multiple keys per provider ensure continuity even if keys are revoked

## Architecture

### API Key Rotation System

Each provider instance manages multiple API keys using the `ApiKeyRotation` class:

```
Request arrives
    ↓
Provider Instance (with API key rotation)
    ├─ Round-robin to next available key
    ├─ Check if key is disabled (< 3 failures) or in cooldown
    └─ Return next usable key
         ↓
    Try API call with selected key
         ├─ Success → mark_success() → reset failures
         └─ Failure → mark_failure() → check if should disable
         
Key Lifecycle:
    0 failures: Enabled
    1-2 failures: Enabled but marked for potential disability
    3+ failures: DISABLED (enter 10-minute cooldown)
    After cooldown: Re-enabled automatically
```

### Retry Logic

The system now has **two levels of retries**:

1. **API Key Retries**: Try different keys within a provider (default: 3 attempts)
2. **Provider Retries**: Try different providers if all keys exhausted (fallback providers)

```
Request for Model X
    ↓
Provider 1 (priority 0)
    ├─ Key 1 → Try → Fails
    ├─ Key 2 → Try → Fails
    └─ Key 3 → Try → Succeeds ✓ RETURN RESPONSE
    
If all keys fail:
    ↓
Provider 2 (priority 1)
    ├─ Key 1 → Try → Succeeds ✓ RETURN RESPONSE
    
If all providers fail:
    └─ Return 503 Service Unavailable
```

## Configuration

### Option 1: Multiple Keys as List (Recommended)

```yaml
providers:
  openai:
    type: openai
    api_keys:
      - ${OPENAI_API_KEY_1}
      - ${OPENAI_API_KEY_2}
      - ${OPENAI_API_KEY_3}
    base_url: https://api.openai.com/v1
```

### Option 2: Single Key (Backward Compatible)

```yaml
providers:
  openai:
    type: openai
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
```

### Option 3: Environment Variable with Comma-Separated Keys

```yaml
providers:
  openai:
    type: openai
    api_keys_env: OPENAI_PROD_KEYS
    base_url: https://api.openai.com/v1
```

```bash
export OPENAI_PROD_KEYS=sk-key1,sk-key2,sk-key3
```

### Model Configuration with Retry Settings

```yaml
models:
  gpt-4:
    owned_by: openai
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        max_retries: 3                # Max retries per API key
        cooldown_seconds: 600         # 10-minute cooldown for disabled keys
      openai-backup:
        priority: 1
        model_id: gpt-4
        max_retries: 3
        cooldown_seconds: 600
```

## Data Models

### ApiKeyRotation

Manages multiple API keys with round-robin rotation and failure tracking:

```python
@dataclass
class ApiKeyRotation:
    api_keys: List[str]                              # List of API keys
    current_index: int = 0                           # Current position in rotation
    consecutive_failures: dict = {}                  # Failures per key
    disabled_keys: dict = {}                         # Disabled keys with timestamps
    cooldown_seconds: int = 600                      # Cooldown period

    def get_next_key() -> str:
        """Get next available key using round-robin"""

    def mark_failure(api_key: str) -> None:
        """Mark API key as failed, disable if 3+ failures"""

    def mark_success(api_key: str) -> None:
        """Reset API key failures, mark as succeeded"""

    def get_status() -> dict:
        """Get status of all API keys"""
```

### ProviderInstance (Updated)

Enhanced with API key rotation and retry tracking:

```python
@dataclass
class ProviderInstance:
    provider: Provider
    priority: int
    model_id: str
    api_key_rotation: Optional[ApiKeyRotation] = None   # NEW
    enabled: bool = True
    consecutive_failures: int = 0
    last_failure: Optional[float] = None
    retry_count: int = 0                                # NEW
    max_retries: int = 3                                # NEW

    def get_current_api_key() -> Optional[str]:
        """Get next API key using round-robin"""

    def mark_api_key_failure(api_key: str) -> None:
        """Mark specific API key as failed"""

    def mark_api_key_success(api_key: str) -> None:
        """Mark specific API key as succeeded"""

    def increment_retry_count() -> None:
        """Increment request retry counter"""

    def should_retry_request() -> bool:
        """Check if we have retries left for this provider"""
```

## API Endpoints

### POST /v1/chat/completions (Updated)

With round-robin API key retry logic:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}],
    "temperature": 0.7
  }'
```

**Behavior:**
1. Gets model from registry
2. Gets available providers (sorted by priority)
3. For each provider:
   - Resets retry counter
   - Loops up to `max_retries` times:
     - Gets next API key (round-robin)
     - Attempts request with that key
     - On success: marks key success, returns response
     - On failure: marks key failure, increments retry counter
   - If retries exhausted: marks provider failure, tries next provider
4. If all providers exhausted: returns 503

### GET /v1/providers/status

Get detailed status of all providers and their API keys:

```bash
curl http://localhost:8000/v1/providers/status
```

**Response:**
```json
{
  "gpt-4": {
    "model_id": "gpt-4",
    "providers": [
      {
        "name": "openai",
        "priority": 0,
        "enabled": true,
        "model_id": "gpt-4",
        "consecutive_failures": 0,
        "last_failure": null,
        "api_key_status": {
          "total_keys": 3,
          "available_keys": 3,
          "keys": [
            {
              "index": 0,
              "failures": 0,
              "enabled": true,
              "disabled_since": null
            },
            {
              "index": 1,
              "failures": 1,
              "enabled": true,
              "disabled_since": null
            },
            {
              "index": 2,
              "failures": 3,
              "enabled": false,
              "disabled_since": 1705766400.123
            }
          ]
        }
      }
    ]
  }
}
```

### GET /v1/providers/stats

Get performance statistics about providers:

```bash
curl http://localhost:8000/v1/providers/stats
```

## Use Cases

### Use Case 1: Rate Limit Avoidance

**Problem**: Single API key gets rate-limited after 500 requests/minute

**Solution**: Use 3 API keys, rotate through them

```yaml
providers:
  openai:
    api_keys:
      - ${KEY_1}  # 500 req/min
      - ${KEY_2}  # 500 req/min
      - ${KEY_3}  # 500 req/min
    # Now you can handle ~1500 requests/minute
```

### Use Case 2: Cost Optimization

**Problem**: Want to use cheap models by default, expensive models as backup

**Solution**: Configure multiple providers with cost-based priority

```yaml
models:
  gpt-4:
    providers:
      openai-cheap:
        priority: 0      # Try cheap API keys first
        max_retries: 2
      openai-expensive:
        priority: 1      # Fallback to expensive keys
        max_retries: 3
```

### Use Case 3: Key Rotation

**Problem**: Rotate API keys quarterly for security

**Solution**: Update config with new keys, old keys automatically disabled after 3 failures

```yaml
# Week 1: Old and new keys
providers:
  openai:
    api_keys:
      - ${NEW_KEY_1}    # Brand new
      - ${NEW_KEY_2}
      - ${OLD_KEY_1}    # Being phased out
      - ${OLD_KEY_2}
```

### Use Case 4: Multi-Account Setup

**Problem**: Multiple OpenAI accounts for organization

**Solution**: Configure multiple providers, each with their own keys

```yaml
providers:
  openai-team-a:
    api_keys:
      - ${TEAM_A_KEY_1}
      - ${TEAM_A_KEY_2}

  openai-team-b:
    api_keys:
      - ${TEAM_B_KEY_1}
      - ${TEAM_B_KEY_2}

models:
  gpt-4:
    providers:
      openai-team-a:
        priority: 0
      openai-team-b:
        priority: 1
```

## Round-Robin Behavior

### Key Selection Algorithm

```python
def get_next_key(api_keys, current_index, disabled_keys):
    """
    1. Check and re-enable keys if cooldown expired
    2. Get list of available (not disabled) keys
    3. Starting from current_index, find next available key
    4. Return that key and advance current_index
    """
    
    # Step 1: Re-enable keys after cooldown
    check_cooldowns()
    
    # Step 2: Get available keys
    available = [k for k in api_keys if k not in disabled_keys]
    
    if not available:
        # All disabled, re-enable oldest one
        oldest = min(disabled_keys.items(), key=lambda x: x[1])
        available = [oldest[0]]
    
    # Step 3-4: Round-robin to next available
    for _ in range(len(api_keys)):
        key = api_keys[current_index % len(api_keys)]
        current_index = (current_index + 1) % len(api_keys)
        
        if key in available:
            return key
    
    return available[0]  # Fallback
```

### Example Round-Robin Sequence

```
Request 1: Key 0 → Success
Request 2: Key 1 → Success
Request 3: Key 2 → Success
Request 4: Key 0 → Rate limited (1 failure)
Request 5: Key 1 → Success
Request 6: Key 2 → Success
Request 7: Key 0 → Rate limited (2 failures)
Request 8: Key 1 → Rate limited (1 failure)
Request 9: Key 2 → Success
Request 10: Key 0 → Rate limited (3 failures, DISABLED)
Request 11: Key 1 → Success (skip disabled key 0)
Request 12: Key 2 → Success
...
[10 minutes pass]
Request 25: Key 0 → Re-enabled (cooldown expired)
Request 26: Key 0 → Success
```

## Failure Tracking

### Per-Key Failure Tracking

Each API key tracks:
- `consecutive_failures`: Count of recent failures
- `disabled_since`: Timestamp when disabled
- `last_used`: Last successful use timestamp
- `call_count`: Total successful calls

### Failure States

```
State                   Description                         Behavior
═════════════════════   ════════════════════════════════   ════════════════════
0 failures              Fully operational                   Used in rotation
1-2 failures            Minor issues, still usable          Used in rotation
3 failures              Disabled temporarily                Skipped, in cooldown
After cooldown          Ready to retry                      Re-enabled automatically
```

### Cooldown Logic

```python
# When API key gets 3rd failure:
disabled_keys[key] = time.time()  # Mark time of disabling

# When request arrives:
for key in api_keys:
    if key in disabled_keys:
        time_elapsed = now() - disabled_keys[key]
        if time_elapsed >= cooldown_seconds:
            # Re-enable the key
            disabled_keys[key] = None
            consecutive_failures[key] = 0
```

## Configuration Examples

### Example 1: Simple Round-Robin (3 Keys)

```yaml
providers:
  openai:
    type: openai
    api_keys:
      - ${OPENAI_KEY_1}
      - ${OPENAI_KEY_2}
      - ${OPENAI_KEY_3}

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        max_retries: 3
```

Environment:
```bash
export OPENAI_KEY_1=sk-...
export OPENAI_KEY_2=sk-...
export OPENAI_KEY_3=sk-...
```

### Example 2: Multi-Provider with Fallback

```yaml
providers:
  primary:
    type: openai
    api_keys:
      - ${PRIMARY_KEY_1}
      - ${PRIMARY_KEY_2}
      - ${PRIMARY_KEY_3}

  backup:
    type: openai
    api_keys:
      - ${BACKUP_KEY_1}
      - ${BACKUP_KEY_2}

models:
  gpt-4:
    providers:
      primary:
        priority: 0
        model_id: gpt-4
        max_retries: 3
      backup:
        priority: 1
        model_id: gpt-4
        max_retries: 2
```

### Example 3: Cost-Optimized Setup

```yaml
providers:
  cheap:
    type: openai
    api_keys: [${CHEAP_KEY_1}, ${CHEAP_KEY_2}]

  standard:
    type: openai
    api_keys: [${STANDARD_KEY}]

  premium:
    type: openai
    api_keys: [${PREMIUM_KEY_1}, ${PREMIUM_KEY_2}, ${PREMIUM_KEY_3}]

models:
  gpt-3.5:
    providers:
      cheap:
        priority: 0        # Try cheap first
        max_retries: 2
      standard:
        priority: 1
        max_retries: 1

  gpt-4:
    providers:
      standard:
        priority: 0
        max_retries: 2
      premium:
        priority: 1        # Fallback to premium
        max_retries: 3
```

## Monitoring & Debugging

### Check Provider Status

```bash
# Get status for all providers
curl http://localhost:8000/v1/providers/status

# Get status for specific model
curl http://localhost:8000/v1/providers/status?model_id=gpt-4
```

### Check Provider Statistics

```bash
curl http://localhost:8000/v1/providers/stats
```

### Example Status Output

```json
{
  "gpt-4": {
    "providers": [
      {
        "name": "openai",
        "priority": 0,
        "enabled": true,
        "consecutive_failures": 0,
        "api_key_status": {
          "total_keys": 3,
          "available_keys": 3,
          "keys": [
            {"index": 0, "failures": 0, "enabled": true},
            {"index": 1, "failures": 1, "enabled": true},
            {"index": 2, "failures": 3, "enabled": false, "disabled_since": 1705766400}
          ]
        }
      }
    ]
  }
}
```

### Common Issues & Solutions

**Issue**: All API keys showing failures

**Solutions**:
1. Check API keys are valid and not expired
2. Verify rate limits on the account
3. Check network connectivity
4. Review OpenAI API status page

**Issue**: Key not being used in round-robin

**Reason**: Key is disabled (3+ failures)

**Solution**: Wait for cooldown period (default 10 minutes) or restart the server

**Issue**: Requests still failing despite multiple keys

**Reason**: All keys exhausted or all providers down

**Solution**: 
1. Check provider status endpoint
2. Verify configuration is correct
3. Check for network/firewall issues

## Advanced Topics

### Custom Retry Strategy

You can adjust retry behavior per model:

```yaml
models:
  gpt-4:
    providers:
      openai:
        max_retries: 5          # Aggressive retries
        cooldown_seconds: 300   # 5-minute cooldown
      backup:
        max_retries: 1          # Quick failover
        cooldown_seconds: 120   # 2-minute cooldown
  
  gpt-3.5:
    providers:
      openai:
        max_retries: 2          # Conservative retries
        cooldown_seconds: 900   # 15-minute cooldown
```

### Key Rotation Strategy

Rotate keys gradually:

```yaml
# Old keys in cooldown
providers:
  openai:
    api_keys:
      - ${NEW_KEY_1}     # New, will be used first
      - ${NEW_KEY_2}
      - ${OLD_KEY_1}     # Old, will get 3 failures and disable
      - ${OLD_KEY_2}     # Old, will get 3 failures and disable
```

After 3 failures + cooldown period, old keys are naturally phased out while new keys are being used.

## Performance Considerations

- **Round-robin overhead**: Negligible (O(1) lookup)
- **Failure tracking**: Minimal memory (dict per key)
- **Cooldown checking**: O(n) where n = number of keys (done at request time)
- **API key rotation**: No additional API calls

## Security Notes

⚠️ **Important Security Considerations**:

1. **Never commit API keys** to version control
2. **Use environment variables** for all keys
3. **Rotate keys quarterly** for security
4. **Monitor key usage** via status endpoint
5. **Use strong keys** with appropriate permissions
6. **Restrict key scope** to specific models/organizations if possible
7. **Audit key access** in OpenAI dashboard

## Migration Guide

### From Single Key to Multiple Keys

**Before** (single key):
```yaml
providers:
  openai:
    type: openai
    api_key: ${OPENAI_API_KEY}

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
```

**After** (multiple keys):
```yaml
providers:
  openai:
    type: openai
    api_keys:
      - ${OPENAI_API_KEY}         # Keep existing
      - ${OPENAI_API_KEY_2}       # Add new
      - ${OPENAI_API_KEY_3}       # Add new

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        max_retries: 3            # Optional: configure retries
```

**Backward Compatibility**: Single `api_key` still works, just gets wrapped in a single-key rotation.

## Troubleshooting

### Q: How do I check which key is being used?

**A**: Enable debug logging or check the request response. The proxy doesn't expose which key was used in the response (for security), but you can check provider status:

```bash
curl http://localhost:8000/v1/providers/status
```

### Q: What happens if all keys are disabled?

**A**: After the cooldown period (default 10 minutes), the oldest disabled key is automatically re-enabled. This ensures the system always has at least one available key.

### Q: Can I change retry settings without restarting?

**A**: Currently, retry settings are loaded from config on startup. You'll need to restart the server after changing `max_retries` or `cooldown_seconds` in config.yaml.

### Q: Why is my request getting a 503 even though I have multiple keys?

**Possible reasons**:
1. All keys have 3+ failures and are in cooldown
2. Network issue preventing any key from working
3. OpenAI API is down
4. Configuration error (no keys found)

Check status endpoint to debug:
```bash
curl http://localhost:8000/v1/providers/status | jq .
```

## Summary

| Feature | Benefit |
|---------|---------|
| Multiple API keys | Avoid rate limits |
| Round-robin rotation | Even load distribution |
| Per-key failure tracking | Smart failover |
| Automatic re-enabling | Self-healing system |
| Multi-level retries | High reliability |
| Status endpoints | Monitoring & debugging |

This implementation provides production-ready reliability with multiple API keys, intelligent failover, and comprehensive monitoring capabilities.