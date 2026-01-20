# Architecture Documentation

## Overview

The LLM Provider Proxy is a FastAPI-based server that acts as an intelligent router for Large Language Model (LLM) API requests. It provides:

- **Multi-provider support**: Route requests to multiple LLM providers
- **Automatic failover**: Seamlessly switch between providers on failure
- **OpenAI-compatible API**: Drop-in replacement for OpenAI endpoints
- **Provider abstraction**: Easy to add new providers

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client                               │
│              (Python SDK, curl, HTTP client)                │
└────────────────────────┬────────────────────────────────────┘
                         │
                    HTTP Request
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Server                           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Endpoints:                                            │ │
│  │  - POST /v1/chat/completions                          │ │
│  │  - GET /v1/models                                     │ │
│  │  - GET /health                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                         │                                    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              ModelRegistry                             │ │
│  │                                                         │ │
│  │  - Load providers from YAML config                    │ │
│  │  - Load model definitions                             │ │
│  │  - Route requests to correct model                    │ │
│  └────────────────────────────────────────────────────────┘ │
│                         │                                    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Model + ProviderInstances                    │ │
│  │                                                         │ │
│  │  - Track provider availability                        │ │
│  │  - Sort by priority                                   │ │
│  │  - Filter out disabled providers                      │ │
│  └────────────────────────────────────────────────────────┘ │
│                         │                                    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │        Provider Abstraction Layer                      │ │
│  │                                                         │ │
│  │  - translate_request()                                │ │
│  │  - make_request()                                     │ │
│  │  - translate_response()                               │ │
│  │  - Failure tracking & retry logic                     │ │
│  └────────────────────────────────────────────────────────┘ │
│                         │                                    │
│      ┌──────────────────┼──────────────────┐               │
│      ▼                  ▼                  ▼               │
│  ┌────────┐         ┌────────┐       ┌──────────┐        │
│  │ OpenAI │         │Anthropic│     │  Cohere  │        │
│  │Provider│         │Provider │     │ Provider │        │
│  └────────┘         └────────┘       └──────────┘        │
│                                                            │
└─────────────────────────────────────────────────────────────┘
                         │
                    HTTP Request
                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
   ┌────────┐        ┌────────┐      ┌──────────┐
   │ OpenAI │        │Anthropic       │  Cohere  │
   │  API   │        │  API   │       │   API    │
   └────────┘        └────────┘      └──────────┘
```

## Component Structure

### 1. Entry Point: `app.py`

FastAPI application that handles HTTP requests.

**Key Responsibilities:**
- Define API endpoints (`/v1/chat/completions`, `/v1/models`, `/health`)
- Parse and validate incoming requests using Pydantic models
- Coordinate with ModelRegistry to route requests
- Handle errors and return appropriate HTTP status codes
- Track provider failures and retry logic

**Request Flow:**
```
Request → Pydantic Validation → ModelRegistry → Provider → Response
```

### 2. Data Models: `models.py`

Core data structures using Python dataclasses.

#### Message
Represents a single message in a conversation.
```python
@dataclass
class Message:
    role: str          # "user", "assistant", "system"
    content: str       # Message text
```

#### ProviderInstance
Wraps a provider for a specific model with failure tracking.

**Key Attributes:**
- `provider`: Reference to the Provider instance
- `priority`: Sort order (lower = tried first)
- `model_id`: Provider's model name
- `enabled`: Currently available?
- `consecutive_failures`: Failure counter
- `last_failure`: Unix timestamp of last failure

**Key Methods:**
- `mark_failure()`: Increment failures, disable after 3
- `mark_success()`: Reset failures to 0
- `should_retry(cooldown_seconds=600)`: Check if cooldown expired

**Failure Logic:**
```
Mark Failure
    ↓
consecutive_failures++
last_failure = now()
    ↓
Is consecutive_failures >= 3?
    ├─ YES → enabled = False (Provider disabled)
    └─ NO  → Keep enabled
    
Later, when request arrives:
    ↓
Check should_retry()
    ├─ enough time passed? → Re-enable provider
    └─ not enough time? → Keep disabled
