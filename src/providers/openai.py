"""OpenAI provider implementation."""

import requests
import uuid
import time
from typing import Optional

from .base import Provider


class OpenAIProvider(Provider):
    """Provider for OpenAI's API."""

    def __init__(self, name: str, config: dict) -> None:
        """Initialize OpenAI provider.
        
        Args:
            name: Provider name
            config: Configuration dictionary
        """
        super().__init__(name, config)
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.timeout = config.get("timeout", 60)

    def translate_request(
        self, messages: list[dict], model_id: str, api_key: str, **kwargs
    ) -> dict:
        """Convert OpenAI format to OpenAI format (pass-through with processing).
        
        Args:
            messages: List of message dicts
            model_id: Model ID for OpenAI
            api_key: The API key to use for this request
            **kwargs: temperature, max_tokens, top_p, stop, etc.
            
        Returns:
            Request dict for OpenAI API
        """
        request = {
            "model": model_id,
            "messages": messages,
        }

        # Add optional parameters if provided
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            request["temperature"] = kwargs["temperature"]

        # Handle both max_tokens and max_completion_tokens
        max_tokens = kwargs.get("max_tokens") or kwargs.get("max_completion_tokens")
        if max_tokens is not None:
            request["max_tokens"] = max_tokens

        if "top_p" in kwargs and kwargs["top_p"] is not None:
            request["top_p"] = kwargs["top_p"]

        if "stop" in kwargs and kwargs["stop"] is not None:
            request["stop"] = kwargs["stop"]

        return request

    def make_request(self, request_data: dict, api_key: str) -> dict:
        """Make request to OpenAI API.
        
        Args:
            request_data: Request dict from translate_request
            api_key: The API key to use for this request
            
        Returns:
            Raw JSON response
            
        Raises:
            Exception: On API error
        """
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
                error_msg = response.text
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg = str(error_data["error"])
                except:
                    pass
                
                raise Exception(
                    f"OpenAI API error {response.status_code}: {error_msg}"
                )

            return response.json()
        except requests.exceptions.Timeout:
            raise Exception(f"OpenAI API timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"OpenAI API connection error: {e}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"OpenAI API request error: {e}")

    def translate_response(self, response_data: dict) -> dict:
        """OpenAI response is already in the right format, return as-is.
        
        Args:
            response_data: Raw response from OpenAI API
            
        Returns:
            Response in OpenAI format (pass-through)
        """
        # OpenAI responses are already in the right format
        return response_data

    def chat_completion(
        self, messages: list[dict], model_id: str, api_key: str, **kwargs
    ) -> dict:
        """Main entry point for chat completion requests.
        
        Args:
            messages: List of message dicts
            model_id: Provider-specific model identifier
            api_key: The API key to use for this request
            **kwargs: Additional parameters (temperature, max_tokens, etc.)
            
        Returns:
            Response in OpenAI format
            
        Raises:
            Exception: If any step fails
        """
        request_data = self.translate_request(messages, model_id, api_key, **kwargs)
        response_data = self.make_request(request_data, api_key)
        return self.translate_response(response_data)