"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, name: str, config: dict):
        """Initialize the provider.
        
        Args:
            name: Name of the provider (e.g., "openai", "anthropic")
            config: Configuration dictionary for the provider
        """
        self.name = name
        self.config = config

    @abstractmethod
    def translate_request(self, messages: list[dict], model_id: str, **kwargs) -> dict:
        """Convert OpenAI format request to provider's native format.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model_id: The model ID as known by this provider
            **kwargs: Additional parameters like temperature, max_tokens, etc.
            
        Returns:
            Dict in the provider's native format
        """
        pass

    @abstractmethod
    def make_request(self, request_data: dict) -> dict:
        """Make the actual API request to the provider.
        
        Args:
            request_data: Request dict from translate_request
            
        Returns:
            Raw JSON response from the provider
            
        Raises:
            Exception: On any API error
        """
        pass

    @abstractmethod
    def translate_response(self, response_data: dict) -> dict:
        """Convert provider's response to OpenAI format.
        
        Args:
            response_data: Raw response from make_request
            
        Returns:
            Dict in OpenAI format
        """
        pass

    def chat_completion(self, messages: list[dict], model_id: str, **kwargs) -> dict:
        """Main entry point for chat completion requests.
        
        Args:
            messages: List of message dicts
            model_id: The model ID as known by this provider
            **kwargs: Additional parameters
            
        Returns:
            Response in OpenAI format
        """
        request_data = self.translate_request(messages, model_id, **kwargs)
        response_data = self.make_request(request_data)
        return self.translate_response(response_data)