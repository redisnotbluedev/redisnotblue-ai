# OpenAI Proxy Server

A FastAPI server that acts as a proxy to multiple LLM providers with automatic failover support. Route requests through your preferred providers with fallback capabilities.

## Features

- **Multi-Provider Support**: Route requests to multiple LLM providers (OpenAI, and easily extensible to others)
- **Automatic Failover**: Seamlessly switch between providers if one fails
- **Failure Tracking**: Track consecutive failures per provider with automatic cooldown and retry logic
- **Priority-Based Routing**: Choose which provider gets tried first for each model
- **OpenAI-Compatible API**: Drop-in replacement for OpenAI API endpoints
- **Configuration-Driven**: Easy YAML-based configuration for providers and models

## Project Structure

```
redisnotblue-ai/
├── src/
│   ├── __init__.py
│   ├── app.py              # FastAPI application
│   ├── models.py           # Data models (Message, Model, ProviderInstance)
│   ├── registry.py         # Model and provider registry
│   └── providers/
│       ├── __init__.py
│       ├── base.py         # Abstract Provider base class
│       └── openai.py       # OpenAI provider implementation
├── config/
│   └── config.yaml         # Configuration file
├── requirements.txt        # Python dependencies
└── README.md
```

## Installation

1. Clone the repository:
```bash
git clone <repo-url>
cd redisnotblue-ai
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

Edit `config/config.yaml` to configure your providers and models:

```yaml
providers:
  openai_primary:
    type: openai
    api_key: sk-xxxxxx
    base_url: https://api.openai.com/v1

  openai_backup:
    type: openai
    api_key: sk-xxxxxx
    base_url: https://api.openai.com/v1

models:
  gpt-4:
    owned_by: openai
    providers:
      openai_primary:
        priority: 0           # Lower priority = tried first
        model_id: gpt-4       # Provider's model identifier
      openai_backup:
        priority: 1
        model_id: gpt-4
```

### Environment Variables

You can use environment variables in the config file with `${VAR_NAME}` syntax:

```yaml
providers:
  openai:
    type: openai
    api_key: ${OPENAI_API_KEY}
```

Or set `CONFIG_PATH` environment variable to use a different config file:
```bash
export CONFIG_PATH=/path/to/config.yaml
```

## Running the Server

```bash
# From the project root
cd src
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Or directly:
```bash
cd src
python app.py
```

The server will start on `http://localhost:8000`

## API Endpoints

### `POST /v1/chat/completions`

Create a chat completion request. Compatible with OpenAI's API.

**Request:**
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 100
}
```

**Response:**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hi there! How can I help?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

**Parameters:**
- `model` (required): Model ID
- `messages` (required): Array of message objects with `role` and `content`
- `temperature` (optional): 0-2, default 1.0
- `max_tokens` (optional): Max tokens in response
- `max_completion_tokens` (optional): Alternative name for max_tokens
- `top_p` (optional): 0-1, default 1.0
- `stop` (optional): String or array of stop sequences

### `GET /v1/models`

List all available models.

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4",
      "object": "model",
      "created": 1234567890,
      "owned_by": "openai"
    },
    {
      "id": "gpt-3.5-turbo",
      "object": "model",
      "created": 1234567890,
      "owned_by": "openai"
    }
  ]
}
```

### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "ok"
}
```

## Usage Examples

### Using with Python OpenAI client

```python
import openai

# Point to your proxy server
openai.api_base = "http://localhost:8000/v1"
openai.api_key = "any-value"  # Required but not validated by proxy

# Use normally
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)
print(response.choices[0].message.content)
```

### Using with requests

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello!"}
        ]
    }
)
print(response.json())
```

### Using with curl

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Failover and Failure Handling

The proxy automatically handles provider failures:

1. **Failure Tracking**: Each provider instance tracks consecutive failures
2. **Automatic Disabling**: After 3 consecutive failures, a provider is disabled
3. **Cooldown Period**: Disabled providers enter a 10-minute cooldown
4. **Automatic Retry**: After cooldown expires, the provider is re-enabled
5. **Fallback**: Requests automatically route to the next available provider

