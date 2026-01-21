# Creating Custom Providers

This guide walks you through implementing a new provider type for the proxy.

## Overview

A provider is a class that handles communication with an external API. The proxy currently supports OpenAI-compatible APIs out of the box, but you can add support for any API by implementing the `Provider` interface.

## The Provider Interface

All providers inherit from `Provider` (in `src/providers/base.py`) and must implement three methods:

### 1. `translate_request(messages, model_id, **kwargs) -> TransformedRequest`

Converts the OpenAI format request into the provider's native format.

**Input:**
- `messages`: List of message dicts with `role` and `content`
- `model_id`: Model name to use
- `**kwargs`: Optional parameters like `temperature`, `max_tokens`, `top_p`, `stop`

**Output:**
- `TransformedRequest` object containing:
  - `data`: The request dict in provider's native format
  - `original_model_id`: The model ID from config
  - `provider_model_id`: The model ID for this provider

**Example (OpenAI-compatible):**
```python
def translate_request(self, messages, model_id, **kwargs):
    request = {
        "model": model_id,
        "messages": messages,
    }
    
    # Add optional parameters if provided
    for key in ["temperature", "top_p", "stop"]:
        if key in kwargs and kwargs[key] is not None:
            request[key] = kwargs[key]
    
    # Handle max_tokens (supports both max_tokens and max_completion_tokens)
    max_tokens = kwargs.get("max_tokens") or kwargs.get("max_completion_tokens")
    if max_tokens is not None:
        request["max_tokens"] = max_tokens
    
    return TransformedRequest(
        data=request,
        original_model_id=model_id,
        provider_model_id=model_id,
    )
```

### 2. `make_request(request_data, api_key) -> dict`

Makes the actual HTTP request to the provider's API.

**Input:**
- `request_data`: The request dict from `translate_request().data`
- `api_key`: The API key for authentication

**Output:**
- Raw response dict from the provider

**Must raise exceptions on failure** - the proxy will catch them and try the next provider.

**Example:**
```python
def make_request(self, request_data, api_key):
    url = f"{self.base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.post(
            url,
            json=request_data,
            headers=headers,
            timeout=self.timeout
        )
        
        if response.status_code != 200:
            raise Exception(f"API error {response.status_code}: {response.text}")
        
        return response.json()
    except requests.exceptions.Timeout:
        raise Exception(f"Request timeout after {self.timeout}s")
    except Exception as e:
        raise Exception(f"Request failed: {e}")
```

### 3. `translate_response(response_data, original_request) -> TransformedResponse`

Converts the provider's response into OpenAI format.

**Input:**
- `response_data`: Raw response dict from the API
- `original_request`: Original request data (for context)

**Output:**
- `TransformedResponse` object containing:
  - `data`: Response dict in OpenAI format
  - `provider_name`: Name of this provider instance (from config)
  - `original_request`: The request that was sent

**Requirements:**
- Response must include: `id`, `object`, `created`, `model`, `choices`, `usage`, `provider`
- Each choice must have: `index`, `message`, `finish_reason`
- Usage must have: `prompt_tokens`, `completion_tokens`, `total_tokens`

**Example:**
```python
def translate_response(self, response_data, original_request):
    response = dict(response_data)
    
    # Ensure required fields
    if "id" not in response:
        response["id"] = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    if "object" not in response:
        response["object"] = "chat.completion"
    if "created" not in response:
        response["created"] = int(time.time())
    if "model" not in response:
        response["model"] = original_request.get("model", "unknown")
    if "usage" not in response:
        response["usage"] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    if "choices" not in response:
        response["choices"] = []
    
    # Add provider name from config
    response["provider"] = self.name
    
    return TransformedResponse(
        data=response,
        provider_name=self.name,
        original_request=original_request,
    )
```

## Optional Methods

You can override these for custom behavior:

### `validate_request(messages, model_id, **kwargs) -> ValidationResult`

Validate the request before sending. Default implementation checks for non-empty messages and valid structure.

```python
def validate_request(self, messages, model_id, **kwargs):
    errors = []
    
    # Your custom validation logic
    if not messages:
        errors.append(ValidationError(
            field="messages",
            message="Messages cannot be empty",
            code="EMPTY_MESSAGES"
        ))
    
    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors
    )
```

### `prefill_request(messages, model_id, **kwargs) -> dict`

Provide default values for optional parameters.

```python
def prefill_request(self, messages, model_id, **kwargs):
    prefilled = {}
    
    # Set reasonable defaults
    if "temperature" not in kwargs or kwargs["temperature"] is None:
        prefilled["temperature"] = 0.7
    
    return prefilled
```

## Registering Your Provider

1. **Add to provider classes map** in `src/providers/__init__.py` or `src/registry.py`:

```python
from .anthropic import AnthropicProvider

PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,  # Add this line
}
```

2. **Use in config** (`config/config.yaml`):

```yaml
providers:
  anthropic_instance:
    type: anthropic  # Must match the key in PROVIDER_CLASSES
    base_url: https://api.anthropic.com/v1
    api_keys:
      - sk-ant-xxxxx

models:
  claude-3:
    providers:
      anthropic_instance:
        model_id: claude-3-opus-20240229
```

3. **Update schema** (`config/schema.json`):

Add your provider type to the enum:
```json
"type": {
    "type": "string",
    "enum": ["openai", "anthropic"],
    "description": "Provider type"
}
```

## Testing Your Provider

Add a simple test function:

```python
# test_anthropic.py
from src.providers.anthropic import AnthropicProvider

provider = AnthropicProvider("test", {
    "base_url": "https://api.anthropic.com/v1",
    "timeout": 60,
})

# Test request translation
messages = [{"role": "user", "content": "Hello"}]
transformed = provider.translate_request(messages, "claude-3-opus-20240229")
print("Request:", transformed.data)

# Test validation (optional)
result = provider.validate_request(messages, "claude-3-opus-20240229")
print("Valid:", result.is_valid)
```

## Common Pitfalls

1. **Forgetting to set `response["provider"]`** - The client needs to know which provider handled the request
2. **Not handling missing fields** - Always ensure all required fields exist in the response
3. **Not raising exceptions on failure** - The proxy won't know to try the next provider
4. **Parameter mapping differences** - Different APIs use different parameter names (e.g., `max_tokens` vs `max_completion_tokens`)
5. **Token counting** - Make sure your provider returns `usage.prompt_tokens` and `usage.completion_tokens`

## Performance Tips

- **Cache common values** in `__init__` (like base_url, timeout)
- **Reuse HTTP connections** by using requests.Session if making multiple calls
- **Don't over-validate** - let the API reject invalid requests
- **Stream errors** - raise exceptions early, don't accumulate errors

## Debug Mode

To test your provider without the full proxy, you can instantiate it directly:

```python
provider = YourProvider("test", config)
response = provider.chat_completion(
    messages=[{"role": "user", "content": "test"}],
    model_id="your-model",
    api_key="your-key",
    temperature=0.7
)
print(response)
```

The full response will include metadata you can inspect to debug issues.
