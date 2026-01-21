# How It Works: OpenAI-Compatible Proxy with Rate Limiting

This document explains the internals of the proxy server, including rate limiting, provider management, and request routing.

## Architecture Overview

```
┌─────────────────┐
│  Client Request │
│  /chat/complete │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│   FastAPI Request Handler       │
│  - Validate request             │
│  - Find model in registry       │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│   Get Available Providers       │
│  - Filter enabled providers     │
│  - Sort by health score         │
│  - Apply priority ordering      │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│   For Each Provider (with retry)│
│  - Get next available API key   │
│  - Check rate limits            │
│  - Make request to provider     │
│  - Record metrics               │
│  - Return response on success   │
└────────┬────────────────────────┘
         │
    On Failure:
         ▼
┌─────────────────────────────────┐
│   Retry Logic                   │
│  - Exponential backoff          │
│  - Mark key as failed           │
│  - Try next provider/key        │
│  - Circuit breaker check        │
└─────────────────────────────────┘
```

## Core Components

### 1. Model Registry (`registry.py`)

The registry manages the mapping of logical models to provider instances.

**Responsibilities:**
- Load configuration from YAML file
- Parse provider and model definitions
- Instantiate provider objects
- Set up API key rotation for each model/provider
- Configure rate limits from YAML

**Flow:**
```
Load config.yaml
  ↓
Parse providers section
  ↓
Create Provider instances (OpenAI, Custom, etc.)
  ↓
Parse models section
  ↓
For each model:
  - For each provider:
    - Create ProviderInstance
    - Set up ApiKeyRotation
    - Configure rate limits
    - Store in Model.provider_instances
  ↓
Return configured models
```

### 2. Rate Limiting System (`models.py::RateLimitTracker`)

Each API key has a `RateLimitTracker` that enforces multiple time-period limits simultaneously.

**Key Concepts:**

- **Time Windows**: Limits can be per-minute, per-hour, per-day, or per-month
- **Multiple Limits**: All configured limits must be satisfied (AND logic)
- **Sliding Windows**: Uses timestamps of actual requests, not clock boundaries
- **Efficient Storage**: Keeps only last 1000 requests to save memory

**How It Works:**

```python
# Configuration example
rate_limits = {
    "requests_per_minute": 3500,
    "tokens_per_day": 90000
}

# When a request is made:
tracker.add_request(tokens=150)

# Tracker stores: [current_timestamp]
# Tracker stores: [(current_timestamp, 150)]

# When checking if rate limited:
for limit_key, limit_value in rate_limits.items():
    window_seconds = get_time_window(period)  # "minute" → 60
    current_usage = count_items_in_window(requests, window_seconds)
    
    if current_usage >= limit_value:
        return True  # Rate limited!
```

**Example Timeline:**

```
Time: 12:00:00 - Request #1 (100 tokens) - OK
Time: 12:00:05 - Request #2 (100 tokens) - OK
Time: 12:00:10 - Request #3 (100 tokens) - OK
...
Time: 12:01:00 - Request #100 (100 tokens) - RATE LIMITED!
                 (3500 requests already in last 60 seconds)

Time: 12:01:05 - Check again
                 Oldest request from 12:00:05 (55s ago) still in window
                 Current usage: 3499 - OK to proceed!
                 Proceed with Request #101
```

**Multiple Limits Example:**

```
Configuration:
  requests_per_minute: 100
  tokens_per_hour: 50000

Usage:
  12:00:00 - 90 requests, 20000 tokens in past minute - OK
  12:00:15 - 100 requests, 25000 tokens in past minute - RATE LIMITED!
             (requests_per_minute limit hit)
  
  12:01:00 - 50 requests, 30000 tokens in past minute - OK
             (past minute reset)
             BUT: 45000 tokens in past hour - OK
  
  12:01:30 - 60 requests, 35000 tokens in past minute - OK
             52000 tokens in past hour - RATE LIMITED!
             (tokens_per_hour limit hit, even though minute is OK)
```

### 3. API Key Rotation (`models.py::ApiKeyRotation`)

When multiple API keys are configured, the proxy uses round-robin rotation with intelligence.

**Key Features:**

- **Round-Robin**: Cycles through keys fairly
- **Failure Tracking**: Disables keys that fail
- **Rate Limit Awareness**: Skips keys that are rate-limited
- **Cooldown Recovery**: Re-enables failed keys after 10 minutes
- **Fallback**: If all keys disabled, forces retry of oldest failed key

**Algorithm:**

