"""OpenAI provider implementation - simple passthrough for OpenAI-compatible APIs."""

import requests
import uuid
import time
from .base import Provider, TransformedRequest, TransformedResponse


class OpenAIProvider(Provider):
	"""Provider for OpenAI-compatible APIs."""

	def __init__(self, name: str, config: dict):
		super().__init__(name, config)
		self.base_url = config.get("base_url", "https://api.openai.com/v1")
		self.timeout = config.get("timeout", 60)
		self.chat_completions_path = config.get("chat_completions_path", "/chat/completions") # Ollama uses /chat not /chat/completions, added for parity and further customisation

	def translate_request(
		self, messages: list[dict], model_id: str, **kwargs
	) -> TransformedRequest:
		"""Build OpenAI format request."""
		request = {
			"model": model_id,
			"messages": messages,
		}

		# Add optional parameters if provided
		for key in ["temperature", "top_p", "stop", "max_tokens"]:
			if key in kwargs and kwargs[key] is not None:
				request[key] = kwargs[key]

		return TransformedRequest(
			data=request,
			original_model_id=model_id,
			provider_model_id=model_id,
		)

	def make_request(self, request_data: dict, api_key: str) -> dict:
		"""Make request to OpenAI-compatible API."""
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
				except Exception:
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

	def translate_response(
		self,
		response_data: dict,
		original_request: dict,
	) -> TransformedResponse:
		"""Convert provider's response to OpenAI format."""
		usage = response_data.get("usage", {})
		prompt = usage.get("prompt_tokens")
		completion = usage.get("completion_tokens")

		response = {
			"id": f"chatcmpl-{uuid.uuid4()}",
			"object": "chat.completion",
			"created": int(time.time()),
			"model": original_request.get("model", "unknown"),
			"choices": response_data.get("choices", []),
			"usage": {
				"prompt_tokens": prompt,
				"completion_tokens": completion,
				"total_tokens": usage.get("total_tokens", (prompt or 0) + (completion or 0))
			},
			"provider": self.name
		}

		return TransformedResponse(
			data=response,
			provider_name=self.name,
			original_request=original_request,
		)
