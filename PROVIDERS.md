redisnotblue-ai/PROVIDERS.md
# Creating Custom Providers

This comprehensive guide covers the Providers API for the OpenAI-compatible proxy server. The provider system enables seamless integration with any LLM API by implementing a standardized interface that handles request transformation, API communication, response normalization, and advanced features like rate limiting, failover, and streaming.

## Table of Contents

- [Overview](#overview)
- [Provider Interface](#provider-interface)
- [Data Structures](#data-structures)
- [Configuration](#configuration)
- [Request Flow](#request-flow)
- [Supported Parameters](#supported-parameters)
- [Streaming Support](#streaming-support)
- [Rate Limiting](#rate-limiting)
- [Error Handling](#error-handling)
- [Multi-Modal Content](#multi-modal-content)
- [Tool Calling](#tool-calling)
- [Authentication](#authentication)
- [Testing](#testing)
- [Debug Mode](#debug-mode)
- [Performance Tips](#performance-tips)
- [Common Pitfalls](#common-pitfalls)
- [Examples](#examples)

## Overview

The proxy server uses a provider-based architecture where each external API (OpenAI, Anthropic, custom endpoints) is encapsulated in a `Provider` class. Providers handle:

- **Request Translation**: Converting OpenAI-format requests to provider-specific formats
- **API Communication**: Making HTTP requests with proper authentication and error handling
- **Response Normalization**: Converting provider responses to standardized OpenAI format
- **Validation**: Ensuring requests meet provider requirements
- **Rate Limiting**: Enforcing usage limits at multiple levels
- **Failover**: Automatic fallback to alternative providers on failure

The system supports load balancing, priority-based routing, and comprehensive rate limiting with both token-based and credit-based budgeting.

## Provider Interface

All providers inherit from the abstract `Provider` class in `src/providers/base.py`. You must implement three core methods, with optional overrides for customization.

### Core Methods

#### 1. `translate_request(messages, model_id, **kwargs) -> TransformedRequest`

Converts OpenAI chat completion requests to the provider's native API format.

**Parameters:**
- `messages`: List of message dictionaries with `role`, `content`, and optional `tool_calls` keys. Content can be a string or array of content blocks for multimodality.
- `model_id`: The provider-specific model identifier
- `**kwargs`: Optional parameters (see [Supported Parameters](#supported-parameters) section)

**Returns:** `TransformedRequest` object containing:
- `data`: Provider-specific request payload
- `original_model_id`: Original model ID from client request
- `provider_model_id`: Model ID for this provider
- `prefilled_fields`: Default values that were applied
- `route_info`: Metadata for routing decisions

**Example (OpenAI-compatible):**
```redisnotblue-ai/src/providers/openai.py#L20-35
def translate_request(
    self, messages: list[dict], model_id: str, **kwargs
) -> TransformedRequest:
    """Build OpenAI format request."""
    request = {
        "model": model_id,
        "messages": messages,
        "stream": True,
    }

    for key in ["temperature", "top_p", "stop", "max_tokens"]:
        if key in kwargs and kwargs[key] is not None:
            request[key] = kwargs[key]

    return TransformedRequest(
        data=request,
        original_model_id=model_id,
        provider_model_id=model_id,
    )
```

#### 2. `make_request(request_data, api_key) -> dict`

Executes the HTTP request to the provider's API.

**Parameters:**
- `request_data`: The transformed request payload from `translate_request().data`
- `api_key`: Authentication key for the provider

**Returns:** Raw response dictionary from the provider API

**Must raise exceptions on failure** to enable automatic failover to the next provider.

**Example:**
```redisnotblue-ai/src/providers/openai.py#L39-66
def make_request(self, request_data: dict, api_key: str) -> dict:
    """Make streaming request to OpenAI-compatible API and collect all chunks."""
    url = f"{self.base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start_time = time.time()
    try:
        response = requests.post(
            url,
            json=request_data,
            headers=headers,
            timeout=self.timeout,
            stream=True
        )

        if response.status_code != 200:
            raise Exception(
                f"OpenAI API error {response.status_code}: {response.text}"
            )

        return self._process_stream(response, start_time)
    except requests.exceptions.Timeout:
        raise Exception(f"OpenAI API timeout after {self.timeout}s")
    except requests.exceptions.ConnectionError as e:
        raise Exception(f"OpenAI API connection error: {e}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"OpenAI API request error: {e}")
```

#### 3. `translate_response(response_data, original_model_id) -> TransformedResponse`

Converts provider-specific responses to OpenAI chat completion format.

**Parameters:**
- `response_data`: Raw response from `make_request()`
- `original_model_id`: The canonical model ID requested by the client

**Returns:** `TransformedResponse` object containing:
- `data`: OpenAI-formatted response
- `provider_name`: Name of the provider instance
- `original_request`: Original request data for debugging

**Required Response Fields:**
- `id`: Unique completion ID
- `object`: Must be `"chat.completion"`
- `created`: Unix timestamp
- `model`: Original model ID from request
- `choices`: Array of completion choices
- `usage`: Token usage statistics
- `provider`: Provider name for client identification

**Choice Structure:**
- `index`: Zero-based choice index
- `message`: Assistant message with `role` and `content`
- `finish_reason`: Completion reason ("stop", "length", etc.)

**Usage Structure:**
- `prompt_tokens`: Input token count
- `completion_tokens`: Output token count
- `total_tokens`: Sum of prompt and completion tokens

**Example:**
```redisnotblue-ai/src/providers/openai.py#L90-115
def translate_response(
    self,
    response_data: dict,
    original_model_id: str,
) -> TransformedResponse:
    """Convert provider's response to OpenAI format."""
    usage = response_data.get("usage", {})
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    ttft = response_data.get("ttft")

    response = {
        "id": response_data.get("id", f"chatcmpl-{uuid.uuid4()}"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": original_model_id,
        "choices": response_data.get("choices", []),
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": usage.get("total_tokens", (prompt or 0) + (completion or 0))
        },
        "provider": self.name
    }

    if ttft:
        response["ttft"] = ttft

    return TransformedResponse(
        data=response,
        provider_name=self.name,
        original_request={},
    )
```

### Optional Methods

#### `validate_request(messages, model_id, **kwargs) -> ValidationResult`

Pre-flight validation of requests. Default implementation checks for empty messages and basic structure.

**Returns:** `ValidationResult` with `is_valid` boolean and list of `ValidationError` objects.

**Example:**
```redisnotblue-ai/src/providers/base.py#L32-67
def validate_request(
    self,
    messages: list[dict],
    model_id: str,
    **kwargs
) -> ValidationResult:
    """
    Validate request data before sending to provider.
    Can be overridden by subclasses to implement custom validation.
    """
    errors = []

    # Basic validation
    if not messages:
        errors.append(ValidationError(
            field="messages",
            message="Messages list cannot be empty",
            code="EMPTY_MESSAGES"
        ))

    if not model_id:
        errors.append(ValidationError(
            field="model_id",
            message="Model ID is required",
            code="MISSING_MODEL_ID"
        ))

    # Validate message structure
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            errors.append(ValidationError(
                field=f"messages[{i}]",
                message="Message must be a dict",
                code="INVALID_MESSAGE_TYPE"
            ))
            continue

        if "role" not in msg:
            errors.append(ValidationError(
                field=f"messages[{i}].role",
                message="Message role is required",
                code="MISSING_ROLE"
            ))

        if "content" not in msg:
            errors.append(ValidationError(
                field=f"messages[{i}].content",
                message="Message content is required",
                code="MISSING_CONTENT"
            ))

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors
    )
```

#### `prefill_request(messages, model_id, **kwargs) -> dict`

Provides default values for optional parameters. Useful for setting provider-specific defaults.

**Returns:** Dictionary of default parameter values.

**Example:**
```redisnotblue-ai/src/providers/base.py#L69-82
def prefill_request(
    self,
    messages: list[dict],
    model_id: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Provide prefilled/default values for the request.
    Subclasses can override to add provider-specific defaults.
    """
    return {}
```

## Data Structures

### TransformedRequest

Contains the transformed request data and metadata.

```redisnotblue-ai/src/providers/base.py#L7-13
@dataclass
class TransformedRequest:
    """Request after transformation with metadata."""
    data: dict
    original_model_id: str
    provider_model_id: str
    prefilled_fields: Dict[str, Any] = field(default_factory=dict)
    route_info: Dict[str, Any] = field(default_factory=dict)
```

### TransformedResponse

Contains the normalized response data and metadata.

```redisnotblue-ai/src/providers/base.py#L15-20
@dataclass
class TransformedResponse:
    """Response after transformation with metadata."""
    data: dict
    provider_name: str
    original_request: Dict[str, Any] = field(default_factory=dict)
```

### ValidationResult

Result of request validation with any errors found.

```redisnotblue-ai/src/providers/base.py#L22-25
@dataclass
class ValidationResult:
    """Result of request validation."""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
```

### ValidationError

Represents a specific validation error.

```redisnotblue-ai/src/providers/base.py#L3-6
@dataclass
class ValidationError:
    """Represents a validation error with details."""
    field: str
    message: str
    code: Optional[str] = None
```

## Configuration

Providers are configured in `config/config.yaml` with extensive options for rate limiting, authentication, and behavior.

### Provider Configuration

```yaml
providers:
  my_provider:
    type: openai  # Must match PROVIDER_CLASSES key
    base_url: https://api.example.com/v1
    chat_completions_path: /chat/completions  # Optional path override
    api_keys:
      - sk-key1
      - sk-key2
    timeout: 60
    rate_limits:  # Provider-level defaults
      requests_per_minute: 100
      tokens_per_hour: 10000
```

### Model-Provider Configuration

```yaml
models:
  gpt-4:
    providers:
      my_provider:
        model_id: gpt-4-turbo  # Provider-specific model name
        priority: 0  # Lower = higher priority
        api_keys:  # Override provider keys
          - sk-specific-key
        rate_limits:
          requests_per_minute: 50
          tokens_per_day: 50000
          credits_per_hour: 10.0
        credits_per_token: 0.002  # $0.002 per token
        credits_per_request: 0.1   # $0.10 per request
        max_retries: 3
        multiplier: 1.0  # Request/token counting multiplier
```

### Rate Limiting Options

The proxy supports multiple rate limiting strategies:

**Request-Based Limits:**
- `requests_per_minute/hour/day/month`

**Token-Based Limits:**
- `tokens_per_*`: Total tokens (prompt + completion)
- `in_tokens_per_*`: Input tokens only
- `out_tokens_per_*`: Output tokens only

**Credit-Based Limits:**
- `credits_per_token`: Cost per token
- `credits_per_million_tokens`: Per-million pricing
- `credits_per_request`: Fixed cost per request
- `credits_per_minute/hour/day/month`: Credit budgets

**Multipliers:**
- `multiplier`: Overall request/token multiplier
- `token_multiplier`: Token-specific multiplier
- `request_multiplier`: Request-specific multiplier

## Request Flow

1. **Client Request** → FastAPI endpoint receives OpenAI-format request
2. **Model Resolution** → Registry finds model configuration
3. **Provider Selection** → Load balancer selects provider based on priority/health
4. **Validation** → `validate_request()` checks request validity
5. **Prefilling** → `prefill_request()` applies defaults
6. **Translation** → `translate_request()` converts to provider format
7. **API Call** → `make_request()` executes HTTP request
8. **Response Translation** → `translate_response()` normalizes response
9. **Rate Limiting** → Usage is tracked and limits enforced
10. **Response** → OpenAI-format response returned to client

## Supported Parameters

The proxy supports the core OpenAI Chat Completions API parameters:

### Core Parameters
- `model`: Model identifier (required)
- `messages`: Array of message objects (required)
- `temperature`: Sampling temperature (0.0 to 2.0)
- `max_tokens`: Maximum tokens to generate
- `max_completion_tokens`: Alternative to max_tokens
- `top_p`: Nucleus sampling parameter (0.0 to 1.0)
- `stop`: Stop sequences (string or array)
- `stream`: Enable streaming responses

### Tool Calling Parameters
- `tools`: Array of available tools/functions
- `tool_choice`: Control tool usage ("auto", "none", "required", or specific function)

### Message Structure
Messages support:
- `role`: "system", "user", "assistant", "tool"
- `content`: String or array of content blocks (for multimodality)
- `tool_calls`: Array of tool calls (assistant messages)
- `tool_call_id`: ID for tool result messages

### Content Blocks (Multimodality)
- `{"type": "text", "text": "..."}`: Text content
- `{"type": "image_url", "image_url": {"url": "..."}}`: Image content

### Tool Definitions
```json
{
  "type": "function",
  "function": {
    "name": "function_name",
    "description": "Function description",
    "parameters": {
      "type": "object",
      "properties": {...}
    }
  }
}
```

## Streaming Support

The proxy supports streaming responses for real-time token delivery. Providers should:

1. Set `"stream": true` in request translation
2. Use `stream=True` in HTTP requests
3. Process Server-Sent Events (SSE) format
4. Return complete response with accumulated content

**Streaming Response Format:**
```
data: {"id": "chatcmpl-123", "choices": [{"delta": {"content": "Hello"}}]}\n\n
data: {"id": "chatcmpl-123", "choices": [{"delta": {"content": " world"}}]}\n\n
data: [DONE]\n\n
```

**Example Streaming Implementation:**
```redisnotblue-ai/src/providers/openai.py#L68-89
def _process_stream(self, response, start_time) -> dict:
    """Process streaming response and collect chunks."""
    chunks = []
    first_chunk_time = None
    finish_reason = None
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    for line in response.iter_lines():
        if not line:
            continue

        line = line.decode('utf-8') if isinstance(line, bytes) else line

        if line.startswith('data: '):
            data_str = line[6:]

            if data_str == '[DONE]':
                break

            try:
                chunk = json.loads(data_str)

                if first_chunk_time is None:
                    first_chunk_time = time.time() - start_time

                if "choices" in chunk and chunk["choices"]:
                    choice = chunk["choices"][0]
                    if "delta" in choice and "content" in choice["delta"] and choice["delta"]["content"] is not None:
                        chunks.append(choice["delta"]["content"])
                    if "finish_reason" in choice and choice["finish_reason"]:
                        finish_reason = choice["finish_reason"]

                if "usage" in chunk:
                    usage = chunk["usage"]

            except json.JSONDecodeError:
                continue

    content = "".join(chunks)

    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": finish_reason or "stop"
            }
        ],
        "usage": usage,
        "ttft": first_chunk_time if first_chunk_time else None
    }
```

## Rate Limiting

The proxy implements sophisticated rate limiting with multiple enforcement levels:

### Enforcement Levels

1. **Provider Level**: Default limits for all models using the provider
2. **Model-Provider Level**: Specific limits for each model-provider combination
3. **API Key Level**: Per-key limits (when using multiple keys)

### Limit Types

**Sliding Window Limits:**
- Request and token limits use sliding windows (e.g., last 60 seconds)
- Example: `requests_per_minute: 100` allows 100 requests in any 60-second window

**Calendar-Based Limits:**
- Credit limits reset at calendar boundaries
- `credits_per_hour`: Resets at :00 minutes
- `credits_per_day`: Resets at 00:00 UTC
- `credits_per_month`: Resets on 1st at 00:00 UTC

### Credit Calculation

Credits are calculated from token counts and fixed fees:

```python
total_credits = (prompt_tokens * credits_per_in_token) + 
                (completion_tokens * credits_per_out_token) + 
                credits_per_request
```

## Error Handling

Providers must raise exceptions on API failures to trigger failover. The proxy catches and handles:

- **HTTP Errors**: Non-2xx status codes
- **Timeouts**: Request timeouts
- **Connection Errors**: Network issues
- **Rate Limits**: 429 responses (may retry different provider/key)
- **Authentication Errors**: Invalid API keys

**Exception Format:**
```python
raise Exception(f"Provider error: {details}")
```

The proxy will:
1. Log the error
2. Try the next provider in priority order
3. Return error to client if all providers fail





## Multi-Modal Content

The proxy now supports multi-modal content through OpenAI's content array format, allowing messages to contain text, images, and other media types.

**Message Format:**
```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "What's in this image?"},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
  ]
}
```

**Provider Implementation:**
```redisnotblue-ai/src/providers/antigravity/antigravity.py#L247-259
# Multi-modal content handling
elif isinstance(content, list):
    # Multi-modal content
    parts = []
    for item in content:
        if item["type"] == "text":
            parts.append({"text": item["text"]})
        elif item["type"] == "image_url":
            # Handle images (simplified - you may need base64 decoding)
            parts.append({
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": item["image_url"]["url"]
                }
            })
```

**Supported Content Types:**
- `text`: Plain text content
- `image_url`: Images via URL or base64 data

## Tool Calling

The proxy supports function/tool calling through OpenAI's tools format, enabling models to call external functions and APIs.

**Request Format:**
```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get weather information",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"}
          }
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

**Response Format:**
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_123",
            "type": "function",
            "function": {
              "name": "get_weather",
              "arguments": "{\"location\": \"New York\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

**Provider Implementation Example:**
```redisnotblue-ai/src/providers/antigravity/antigravity.py#L289-307
# Add tools if provided
if kwargs.get("tools"):
    # Convert OpenAI tools to Gemini functionDeclarations
    function_declarations = []
    for tool in kwargs["tools"]:
        if tool.get("type") == "function":
            func = tool["function"]
            declaration = {
                "name": func["name"],
                "description": func.get("description", "")
            }
            if "parameters" in func:
                declaration["parameters"] = self._clean_schema(func["parameters"])
            function_declarations.append(declaration)

    if function_declarations:
        request_payload["tools"] = [{"functionDeclarations": function_declarations}]
```

**Tool Choice Options:**
- `"auto"`: Model decides whether to call tools
- `"none"`: Model cannot call tools
- `"required"`: Model must call at least one tool
- `{"type": "function", "function": {"name": "specific_function"}}`: Force specific function call

## Authentication

Providers support various authentication methods:

### API Key (Bearer Token)
```redisnotblue-ai/src/providers/openai.py#L41-44
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}
```

### Custom Headers
```redisnotblue-ai/src/providers/github_copilot.py#L48-58
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "GitHubCopilotChat/0.26.7",
    "Editor-Version": "vscode/1.96.5",
    "Editor-Plugin-Version": "copilot-chat/0.26.7",
}
```

### Cookie-Based
```redisnotblue-ai/src/providers/yupp.py#L32-38
headers = {
    "cookie": f"__Secure-yupp.session-token={api_key}",
    "content-type": "text/plain;charset=UTF-8",
    "accept": "text/x-component",
    "next-action": "d6dcb36c50a0282ee9aa466903ba1f02fa093f87",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
}
```

## Testing

### Unit Testing

Create test functions for your provider:

```python
def test_my_provider():
    provider = MyProvider("test", {
        "base_url": "https://api.example.com/v1",
        "timeout": 60,
    })

    # Test request translation
    messages = [{"role": "user", "content": "Hello"}]
    transformed = provider.translate_request(messages, "my-model")
    assert transformed.data["model"] == "my-model"
    assert "messages" in transformed.data

    # Test validation
    result = provider.validate_request(messages, "my-model")
    assert result.is_valid

    print("All tests passed!")
```

### Integration Testing

Test with real API calls (use test keys):

```python
def test_integration():
    provider = MyProvider("test", config)
    
    response = provider.chat_completion(
        messages=[{"role": "user", "content": "Hello"}],
        model_id="my-model",
        api_key="test-key"
    )
    
    assert "choices" in response
    assert len(response["choices"]) > 0
    print("Integration test passed!")
```

## Debug Mode

Test providers directly without the full proxy:

```python
provider = MyProvider("debug", config)

# Manual testing
messages = [{"role": "user", "content": "Test message"}]
transformed = provider.translate_request(messages, "model-id")
print("Request:", transformed.data)

# Full completion test
response = provider.chat_completion(
    messages=messages,
    model_id="model-id",
    api_key="your-api-key",
    temperature=0.7
)
print("Response:", response)
```

## Performance Tips

1. **Cache Configuration**: Store parsed config values in `__init__`
2. **Connection Reuse**: Use `requests.Session()` for multiple calls
3. **Minimal Validation**: Let APIs reject invalid requests
4. **Early Error Raising**: Fail fast to enable quick failover
5. **Efficient Streaming**: Process chunks incrementally
6. **Token Estimation**: Cache token counts for rate limiting
7. **Async Considerations**: Design for concurrent requests

## Common Pitfalls

1. **Missing Provider Field**: Always set `response["provider"] = self.name`
2. **Incomplete Response Fields**: Ensure all required OpenAI fields exist
3. **Silent Failures**: Always raise exceptions on API errors
4. **Parameter Mismapping**: Different APIs use different parameter names
5. **Token Counting**: Return accurate `usage` for rate limiting
6. **Streaming State**: Maintain state across streaming chunks
7. **Validation Overload**: Don't duplicate API validation logic
8. **Memory Leaks**: Clean up connections and large response data
9. **Race Conditions**: Handle concurrent requests safely
10. **Error Masking**: Preserve original error details for debugging

## Examples

### Complete OpenAI-Compatible Provider

```redisnotblue-ai/src/providers/openai.py#L1-115
"""OpenAI provider implementation with streaming support and TTFT tracking."""

import requests
import uuid
import time
import json
from .base import Provider, TransformedRequest, TransformedResponse


class OpenAIProvider(Provider):
    """Provider for OpenAI-compatible APIs with streaming support."""

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.timeout = config.get("timeout", 60)
        self.chat_completions_path = config.get("chat_completions_path", "/chat/completions")

    def translate_request(
        self, messages: list[dict], model_id: str, **kwargs
    ) -> TransformedRequest:
        """Build OpenAI format request."""
        request = {
            "model": model_id,
            "messages": messages,
            "stream": True,
        }

        for key in ["temperature", "top_p", "stop", "max_tokens"]:
            if key in kwargs and kwargs[key] is not None:
                request[key] = kwargs[key]

        return TransformedRequest(
            data=request,
            original_model_id=model_id,
            provider_model_id=model_id,
        )

    def make_request(self, request_data: dict, api_key: str) -> dict:
        """Make streaming request to OpenAI-compatible API and collect all chunks."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        start_time = time.time()
        try:
            response = requests.post(
                url,
                json=request_data,
                headers=headers,
                timeout=self.timeout,
                stream=True
            )

            if response.status_code != 200:
                raise Exception(
                    f"OpenAI API error {response.status_code}: {response.text}"
                )

            return self._process_stream(response, start_time)
        except requests.exceptions.Timeout:
            raise Exception(f"OpenAI API timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"OpenAI API connection error: {e}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"OpenAI API request error: {e}")

    def _process_stream(self, response, start_time) -> dict:
        """Process streaming response and collect chunks."""
        chunks = []
        first_chunk_time = None
        finish_reason = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0}

        for line in response.iter_lines():
            if not line:
                continue

            line = line.decode('utf-8') if isinstance(line, bytes) else line

            if line.startswith('data: '):
                data_str = line[6:]

                if data_str == '[DONE]':
                    break

                try:
                    chunk = json.loads(data_str)

                    if first_chunk_time is None:
                        first_chunk_time = time.time() - start_time

                    if "choices" in chunk and chunk["choices"]:
                        choice = chunk["choices"][0]
                        if "delta" in choice and "content" in choice["delta"] and choice["delta"]["content"] is not None:
                            chunks.append(choice["delta"]["content"])
                        if "finish_reason" in choice and choice["finish_reason"]:
                            finish_reason = choice["finish_reason"]

                    if "usage" in chunk:
                        usage = chunk["usage"]

                except json.JSONDecodeError:
                    continue

        content = "".join(chunks)

        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": finish_reason or "stop"
                }
            ],
            "usage": usage,
            "ttft": first_chunk_time if first_chunk_time else None
        }

    def translate_response(
        self,
        response_data: dict,
        original_model_id: str,
    ) -> TransformedResponse:
        """Convert provider's response to OpenAI format."""
        usage = response_data.get("usage", {})
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        ttft = response_data.get("ttft")

        response = {
            "id": response_data.get("id", f"chatcmpl-{uuid.uuid4()}"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": original_model_id,
            "choices": response_data.get("choices", []),
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": usage.get("total_tokens", (prompt or 0) + (completion or 0))
            },
            "provider": self.name
        }

        if ttft:
            response["ttft"] = ttft

        return TransformedResponse(
            data=response,
            provider_name=self.name,
            original_request={},
        )
```

### Advanced Antigravity Provider Excerpt

```redisnotblue-ai/src/providers/antigravity/antigravity.py#L216-280
def translate_request(
    self,
    messages: List[Dict[str, Any]],
    model_id: str,
    **kwargs
) -> TransformedRequest:
    """Transform OpenAI format to Antigravity format."""

    # Resolve model
    api_model, thinking_level, thinking_config = self.resolve_model(model_id)

    # Convert OpenAI messages to Gemini contents format
    contents = []
    system_instruction = None

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "system":
            # System messages go in systemInstruction
            system_instruction = content
            continue

        # Map assistant -> model for Gemini
        if role == "assistant":
            role = "model"

        # Convert content to parts
        if isinstance(content, str):
            parts = [{"text": content}]
        else:
            parts = [{"text": str(content)}]

        contents.append({
            "role": role,
            "parts": parts
        })

    # Build request payload
    request_payload = {
        "contents": contents
    }

    # Add system instruction
    if system_instruction:
        request_payload["systemInstruction"] = {
            "role": "user",  # Antigravity requires "user" role
            "parts": [{"text": system_instruction}]
        }

    # Add thinking configuration
    if thinking_config:
        request_payload["thinkingConfig"] = thinking_config

    # Add thinking level for Gemini models
    if thinking_level:
        if "generationConfig" not in request_payload:
            request_payload["generationConfig"] = {}
        request_payload["generationConfig"]["thinkingLevel"] = thinking_level

    # Add optional parameters
    if kwargs.get("temperature") is not None:
        if "generationConfig" not in request_payload:
            request_payload["generationConfig"] = {}
        request_payload["generationConfig"]["temperature"] = kwargs["temperature"]

    if kwargs.get("top_p") is not None:
        if "generationConfig" not in request_payload:
            request_payload["generationConfig"] = {}
        request_payload["generationConfig"]["topP"] = kwargs["top_p"]

    max_tokens = kwargs.get("max_tokens") or kwargs.get("max_completion_tokens")
    if max_tokens:
        if "generationConfig" not in request_payload:
            request_payload["generationConfig"] = {}
        request_payload["generationConfig"]["maxOutputTokens"] = max_tokens

    if kwargs.get("stop"):
        stops = kwargs["stop"] if isinstance(kwargs["stop"], list) else [kwargs["stop"]]
        if "generationConfig" not in request_payload:
            request_payload["generationConfig"] = {}
        request_payload["generationConfig"]["stopSequences"] = stops

    # Get project ID
    refresh_token = self.refresh_tokens[self.current_account]
    access_token = self.get_access_token(refresh_token)

    # Fetch project ID if not cached
    if refresh_token not in self.token_cache or "project_id" not in self.token_cache[refresh_token]:
        project_id = self.fetch_project_id(access_token)
        if refresh_token in self.token_cache:
            self.token_cache[refresh_token]["project_id"] = project_id
    else:
        project_id = self.token_cache[refresh_token]["project_id"]

    # Wrap in Antigravity envelope
    wrapped_request = {
        "project": project_id,
        "model": api_model,
        "request": request_payload,
        "requestType": "agent",
        "userAgent": "antigravity",
        "requestId": f"agent-{uuid.uuid4().hex}"
    }

    return TransformedRequest(
        data=wrapped_request,
        original_model_id=model_id,
        provider_model_id=api_model
    )
```

This comprehensive guide covers all aspects of implementing custom providers for the OpenAI-compatible proxy server. The provider system is designed to be flexible, robust, and extensible, supporting everything from simple API wrappers to complex integrations with advanced features like streaming, multimodality, tool calling, and comprehensive rate limiting.