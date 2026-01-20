"""Example: Anthropic provider implementation.

This shows how to add support for Anthropic's Claude API.
To use this, register it in src/registry.py:

    from providers.anthropic import AnthropicProvider
    
    PROVIDER_CLASSES = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }

Then in config.yaml:

    providers:
      anthropic:
        type: anthropic
        api_key: ${ANTHROPIC_API_KEY}
    
    models:
      claude-opus:
        providers:
          anthropic:
            priority: 0
            model_id: claude-3-opus-20240229
"""

import requests
from providers.base import Provider


class AnthropicProvider(Provider):
    """Provider for Anthropic's Claude API."""

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.base_url = config.get("base_url", "https://api.anthropic.com/v1")
        self.timeout = config.get("timeout", 60)

    def translate_request(
        self, messages: list[dict], model_id: str, **kwargs
    ) -> dict:
        """Convert OpenAI format to Anthropic format."""
        # Anthropic expects system message separate from messages
        system = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        request = {
            "model": model_id,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens") or kwargs.get("max_completion_tokens") or 1024,
        }

        if system:
            request["system"] = system

        if "temperature" in kwargs and kwargs["temperature"] is not None:
            request["temperature"] = kwargs["temperature"]

        if "top_p" in kwargs and kwargs["top_p"] is not None:
            request["top_p"] = kwargs["top_p"]

        return request

    def make_request(self, request_data: dict, api_key: str) -> dict:
        """Make request to Anthropic API."""
        url = f"{self.base_url}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
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
                try:
                    error_data = response.json()
                    error_msg = str(error_data.get("error", response.text))
                except:
                    error_msg = response.text

                raise Exception(
                    f"Anthropic API error {response.status_code}: {error_msg}"
                )

            return response.json()
        except requests.exceptions.Timeout:
            raise Exception(f"Anthropic API timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"Anthropic API connection error: {e}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Anthropic API request error: {e}")

    def translate_response(self, response_data: dict) -> dict:
        """Convert Anthropic response to OpenAI format."""
        # Extract text from Anthropic's content blocks
        text_content = ""
        if "content" in response_data:
            for block in response_data["content"]:
                if block.get("type") == "text":
                    text_content = block.get("text", "")
                    break

        # Map to OpenAI format
        return {
            "id": f"chatcmpl-{response_data.get('id', 'unknown')[:8]}",
            "object": "chat.completion",
            "created": int(__import__('time').time()),
            "model": response_data.get("model", "claude"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": text_content
                    },
                    "finish_reason": response_data.get("stop_reason", "stop")
                }
            ],
            "usage": {
                "prompt_tokens": response_data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": response_data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": (
                    response_data.get("usage", {}).get("input_tokens", 0) +
                    response_data.get("usage", {}).get("output_tokens", 0)
                )
            }
        }