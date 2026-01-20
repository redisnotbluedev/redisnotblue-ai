"""OpenAI provider implementation."""

import requests
from .base import Provider


class OpenAIProvider(Provider):
	"""Provider for OpenAI's API."""

	def __init__(self, name: str, config: dict):
		super().__init__(name, config)
		self.base_url = config.get("base_url", "https://api.openai.com/v1")
		self.timeout = config.get("timeout", 60)

	def translate_request(
		self, messages: list[dict], model_id: str, **kwargs
	) -> dict:
		"""Convert OpenAI format to OpenAI format (pass-through)."""
		request = {
			"model": model_id,
			"messages": messages,
		}

		if "temperature" in kwargs and kwargs["temperature"] is not None:
			request["temperature"] = kwargs["temperature"]

		max_tokens = kwargs.get("max_tokens") or kwargs.get("max_completion_tokens")
		if max_tokens is not None:
			request["max_tokens"] = max_tokens

		if "top_p" in kwargs and kwargs["top_p"] is not None:
			request["top_p"] = kwargs["top_p"]

		if "stop" in kwargs and kwargs["stop"] is not None:
			request["stop"] = kwargs["stop"]

		return request

	def make_request(self, request_data: dict, api_key: str) -> dict:
		"""Make request to OpenAI API."""
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
		"""OpenAI response is already in the correct format."""
		return response_data