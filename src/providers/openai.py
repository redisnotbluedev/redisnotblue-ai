"""OpenAI provider implementation with enhanced flexibility."""

import requests
import uuid
import time
from typing import Dict, Any, List
from .base import Provider, ValidationError, TransformedRequest, TransformedResponse


class OpenAIProvider(Provider):
	"""Provider for OpenAI-compatible APIs."""

	def __init__(self, name: str, config: dict):
		super().__init__(name, config)
		self.base_url = config.get("base_url", "https://api.openai.com/v1")
		self.timeout = config.get("timeout", 60)
		self.model_mapping = config.get("model_mapping", {})
		self.default_params = config.get("defaults", {})

	def validate_request(
		self, messages: list[dict], model_id: str, **kwargs
	) -> List[ValidationError]:
		"""Validate OpenAI-format requests."""
		errors = []

		# Check messages
		if not messages:
			errors.append(ValidationError(
				field="messages",
				message="Messages cannot be empty",
				code="EMPTY_MESSAGES"
			))
		else:
			for i, msg in enumerate(messages):
				if not isinstance(msg, dict):
					errors.append(ValidationError(
						field=f"messages[{i}]",
						message="Message must be a dictionary",
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

		# Check model_id
		if not model_id:
			errors.append(ValidationError(
				field="model_id",
				message="Model ID is required",
				code="MISSING_MODEL_ID"
			))

		# Validate parameter types if provided
		if "temperature" in kwargs and kwargs["temperature"] is not None:
			if not isinstance(kwargs["temperature"], (int, float)):
				errors.append(ValidationError(
					field="temperature",
					message="Temperature must be a number",
					code="INVALID_TEMPERATURE"
				))
			elif not 0 <= kwargs["temperature"] <= 2:
				errors.append(ValidationError(
					field="temperature",
					message="Temperature must be between 0 and 2",
					code="TEMPERATURE_OUT_OF_RANGE"
				))

		if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
			if not isinstance(kwargs["max_tokens"], int):
				errors.append(ValidationError(
					field="max_tokens",
					message="max_tokens must be an integer",
					code="INVALID_MAX_TOKENS"
				))
			elif kwargs["max_tokens"] <= 0:
				errors.append(ValidationError(
					field="max_tokens",
					message="max_tokens must be positive",
					code="INVALID_MAX_TOKENS"
				))

		if "max_completion_tokens" in kwargs and kwargs["max_completion_tokens"] is not None:
			if not isinstance(kwargs["max_completion_tokens"], int):
				errors.append(ValidationError(
					field="max_completion_tokens",
					message="max_completion_tokens must be an integer",
					code="INVALID_MAX_COMPLETION_TOKENS"
				))
			elif kwargs["max_completion_tokens"] <= 0:
				errors.append(ValidationError(
					field="max_completion_tokens",
					message="max_completion_tokens must be positive",
					code="INVALID_MAX_COMPLETION_TOKENS"
				))

		if "top_p" in kwargs and kwargs["top_p"] is not None:
			if not isinstance(kwargs["top_p"], (int, float)):
				errors.append(ValidationError(
					field="top_p",
					message="top_p must be a number",
					code="INVALID_TOP_P"
				))
			elif not 0 < kwargs["top_p"] <= 1:
				errors.append(ValidationError(
					field="top_p",
					message="top_p must be between 0 and 1 (exclusive on 0)",
					code="TOP_P_OUT_OF_RANGE"
				))

		return errors

	def prefill_request(
		self, messages: list[dict], model_id: str, **kwargs
	) -> Dict[str, Any]:
		"""Provide OpenAI defaults."""
		prefilled = {}

		# Set reasonable defaults if not provided
		if "temperature" not in kwargs or kwargs["temperature"] is None:
			prefilled["temperature"] = 0.7

		if "top_p" not in kwargs or kwargs["top_p"] is None:
			prefilled["top_p"] = 1.0

		# Add provider-specific defaults
		for key, value in self.default_params.items():
			if key not in kwargs or kwargs[key] is None:
				prefilled[key] = value

		return prefilled

	def map_model_id(self, model_id: str) -> str:
		"""Map OpenAI model ID to provider's native model ID."""
		return self.model_mapping.get(model_id, model_id)

	def translate_model_id_in_response(
		self, provider_model_id: str, original_model_id: str
	) -> str:
		"""Translate model ID back to original format in response."""
		# Create reverse mapping
		reverse_mapping = {v: k for k, v in self.model_mapping.items()}
		return reverse_mapping.get(provider_model_id, original_model_id)

	def translate_request(
		self, messages: list[dict], model_id: str, **kwargs
	) -> TransformedRequest:
		"""Convert OpenAI format to OpenAI-compatible format."""
		request = {
			"model": model_id,
			"messages": messages,
		}

		# Handle temperature
		if "temperature" in kwargs and kwargs["temperature"] is not None:
			request["temperature"] = kwargs["temperature"]

		# Handle max_tokens (supports both max_tokens and max_completion_tokens)
		max_tokens = kwargs.get("max_tokens") or kwargs.get("max_completion_tokens")
		if max_tokens is not None:
			request["max_tokens"] = max_tokens

		# Handle top_p
		if "top_p" in kwargs and kwargs["top_p"] is not None:
			request["top_p"] = kwargs["top_p"]

		# Handle stop sequences
		if "stop" in kwargs and kwargs["stop"] is not None:
			request["stop"] = kwargs["stop"]

		# Track which fields were prefilled vs explicitly set
		prefilled_fields = {}
		for key in ["temperature", "top_p", "max_tokens"]:
			if key not in kwargs or kwargs[key] is None:
				if key in request:
					prefilled_fields[key] = "from_defaults"

		return TransformedRequest(
			data=request,
			original_model_id=model_id,
			provider_model_id=model_id,
			prefilled_fields=prefilled_fields,
			route_info={
				"endpoint": f"{self.base_url}/chat/completions",
				"request_type": "chat_completion",
			}
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
		original_model_id: str = None,
		provider_model_id: str = None,
	) -> TransformedResponse:
		"""Convert provider's response to OpenAI format."""
		response = dict(response_data)

		# Ensure response has required fields
		if "id" not in response:
			response["id"] = f"chatcmpl-{uuid.uuid4().hex[:24]}"

		if "object" not in response:
			response["object"] = "chat.completion"

		if "created" not in response:
			response["created"] = int(time.time())

		if "model" not in response:
			response["model"] = provider_model_id or "unknown"

		# Ensure usage stats exist
		if "usage" not in response:
			response["usage"] = {
				"prompt_tokens": 0,
				"completion_tokens": 0,
				"total_tokens": 0,
			}

		# Ensure choices exist
		if "choices" not in response:
			response["choices"] = []
		else:
			# Ensure finish_reason in each choice
			for choice in response["choices"]:
				if "finish_reason" not in choice:
					choice["finish_reason"] = "stop"

		return TransformedResponse(
			data=response,
			provider_name=self.name,
			model_id=original_model_id or provider_model_id,
			provider_model_id=provider_model_id,
			route_info={
				"model_in_response": response.get("model"),
				"response_type": "chat_completion",
			}
		)