```
get_next_key():
  1. Check if any disabled keys can be re-enabled (10min passed?)
  2. Build list of available keys:
     - Not disabled (or cooldown expired)
     - Not rate-limited
  3. If no available keys:
     - Force re-enable oldest failed key
  4. Round-robin through keys, return first available
  5. If no available, return any key (will handle error gracefully)
```

**Example:**

```
Keys: [key1, key2, key3]
Disabled: {key1: 12:00:00, key2: None, key3: None}
RateLimited: {key1: False, key2: True, key3: False}

get_next_key() calls:
  Call 1: key2 unavailable (rate limited), key3 available → return key3
  Call 2: key3 used, round-robin to key1, disabled → try key2, disabled
          → try key3 again → return key3
  Call 3: key1 cooldown elapsed → re-enable → return key1

Result: Requests distributed to key3, key3, key1
        (key2 skipped while rate-limited)
```

### 4. Provider Selection and Health Scoring

Providers are ranked by health score, which combines multiple factors.

**Health Score Calculation:**

```
base_score = 100.0

# Circuit breaker state
if circuit_open:
    return 0.0
if circuit_half_open:
    base_score -= 50

# Consecutive failures
base_score -= min(failures * 10, 40)

# Response speed
avg_time = average_response_time_ms
speed_penalty = min(avg_time * 10, 30)
base_score -= speed_penalty

final_score = max(0, min(base_score, 100))
```

**Example:**

```
Provider A:
  - Circuit: closed (0 penalty)
  - Failures: 1 (10 penalty)
  - Avg response time: 100ms (10 penalty)
  - Score: 100 - 0 - 10 - 10 = 80

Provider B:
  - Circuit: half-open (50 penalty)
  - Failures: 0 (0 penalty)
  - Avg response time: 50ms (5 penalty)
  - Score: 100 - 50 - 0 - 5 = 45

Provider A is selected first (80 > 45)
```

### 5. Circuit Breaker Pattern

Prevents cascading failures by tracking provider health.

**States:**

- **Closed**: Normal operation, requests pass through
- **Open**: Provider is failing, reject requests immediately
- **Half-Open**: Testing if provider recovered

**Transitions:**

```
CLOSED:
  ✓ Success → failure_count reset
  ✗ Failure → failure_count++
    (if failure_count >= threshold, go to OPEN)

OPEN:
  (timeout elapsed?) → go to HALF_OPEN

HALF_OPEN:
  ✓ Success → success_count++
    (if success_count >= threshold, go to CLOSED)
  ✗ Failure → go back to OPEN
```

**Default Configuration:**
- failure_threshold: 5 consecutive failures to trip open
- success_threshold: 2 consecutive successes to close
- timeout_seconds: 60 seconds before retry

### 6. Exponential Backoff

When retrying failed requests, delays increase exponentially.

**Formula:**

```
delay = min(base_delay * (multiplier ^ attempt), max_delay)
```

**Example (base_delay=1, multiplier=2, max_delay=300):**

```
Attempt 0: 1 second delay (1 * 2^0 = 1)
Attempt 1: 2 second delay (1 * 2^1 = 2)
Attempt 2: 4 second delay (1 * 2^2 = 4)
Attempt 3: 8 second delay (1 * 2^3 = 8)
Attempt 4: 16 second delay (1 * 2^4 = 16)
Attempt 5: 32 second delay (1 * 2^5 = 32)
... continues up to 300 second max
```

### 7. Request Flow with Retries

```
Request comes in for "gpt-4"
│
├─ Get Model("gpt-4") from registry
├─ Get available providers (sorted by health score)
│
├─ For each provider in priority order:
│  │
│  ├─ Reset retry counter (retry_count = 0)
│  │
│  └─ While retry_count < max_retries:
│     │
│     ├─ Check circuit breaker (can_attempt?)
│     │  └─ If open → break to next provider
│     │
│     ├─ Get next available API key
│     │  └─ If rate-limited → skip to next key
│     │
│     ├─ If retrying → apply exponential backoff delay
│     │
│     ├─ Send request to provider
│     │  ├─ Measure response time
│     │  ├─ Extract token counts
│     │  │
│     │  ├─ Success:
│     │  │  ├─ Record metrics (speed, tokens)
│     │  │  ├─ Mark key as successful
│     │  │  ├─ Mark provider as successful
│     │  │  └─ Return response to client
│     │  │
│     │  └─ Failure:
│     │     ├─ Mark API key as failed
│     │     ├─ Mark provider as failed
│     │     ├─ Increment retry counter
│     │     ├─ Increment backoff attempt
│     │     └─ Continue to next retry
│     │
│
├─ All providers failed or rate-limited
└─ Return HTTP 503 with error message
```

## Configuration Flow

When the proxy starts:

```
1. Initialize ModelRegistry()

2. load_from_config("config/config.yaml")
   
   Parse YAML:
   ├─ providers:
   │  ├─ navyai:
   │  │  ├─ Create OpenAIProvider("navyai", config_dict)
   │  │  └─ register_provider("navyai", provider_instance)
   │  │
   │  └─ [other providers...]
   │
   └─ models:
      ├─ gpt-4:
      │  └─ providers:
      │     ├─ navyai:
      │     │  ├─ Get provider from registry
      │     │  ├─ Create ApiKeyRotation([keys...])
      │     │  ├─ Call set_rate_limits(rate_limits_dict)
      │     │  │  └─ For each key:
      │     │  │     └─ rate_limiter[key].limits = rate_limits_dict
      │     │  │
      │     │  ├─ Create ProviderInstance(
      │     │  │    provider=provider,
      │     │  │    model_id="gpt-4",
      │     │  │    api_key_rotation=rotation
      │     │  │  )
      │     │  └─ Add to provider_instances list
      │     │
      │     └─ [other providers...]
      │
      ├─ Create Model("gpt-4", provider_instances=[...])
      └─ register_model(model)
```

## Rate Limiting in Action

**Scenario:** 3 API keys, each with limits of 3500 req/min, 90k tokens/day

```
Time 12:00:00:
  Request 1 arrives
  ├─ Get model "gpt-4"
  ├─ Get next key: key1
  ├─ Check rate limit: key1 has [0 requests, 0 tokens] → OK
  ├─ Send request, get response (150 tokens)
  ├─ Record: key1 now has [1 request, 150 tokens]
  └─ Return response

Time 12:00:01-12:00:59:
  Requests 2-3500 arrive
  ├─ Round-robin distribution: key1, key2, key3, key1, key2, key3, ...
  ├─ Each key receives ~1167 requests
  ├─ Each key consumes ~175,000 tokens
  └─ All keys still within limits

Time 12:01:00 (60 seconds later):
  Request 3501 arrives
  ├─ Get next key: key1 (round-robin order)
  ├─ Check rate limit:
  │  ├─ requests_per_minute: 1167 < 3500 ✓
  │  └─ tokens_per_day: 175,000 < 90,000,000 ✓
  ├─ Key1 is OK, send request
  └─ Continue normally

Time 13:00:00 (1 hour later):
  Request ~500,000 arrives
  ├─ Get next key: key1
  ├─ Check rate limit:
  │  ├─ requests_per_minute: 1167 < 3500 ✓
  │  └─ tokens_per_day: 0 (just started new day) < 90,000,000 ✓
  ├─ Key1 is OK
  └─ Continue normally

Time 24:00:00 (end of day):
  All keys have consumed exactly 90,000,000 tokens total
  Next day at 00:00:01:
  ├─ Oldest token timestamp is > 24 hours old
  ├─ All tokens "age out" of the daily window
  ├─ Counter resets to 0
  └─ Requests can proceed again
```

## Metrics Collection

The proxy tracks several metrics for each provider and key:

**Per-Provider:**
- Consecutive failures (incremented on error, reset on success)
- Circuit breaker state (closed/open/half-open)
- Health score (0-100)
- Average response time (rolling average of last 100 requests)
- P95 response time (95th percentile)

**Per-API-Key:**
- Consecutive failures
- Disabled status and duration
- Rate limit status per configured limit
- Current usage vs limits

**Exposed via `/v1/providers/stats`:**

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
          "total_keys": 3,
          "available_keys": 3,
          "keys": [
            {
              "index": 0,
              "failures": 0,
              "enabled": true,
              "rate_limited": false,
              "usage": {
                "requests_per_minute": {"used": 125, "limit": 3500},
                "tokens_per_day": {"used": 50000, "limit": 90000000}
              }
            }
          ]
        }
      }
    ]
  }
}
```

## Request Lifecycle Example

```
Client sends:
POST /v1/chat/completions
{
  "model": "gpt-4",
  "messages": [{"role": "user", "content": "Hello"}]
}

Step 1: Validate
├─ Check model "gpt-4" exists in registry
├─ Validate request format
└─ Success → continue

Step 2: Get Providers
├─ Get Model("gpt-4").get_available_providers()
├─ Filter to enabled or retryable providers
├─ Sort by health_score (descending)
├─ Result: [ProviderInstance(navyai, priority=0, health=90),
            ProviderInstance(a4f, priority=1, health=75)]
└─ Continue

