"""OpenAI provider implementation."""

import uuid
import time
import requests
from typing import Optional
from .base import Provider


class OpenAIProvider(Provider):
    """OpenAI API provider implementation."""

    def __init__(self, name: str, config: dict) -> None:
        """Initialize OpenAI provider.
        
        Args:
            name: Provider name
            config: Must contain 'api_key', optionally 'base_url'
        """
        super().__init__(name, config)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        
        if not self.api_key:
            raise ValueError("OpenAI provider requires 'api_key' in config")

    def translate_request(
        self, messages: list[dict], model_id: str, **kwargs
    ) -> dict:
        """Convert to OpenAI format (already in OpenAI format, pass through).
        
        Args:
            messages: List of message dicts
            model_id: OpenAI model identifier
            **kwargs: temperature, max_tokens, top_p, stop, etc.
            
        Returns:
            Request dict for OpenAI API
        """
        request_data = {
            "model": model_id,
            "messages": messages,
        }
        
        # Add optional parameters if provided
        if "temperature" in kwargs:
            request_data["temperature"] = kwargs["temperature"]
        
        # Handle both max_tokens and max_completion_tokens
        if "max_completion_tokens" in kwargs:
            request_data["max_completion_tokens"] = kwargs["max_completion_tokens"]
        elif "max_tokens" in kwargs:
            request_data["max_tokens"] = kwargs["max_tokens"]
        
        if "top_p" in kwargs:
            request_data["top_p"] = kwargs["top_p"]
        
        if "stop" in kwargs:
            request_data["stop"] = kwargs["stop"]
        
        return request_data

    def make_request(self, request_data: dict) -> dict:
        """Make request to OpenAI API.
        
        Args:
            request_data: Request dict from translate_request
            
        Returns:
            Raw JSON response from OpenAI
            
        Raises:
            Exception: On API error
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        url = f"{self.base_url}/chat/completions"
        
        response = requests.post(
            url,
            json=request_data,
            headers=headers,
            timeout=60,
        )
        
        if response.status_code != 200:
            raise Exception(
                f"OpenAI API error {response.status_code}: {response.text}"
            )
        
        return response.json()

    def translate_response(self, response_data: dict) -> dict:
        """Convert OpenAI response to standard format (already in format, pass through).
        
        Args:
            response_data: Raw response from OpenAI
            
        Returns:
            Response in OpenAI format
        """
        return response_data