```

#### Model
Represents a unified model with multiple provider options.

**Key Attributes:**
- `id`: Unified model name (e.g., "gpt-4")
- `provider_instances`: List of ProviderInstance objects
- `created`: Unix timestamp (metadata)
- `owned_by`: Provider name (metadata)

**Key Methods:**
- `get_available_providers()`: Return sorted, enabled providers
- `to_dict()`: Return OpenAI-format dict

### 3. Provider Abstraction: `providers/base.py`

Abstract base class defining the provider interface.

**Key Methods:**
- `translate_request(messages, model_id, **kwargs) → dict`
  - Convert OpenAI format to provider-specific format
  - Handle temperature, max_tokens, top_p, stop parameters

- `make_request(request_data) → dict`
  - Make actual HTTP request to provider API
  - Handle authentication and error responses
  - Timeout after 60 seconds

- `translate_response(response_data) → dict`
  - Convert provider response to OpenAI format
  - Ensure consistent response structure

- `chat_completion(messages, model_id, **kwargs) → dict`
  - Orchestrate the three methods above
  - Main entry point for providers

### 4. OpenAI Provider: `providers/openai.py`

Concrete implementation of the Provider for OpenAI API.

**Configuration:**
```yaml
providers:
  openai:
    type: openai
    api_key: sk-...
    base_url: https://api.openai.com/v1  # Optional
```

**Request Translation:**
- Already in OpenAI format, mostly pass-through
- Handles both `max_tokens` and `max_completion_tokens`
- Passes optional parameters (temperature, top_p, stop)

**Response Translation:**
- Already in OpenAI format, return as-is

### 5. Registry: `registry.py`

Central registry managing providers and models.

**Key Responsibilities:**
- Load configuration from YAML file
- Instantiate provider classes
- Create model definitions with provider instances
- Route requests to correct model

**Configuration Loading Flow:**
```
Load YAML
    ↓
Parse providers section
    ├─ For each provider:
    │  ├─ Get type (e.g., "openai")
    │  ├─ Look up class in PROVIDER_CLASSES
    │  ├─ Instantiate with config
    │  └─ Store in registry.providers
    │
Parse models section
    ├─ For each model:
    │  ├─ Get provider references
    │  ├─ Create ProviderInstance for each
    │  ├─ Sort by priority
    │  ├─ Create Model object
    │  └─ Store in registry.models
```

**YAML Configuration Structure:**
```yaml
providers:
  provider_name:
    type: provider_type
    # provider-specific config
    
models:
  model_id:
    owned_by: owner_name
    providers:
      provider_name:
        priority: 0
        model_id: provider_specific_model_id
```

## Request Handling Flow

### Chat Completion Request

```
1. Client sends POST /v1/chat/completions
   {
     "model": "gpt-4",
     "messages": [...],
     "temperature": 0.7,
     ...
   }

2. FastAPI validates with ChatCompletionRequest model

3. app.py queries registry for model
   model = registry.get_model("gpt-4")

4. Get available providers (sorted by priority, enabled first)
   providers = model.get_available_providers()

5. For each provider in priority order:
   a. Try: provider.chat_completion(...)
   b. On success:
      - Call provider_instance.mark_success()
      - Return response
   c. On failure:
      - Call provider_instance.mark_failure()
      - Continue to next provider

6. If all fail:
   - Return 503 Service Unavailable
   - Include last error message

7. Response is already in OpenAI format
```

### Model Listing Request

```
1. Client sends GET /v1/models

2. app.py queries registry for all models
   models = registry.list_models()

3. Convert each model to dict
   data = [model.to_dict() for model in models]

4. Return OpenAI-format response
   {
     "object": "list",
     "data": [...]
   }
```

## Failure Recovery Mechanism

### Consecutive Failures

```
Provider fails
    ↓
consecutive_failures++
    ├─ 1st failure: Provider remains enabled
    ├─ 2nd failure: Provider remains enabled
    ├─ 3rd failure: Provider disabled, last_failure set
    └─ 4th+ failure: Already disabled

Cooldown Period (default 600 seconds / 10 minutes):
    
Next request for model arrives:
    ↓
get_available_providers() checks each:
    ├─ enabled=true → include
    └─ enabled=false → check should_retry()
                         ├─ cooldown expired? → re-enable
                         └─ cooldown active? → skip

When provider re-enabled:
    ├─ consecutive_failures reset to 0
    ├─ last_failure cleared
    └─ Provider tried again on next request
```

### Automatic Retry Logic

The system tracks two things per provider:
1. **consecutive_failures**: How many times in a row it failed
2. **last_failure**: When the last failure occurred

This allows:
- **Quick failure detection**: Disable after 3 failures
- **Automatic recovery**: Re-enable after cooldown
- **Graceful degradation**: Don't overwhelm a struggling provider
- **Transparent failover**: Clients don't need to handle retries

## Error Handling

### HTTP Status Codes

| Status | Meaning | Example |
|--------|---------|---------|
| 200 | Success | Chat completion returned |
| 400 | Bad Request | Invalid model name format |
| 404 | Not Found | Model not in registry |
| 500 | Internal Error | Registry initialization failed |
| 503 | Unavailable | All providers failed |

### Error Response Format

```json
{
  "error": {
    "message": "Error description",
    "type": "error"
  }
}
```

## Configuration Examples

### Minimal Setup (Single Provider)

```yaml
providers:
  openai:
    type: openai
    api_key: sk-...

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
```

### Redundancy Setup (Failover)

```yaml
providers:
  primary:
    type: openai
    api_key: sk-primary-...
  backup:
    type: openai
    api_key: sk-backup-...

