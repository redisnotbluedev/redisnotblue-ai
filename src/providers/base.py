from abc import ABC, abstractmethod


class Provider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    @abstractmethod
    def translate_request(self, messages: list[dict], model_id: str, **kwargs) -> dict:
        """Convert OpenAI format request to provider's native format."""
        pass

    @abstractmethod
    def make_request(self, request_data: dict, api_key: str) -> dict:
        """Make the actual API request to the provider."""
        pass

    @abstractmethod
    def translate_response(self, response_data: dict) -> dict:
        """Convert provider's response to OpenAI format."""
        pass

    def chat_completion(self, messages: list[dict], model_id: str, api_key: str, **kwargs) -> dict:
        """Main entry point for chat completion requests."""
        request_data = self.translate_request(messages, model_id, **kwargs)
        response_data = self.make_request(request_data, api_key)
        return self.translate_response(response_data)