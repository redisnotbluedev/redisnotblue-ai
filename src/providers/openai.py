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
						if "delta" in choice and "content" in choice["delta"]:
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
		original_request: dict,
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
			"model": original_request.get("model", "unknown"),
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
			original_request=original_request,
		)