models:
  gpt-4:
    providers:
      primary:
        priority: 0
        model_id: gpt-4
      backup:
        priority: 1
        model_id: gpt-4
```

### Multi-Provider Setup

```yaml
providers:
  openai:
    type: openai
    api_key: sk-...
  anthropic:
    type: anthropic
    api_key: claude-...

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
      
  claude-3:
    providers:
      anthropic:
        priority: 0
        model_id: claude-3-opus
```

## Extending with New Providers

### Step 1: Create Provider Class

Create `src/providers/anthropic.py`:

```python
from .base import Provider

class AnthropicProvider(Provider):
    def translate_request(self, messages, model_id, **kwargs):
        # Convert OpenAI → Anthropic format
        pass
    
    def make_request(self, request_data):
        # Make API call to Anthropic
        pass
    
    def translate_response(self, response_data):
        # Convert Anthropic → OpenAI format
        pass
```

### Step 2: Register Provider

In `src/registry.py`:

```python
from providers.anthropic import AnthropicProvider

PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,  # Add this
}
```

### Step 3: Use in Config

```yaml
providers:
  anthropic:
    type: anthropic
    api_key: ${ANTHROPIC_API_KEY}

models:
  claude-3:
    providers:
      anthropic:
        priority: 0
        model_id: claude-3-opus
```

## Performance Considerations

### Timeout Handling
- Provider requests timeout after 60 seconds
- Slow providers don't block other requests
- Failed requests immediately trigger retry logic

### Priority Optimization
- Configure providers by cost/speed/reliability
- Cheap providers at high priority
- Premium providers as backup
- Example: use cheaper gpt-3.5-turbo first, fallback to gpt-4

### Model Mapping
- Unified model names (e.g., "gpt-4") can map to different provider model IDs
- Useful when models have different names across providers
- Example: "gpt-4" → "gpt-4" on OpenAI, "claude-3-opus" on Anthropic

### Cooldown Period
- Default 600 seconds (10 minutes)
- Configurable in ProviderInstance.should_retry()
- Prevents overwhelming a provider that's temporarily down

## Security Considerations

⚠️ **This is a proxy for API keys - handle carefully:**

1. **Never commit API keys**: Use environment variables
2. **Environment variables**: Store in `.env` or CI/CD secrets
3. **Network security**: Restrict access to trusted clients
4. **HTTPS in production**: Use reverse proxy (nginx, Apache)
5. **Request validation**: Validate incoming requests
6. **Rate limiting**: Implement to prevent abuse (not in base code)
7. **Logging**: Don't log API keys

## Deployment Architecture

### Development

```
Your Machine
    ↓
uvicorn dev server (port 8000)
    ↓
config/config.yaml (local file)
    ↓
LLM Provider APIs
```

### Production

```
Load Balancer (SSL/TLS)
    ↓
Reverse Proxy (nginx)
    ↓
Gunicorn/Uvicorn Workers
    ↓
Shared config (S3, shared volume)
    ↓
LLM Provider APIs
```

### Kubernetes Example

```
Deployment
├─ Service (LoadBalancer)
├─ ConfigMap (config.yaml)
├─ Secret (API keys)
└─ Replica Set
   └─ Pod (FastAPI server)
```

## Testing Strategy

### Unit Tests
- Test data model validation
- Test provider instance failure tracking
- Test model provider sorting

### Integration Tests
- Test provider implementation
- Test registry loading
- Test request/response translation

### End-to-End Tests
- Test complete request flow
- Test failover behavior
- Test error handling

### Mock Testing
- Use mock providers for unit tests
- Mock API responses for integration tests
- Don't need real API keys for testing

## Future Enhancements

1. **Rate limiting**: Track and limit requests per client
2. **Caching**: Cache common responses
3. **Analytics**: Track usage, cost, latency per provider
4. **Circuit breaker**: More sophisticated failure handling
5. **Load balancing**: Distribute requests by cost/speed
6. **Request logging**: Log all requests for audit trail
7. **Admin API**: Manage providers and models at runtime
8. **Streaming**: Support SSE/streaming responses
9. **Async**: Better async/await patterns
10. **Metrics**: Prometheus metrics for monitoring