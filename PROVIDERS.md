# Adding Custom Providers

The proxy uses an extensible provider architecture to support multiple LLM APIs. All providers inherit from the `Provider` base class and implement three core methods.

## Architecture

### Provider Base Class

All providers must inherit from `Provider` and implement:

```python
from providers.base import Provider

class MyProvider(Provider):
    def translate_request(self, messages: list[dict], model_id: str, **kwargs) -> dict:
        """Convert OpenAI format to provider's native format."""
        pass

    def make_request(self, request_data: dict, api_key: str) -> dict:
        """Make the actual API request."""
        pass

    def translate_response(self, response_data: dict) -> dict:
        """Convert provider response to OpenAI format."""
        pass
```

The `chat_completion()` method is inherited and orchestrates these three steps.

## Adding a New Provider

### 1. Create the Provider

Create `src/providers/yourprovider.py`:

```python
import requests
from .base import Provider

class YourProvider(Provider):
    """Provider for Your API."""

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.base_url = config.get("base_url", "https://api.yourservice.com/v1")
        self.timeout = config.get("timeout", 60)

    def translate_request(self, messages: list[dict], model_id: str, **kwargs) -> dict:
        """Convert OpenAI format to Your API format."""
        request = {
            "model": model_id,
            "messages": messages,
        }
        
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            request["temperature"] = kwargs["temperature"]
        
        # Add other parameters as needed
        return request

    def make_request(self, request_data: dict, api_key: str) -> dict:
        """Make HTTP request to Your API."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            url,
            json=request_data,
            headers=headers,
            timeout=self.timeout
        )

        if response.status_code != 200:
            raise Exception(f"API error {response.status_code}: {response.text}")

        return response.json()

    def translate_response(self, response_data: dict) -> dict:
        """Convert Your API response to OpenAI format."""
        # Map your response format to OpenAI's format
        return {
            "id": response_data.get("id", ""),
            "object": "chat.completion",
            "created": int(__import__('time').time()),
            "model": response_data.get("model", ""),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_data.get("content", "")
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": response_data.get("prompt_tokens", 0),
                "completion_tokens": response_data.get("completion_tokens", 0),
                "total_tokens": response_data.get("total_tokens", 0)
            }
        }
```

### 2. Register the Provider

Edit `src/registry.py` and add to `PROVIDER_CLASSES`:

```python
from providers.yourprovider import YourProvider

PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
    "yourprovider": YourProvider,
}
```

### 3. Configure in config.yaml

```yaml
providers:
  your_instance:
    type: yourprovider
    api_key: ${YOUR_API_KEY}
    base_url: https://api.yourservice.com/v1  # optional
    timeout: 60  # optional

models:
  your-model:
    owned_by: your-company
    providers:
      your_instance:
        priority: 0
        model_id: your-actual-model-name
```

## Translation Functions

### translate_request()

Converts the unified OpenAI format to your provider's native format. Always receives:
- `messages`: List of `{"role": "user"|"assistant"|"system", "content": "..."}` dicts
- `model_id`: The model identifier for this provider
- `**kwargs`: Optional parameters (temperature, max_tokens, top_p, stop)

Must return a dict ready to POST to your API.

### make_request()

Handles the HTTP communication. Your job:
1. Build the URL and headers
2. Make the request
3. Handle errors
4. Return the parsed JSON response

### translate_response()

Converts your API's response to OpenAI format. The response MUST have:

```python
{
    "id": "chatcmpl-...",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "model-name",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "response text"
            },
            "finish_reason": "stop"|"length"|"content_filter"
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30
    }
}
```

## Example: Anthropic Claude

See `examples/anthropic_provider.py` for a complete example of adding Anthropic's Claude API.

Key differences from OpenAI:
- System messages handled separately
- Response has `content` blocks instead of flat text
- Token counts named `input_tokens`/`output_tokens`

## Testing Your Provider

```bash
# Start the server
cd src
python -m uvicorn app:app --reload

# Test the endpoint
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "your-model",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Error Handling

Your `make_request()` should raise exceptions for:
- Network errors
- API errors (non-200 status codes)
- Timeouts
- Malformed responses

The proxy's retry logic will handle these automatically:
- Round-robin to next API key on failure
- Fall back to next provider if all keys exhausted
- Automatic cooldown and retry with exponential backoff

## Best Practices

1. **Inherit from Provider**: Ensures compatibility with the retry/failover system
2. **Use super().__init__()**: Properly initializes base class
3. **Handle API differences**: Abstract them in translate_request/response
4. **Validate responses**: Check for required fields before returning
5. **Set reasonable defaults**: For timeout and other config values
6. **Document API mappings**: Comment on format conversions in translate methods
7. **Support environment variables**: Use `${VAR_NAME}` in config for secrets
