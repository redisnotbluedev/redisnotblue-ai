import requests
import time
import uuid
from typing import List, Dict, Any
from .base import Provider, TransformedRequest, TransformedResponse


class SixFingerProvider(Provider):
    """
    Provider implementation for SixFinger API.
    API Endpoint: https://sfapi.pythonanywhere.com/api/v1/chat
    """

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.base_url = config.get("base_url", "https://sfapi.pythonanywhere.com/api/v1/chat")
        self.timeout = config.get("timeout", 60)

    def translate_request(
        self, messages: List[dict], model_id: str, **kwargs
    ) -> TransformedRequest:
        """
        Convert OpenAI format to SixFinger format.
        SixFinger expects 'message', 'model', 'system_prompt', 'history', etc.
        """
        system_prompt = None
        filtered_messages = []

        # Extract system prompt and filter non-system messages
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content")
            else:
                filtered_messages.append(msg)

        # The last message is the primary 'message' for SixFinger
        if not filtered_messages:
            user_message = ""
            history = []
        else:
            user_message = filtered_messages[-1].get("content", "")
            history = filtered_messages[:-1]

        # Map OpenAI-style parameters to SixFinger parameters
        data = {
            "message": user_message,
            "model": model_id or "auto",
            "system_prompt": system_prompt,
            "history": history,
            "stream": False,  # App level handles streaming via aggregation/simulation
            "max_tokens": kwargs.get("max_tokens", 300),
            "temperature": kwargs.get("temperature", 0.7),
            "top_p": kwargs.get("top_p", 0.9),
        }

        # Remove None values to use API defaults
        data = {k: v for k, v in data.items() if v is not None}

        return TransformedRequest(
            data=data,
            original_model_id=model_id,
            provider_model_id=model_id,
        )

    def make_request(self, request_data: dict, api_key: str) -> dict:
        """Execute the POST request to SixFinger API."""
        headers = {
            "Content-Type": "application/json",
        }
        
        # If an API key is provided, assume it's a Bearer token
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = requests.post(
                self.base_url,
                json=request_data,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                raise Exception(
                    f"SixFinger API error {response.status_code}: {response.text}"
                )
                
            return response.json()
        except requests.exceptions.Timeout:
            raise Exception(f"SixFinger API timeout after {self.timeout}s")
        except requests.exceptions.RequestException as e:
            raise Exception(f"SixFinger API request failed: {e}")

    def translate_response(
        self, response_data: dict, original_model_id: str
    ) -> TransformedResponse:
        """Convert SixFinger response to OpenAI format."""
        content = response_data.get("response", "")
        usage = response_data.get("usage", {})
        
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        translated = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": original_model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            },
            "provider": self.name
        }

        return TransformedResponse(
            data=translated,
            provider_name=self.name
        )