Step 3: Try First Provider (navyai)
├─ Reset retry counter to 0
├─ Check circuit breaker: closed ✓
├─ Get next API key
│  ├─ Key rotation: round-robin
│  ├─ Check key1: not disabled, not rate-limited ✓
│  └─ Return key1
├─ Make request
│  ├─ POST https://api.navy/v1/chat/completions
│  ├─ Headers: Authorization: Bearer sk-navy-...
│  ├─ Timeout: 60 seconds
│  ├─ Response: 200 OK, {"choices": [...], "usage": {...}}
│  └─ Duration: 0.45 seconds
├─ Extract metrics
│  ├─ Input tokens: 10
│  ├─ Output tokens: 25
│  ├─ Total: 35 tokens
│  └─ Response time: 0.45s
├─ Record metrics
│  ├─ speed_tracker.record_response(0.45)
│  ├─ api_key_rotation.record_usage(key1, 35)
│  └─ Mark key1 as successful
├─ Mark provider successful
│  ├─ circuit_breaker.record_success()
│  ├─ consecutive_failures = 0
│  └─ backoff.reset()
├─ Format response in OpenAI format
│  ├─ Add unique ID: "chatcmpl-abc123..."
│  ├─ Add timestamp: current Unix time
│  └─ Ensure all required fields present
└─ Return 200 OK with response

Response sent to client:
{
  "id": "chatcmpl-abc123...",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "Hello!"},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 25,
    "total_tokens": 35
  }
}
```

## What Happens on Failure

```
Same request, but navyai provider times out:

Step 3: Try First Provider (navyai) - FAILURE
├─ Post request to provider
├─ Timeout after 60 seconds
├─ Exception caught: "OpenAI API timeout after 60s"
├─ Record failure
│  ├─ api_key_rotation.mark_failure(key1)
│  │  └─ key1 disabled until 12:10:00
│  ├─ consecutive_failures++
│  ├─ circuit_breaker.record_failure()
│  │  └─ failure_count: 0 → 1 (not yet open)
│  └─ backoff.record_attempt()
│     └─ Prepare 1 second delay for next retry
├─ Check if should retry
│  ├─ circuit_breaker.can_attempt? Yes (not yet open)
│  ├─ retry_count < max_retries? 0 < 3 ✓
│  └─ Yes, retry
├─ Apply exponential backoff: sleep(1 second)
├─ Get next API key
│  ├─ Key1 is disabled, skip
│  ├─ Key2: not disabled, not rate-limited ✓
│  └─ Return key2
├─ Retry request with key2
│  ├─ POST https://api.navy/v1/chat/completions
│  ├─ Success! Get response
│  ├─ Record metrics with key2
│  ├─ Mark key2 as successful
│  ├─ Mark provider successful
│  └─ Return response

OR if key2 also fails:
├─ Mark key2 as failed
├─ retry_count: 1 → 2
├─ Get next API key
│  ├─ Key3: available
│  └─ Return key3
├─ Apply backoff: sleep(2 seconds)
├─ Retry with key3...

OR if all keys exhausted:
├─ retry_count: 0 → 1 → 2 → 3
├─ Check should_retry_request: 3 < 3? No
├─ Break to next provider

Step 4: Try Second Provider (a4f)
├─ Same process as above
├─ If succeeds: return response
├─ If fails: continue to next provider

Step 5: All Providers Failed
├─ Return HTTP 503 Service Unavailable
└─ Message: "All providers failed. Last error: ..."
```

## Performance Characteristics

**Time Complexity:**
- Getting next provider: O(n) where n = number of providers (typically small)
- Checking rate limits: O(m) where m = number of configured limits per key (typically 1-4)
- Rate limit tracking: O(1) amortized (sliding window uses fixed-size buffer)

**Space Complexity:**
- Per API key: O(r + t) where r = requests in window, t = token events in window
  - Default: ~1000 tracked items per key (configurable)
  - Per item: ~8 bytes timestamp = ~8KB per key

**Latency Impact:**
- Rate limit check: <1ms per key
- Provider selection: <1ms for typical 2-3 providers
- Backoff delay: 1-300 seconds (configurable, intentional)

## Customization

**Adding a New Provider Type:**

1. Create `src/providers/custom.py`:
```python
from .base import Provider

class CustomProvider(Provider):
    def translate_request(self, messages, model_id, **kwargs) -> dict:
        # Convert to provider's format
        pass
    
    def make_request(self, request_data, api_key) -> dict:
        # Call provider's API
        pass
    
    def translate_response(self, response_data) -> dict:
        # Convert to OpenAI format
        pass
```

2. Register in `src/registry.py`:
```python
from providers.custom import CustomProvider

PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
    "custom": CustomProvider,
}
```

3. Use in config.yaml:
```yaml
providers:
  my_custom:
    type: custom
    # ... custom configuration
```

That's it! The rest of the system handles routing, rate limiting, and error recovery automatically.
