from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class ValidationError:
	"""Represents a validation error with details."""
	field: str
	message: str
	code: Optional[str] = None


@dataclass
class ValidationResult:
	"""Result of request validation."""
	is_valid: bool
	errors: List[ValidationError] = field(default_factory=list)


@dataclass
class TransformedRequest:
	"""Request after transformation with metadata."""
	data: dict
	original_model_id: str
	provider_model_id: str
	prefilled_fields: Dict[str, Any] = field(default_factory=dict)
	route_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransformedResponse:
	"""Response after transformation with metadata."""
	data: dict
	provider_name: str
	model_id: str
	provider_model_id: str
	route_info: Dict[str, Any] = field(default_factory=dict)


class Provider(ABC):
	"""Abstract base class for LLM providers with enhanced flexibility."""

	def __init__(self, name: str, config: dict):
		self.name = name
		self.config = config

	def validate_request(
		self,
		messages: list[dict],
		model_id: str,
		**kwargs
	) -> ValidationResult:
		"""
		Validate request data before sending to provider.
		Can be overridden by subclasses to implement custom validation.

		Args:
			messages: List of message dicts
			model_id: The model ID requested
			**kwargs: Additional parameters

		Returns:
			ValidationResult with any validation errors
		"""
		errors = []

		# Basic validation
		if not messages:
			errors.append(ValidationError(
				field="messages",
				message="Messages list cannot be empty",
				code="EMPTY_MESSAGES"
			))

		if not model_id:
			errors.append(ValidationError(
				field="model_id",
				message="Model ID is required",
				code="MISSING_MODEL_ID"
			))

		# Validate message structure
		for i, msg in enumerate(messages):
			if not isinstance(msg, dict):
				errors.append(ValidationError(
					field=f"messages[{i}]",
					message="Message must be a dict",
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

		return ValidationResult(
			is_valid=len(errors) == 0,
			errors=errors
		)

	def prefill_request(
		self,
		messages: list[dict],
		model_id: str,
		**kwargs
	) -> Dict[str, Any]:
		"""
		Provide prefilled/default values for the request.
		Subclasses can override to add provider-specific defaults.

		Args:
			messages: List of message dicts
			model_id: The model ID requested
			**kwargs: Additional parameters

		Returns:
			Dict of prefilled values (merged with provided kwargs)
		"""
		return {}

	def map_model_id(self, model_id: str) -> str:
		"""
		Map the standardized model ID to provider's native model ID.

		Args:
			model_id: The model ID to map

		Returns:
			The provider's native model ID
		"""
		return model_id

	def translate_model_id_in_response(
		self,
		provider_model_id: str,
		original_model_id: str
	) -> str:
		"""
		Translate provider's model ID back to original format in response.

		Args:
			provider_model_id: The provider's native model ID
			original_model_id: The original model ID from the request

		Returns:
			The model ID to include in the response
		"""
		return original_model_id

	@abstractmethod
	def translate_request(
		self,
		messages: list[dict],
		model_id: str,
		**kwargs
	) -> TransformedRequest:
		"""
		Convert OpenAI format request to provider's native format.
		Now returns TransformedRequest with metadata.

		Args:
			messages: List of message dicts
			model_id: The provider's model ID (already mapped)
			**kwargs: Additional parameters

		Returns:
			TransformedRequest with data, model IDs, and metadata
		"""
		pass

	@abstractmethod
	def make_request(self, request_data: dict, api_key: str) -> dict:
		"""
		Make the actual API request to the provider.

		Args:
			request_data: Request data prepared by translate_request
			api_key: API key for authentication

		Returns:
			dict: Raw response from the provider
		"""
		pass

	@abstractmethod
	def translate_response(
		self,
		response_data: dict,
		original_model_id: str,
		provider_model_id: str,
	) -> TransformedResponse:
		"""
		Convert provider's response to OpenAI format.
		Now handles model ID translation and metadata.

		Args:
			response_data: The raw response from the provider
			original_model_id: The original model ID from the request
			provider_model_id: The provider's native model ID

		Returns:
			TransformedResponse with data and metadata
		"""
		pass

	def chat_completion(
		self,
		messages: list[dict],
		model_id: str,
		api_key: str,
		**kwargs
	) -> dict:
		"""
		Main entry point for chat completion requests.
		Handles validation, prefilling, transformation, and response translation.

		Args:
			messages: List of message dicts
			model_id: The model ID
			api_key: API key for authentication
			**kwargs: Additional parameters

		Returns:
			Response dict with routing information

		Raises:
			ValueError: If validation fails
			Exception: If request fails
		"""
		# Step 1: Validate request
		validation = self.validate_request(messages, model_id, **kwargs)
		if not validation.is_valid:
			error_details = [
				{
					"field": err.field,
					"message": err.message,
					"code": err.code
				}
				for err in validation.errors
			]
			raise ValueError(f"Request validation failed: {error_details}")

		# Step 2: Prefill defaults
		prefilled = self.prefill_request(messages, model_id, **kwargs)
		merged_kwargs = {**prefilled, **kwargs}

		# Step 3: Map model ID to provider's format
		original_model_id = model_id
		provider_model_id = self.map_model_id(model_id)

		# Step 4: Transform request
		transformed_request = self.translate_request(
			messages,
			provider_model_id,
			**merged_kwargs
		)

		# Step 5: Make request
		response_data = self.make_request(transformed_request.data, api_key)

		# Step 6: Transform response
		transformed_response = self.translate_response(
			response_data,
			original_model_id,
			provider_model_id
		)

		# Step 7: Translate model ID back to original format in response
		response = transformed_response.data
		if "model" in response:
			response["model"] = self.translate_model_id_in_response(
				response["model"],
				original_model_id
			)

		# Step 8: Add routing information
		response["_routing"] = {
			"provider": self.name,
			"provider_route": "/v1/chat/completions",
			"original_model_id": original_model_id,
			"provider_model_id": provider_model_id,
			**transformed_response.route_info
		}

		# Step 9: Add request data for debugging (optional)
		response["_request_data"] = transformed_request.data

		return response


__all__ = [
	"Provider",
	"ValidationError",
	"ValidationResult",
	"TransformedRequest",
	"TransformedResponse",
]