When a provider is disabled or fails:
- The next provider in the priority list is tried
- If all providers fail, a 503 error is returned
- The error response includes details about the last failure

## Extending with New Providers

To add a new provider (e.g., Anthropic, Cohere):

1. Create a new file in `src/providers/` (e.g., `anthropic.py`)
2. Implement the `Provider` base class:

```python
from providers.base import Provider

class AnthropicProvider(Provider):
    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.api_key = config.get("api_key")
    
    def translate_request(self, messages: list[dict], model_id: str, **kwargs) -> dict:
        # Convert OpenAI format to Anthropic format
        return {...}
    
    def make_request(self, request_data: dict) -> dict:
        # Make the actual API call
        return {...}
    
    def translate_response(self, response_data: dict) -> dict:
        # Convert Anthropic response to OpenAI format
        return {...}
```

3. Register in `src/registry.py`:

```python
from providers.anthropic import AnthropicProvider

PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}
```

4. Use in config:

```yaml
providers:
  anthropic:
    type: anthropic
    api_key: ${ANTHROPIC_API_KEY}

models:
  claude-opus:
    providers:
      anthropic:
        priority: 0
        model_id: claude-opus-4-1
```

## Data Models

### Message
- `role`: str (e.g., "user", "assistant", "system")
- `content`: str (message text)

### ProviderInstance
Represents a provider for a specific model with failure tracking.

**Attributes:**
- `provider`: Provider instance
- `priority`: int (lower = tried first)
- `model_id`: str (provider's model name)
- `enabled`: bool (currently available?)
- `consecutive_failures`: int (failure count)
- `last_failure`: float | None (Unix timestamp)

**Methods:**
- `mark_failure()`: Increment failures and disable if >= 3
- `mark_success()`: Reset failures
- `should_retry(cooldown_seconds=600)`: Check if ready to retry

### Model
Represents a unified model with multiple providers.

**Attributes:**
- `id`: str (unified model name)
- `provider_instances`: list[ProviderInstance]
- `created`: int (Unix timestamp)
- `owned_by`: str (provider name)

**Methods:**
- `get_available_providers()`: Get enabled providers sorted by priority
- `to_dict()`: Return OpenAI-format model object

## Error Handling

The proxy returns appropriate HTTP status codes:

- **200 OK**: Successful completion
- **404 Not Found**: Model not found
- **500 Internal Server Error**: Registry not initialized
- **503 Service Unavailable**: All providers failed

Error responses include details:
```json
{
  "error": {
    "message": "Model not found: gpt-5",
    "type": "error"
  }
}
```

## Performance Considerations

- **Timeouts**: Provider requests timeout after 60 seconds
- **Cooldown**: Failed providers have 10-minute cooldown before retry
- **Priority**: Configure providers by priority to optimize cost/performance
- **Model Mapping**: Map unified model names to provider-specific names

## Troubleshooting

### "Registry not initialized"
- Ensure `config/config.yaml` exists
- Check `CONFIG_PATH` environment variable
- Verify startup completed without errors

### "Model not found"
- Check model ID in request matches `config.yaml`
- Run `GET /v1/models` to see available models

### "All providers failed"
- Check API keys in config
- Verify provider base URLs
- Check network connectivity
- Review provider API documentation

### Provider keeps failing
- Check API key validity
- Verify rate limits aren't exceeded
- Check provider-specific model names in `model_id` field
- Review last failure message in logs

## Security Considerations

⚠️ **This is a proxy server - handle API keys carefully:**

1. **Never commit API keys** to version control
2. **Use environment variables** for sensitive config
3. **Restrict network access** to trusted clients
4. **Use HTTPS** in production
5. **Validate requests** if exposed to untrusted networks
6. **Rotate API keys** regularly

## License

MIT