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
	original_request: Dict[str, Any] = field(default_factory=dict)


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
			**kwargs: Additional parameters (tools, tool_choice, etc.)

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

			if "content" not in msg and "tool_calls" not in msg:
				errors.append(ValidationError(
					field=f"messages[{i}].content",
					message="Message content or tool_calls is required",
					code="MISSING_CONTENT"
				))

			# Validate content structure (can be string or list for multimodality)
			content = msg.get("content")
			if content is not None:
				if isinstance(content, list):
					# Validate multimodal content
					for j, block in enumerate(content):
						if not isinstance(block, dict) or "type" not in block:
							errors.append(ValidationError(
								field=f"messages[{i}].content[{j}]",
								message="Content block must be a dict with 'type' field",
								code="INVALID_CONTENT_BLOCK"
							))
				elif not isinstance(content, str):
					errors.append(ValidationError(
						field=f"messages[{i}].content",
						message="Content must be a string or list of content blocks",
						code="INVALID_CONTENT_TYPE"
					))

			# Validate tool calls if present
			tool_calls = msg.get("tool_calls")
			if tool_calls is not None:
				if not isinstance(tool_calls, list):
					errors.append(ValidationError(
						field=f"messages[{i}].tool_calls",
						message="Tool calls must be a list",
						code="INVALID_TOOL_CALLS"
					))
				else:
					for j, tool_call in enumerate(tool_calls):
						if not isinstance(tool_call, dict):
							errors.append(ValidationError(
								field=f"messages[{i}].tool_calls[{j}]",
								message="Tool call must be a dict",
								code="INVALID_TOOL_CALL"
							))

		# Validate tools parameter
		tools = kwargs.get("tools")
		if tools is not None:
			if not isinstance(tools, list):
				errors.append(ValidationError(
					field="tools",
					message="Tools must be a list",
					code="INVALID_TOOLS"
				))
			else:
				for i, tool in enumerate(tools):
					if not isinstance(tool, dict) or tool.get("type") != "function":
						errors.append(ValidationError(
							field=f"tools[{i}]",
							message="Tool must be a dict with type 'function'",
							code="INVALID_TOOL"
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
			**kwargs: Additional parameters (tools, tool_choice, etc.)

		Returns:
			Dict of prefilled values (merged with provided kwargs)
		"""
		prefilled = {}

		# Set common defaults that providers might want to override
		if "temperature" not in kwargs and kwargs.get("temperature") is None:
			prefilled["temperature"] = 0.7

		if "top_p" not in kwargs and kwargs.get("top_p") is None:
			prefilled["top_p"] = 1.0

		return prefilled

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
			messages: List of message dicts (may include multimodal content and tool calls)
			model_id: The provider's model ID (already mapped)
			**kwargs: Additional parameters (tools, tool_choice, frequency_penalty, etc.)

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
	) -> TransformedResponse:
		"""
		Convert provider's response to OpenAI format.

		Args:
			response_data: The raw response from the provider
			original_model_id: The canonical model ID requested by the client

		Returns:
			TransformedResponse with data and metadata
		"""
		pass

	def chat_completion(
		self,
		messages: list[dict],
		model_id: str,
		api_key: str,
		canonical_model_id: str = None,
		**kwargs
	) -> dict:
		"""
		Main entry point for chat completion requests.
		Handles validation, prefilling, transformation, and response translation.

		Args:
			messages: List of message dicts (may include multimodal content and tool calls)
			model_id: The model ID
			api_key: API key for authentication
			canonical_model_id: Original model ID from client
			**kwargs: Additional parameters (tools, tool_choice, frequency_penalty, etc.)

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

		# Save original request before any transformation
		original_request = {
			"messages": messages,
			"model": canonical_model_id or model_id,
			**merged_kwargs
		}

		# Step 3: Transform request
		transformed_request = self.translate_request(
			messages,
			model_id,
			**merged_kwargs
		)

		# Step 4: Make request
		response_data = self.make_request(transformed_request.data, api_key)

		# Step 5: Transform response
		transformed_response = self.translate_response(
			response_data,
			canonical_model_id or transformed_request.original_model_id
		)

		response = transformed_response.data
		return response


__all__ = [
	"Provider",
	"ValidationError",
	"ValidationResult",
	"TransformedRequest",
	"TransformedResponse",
]