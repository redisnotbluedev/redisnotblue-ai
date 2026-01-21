"""FastAPI application for the OpenAI-compatible proxy server."""

import asyncio
import time
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Union

from registry import ModelRegistry
from models import Message

registry: Optional[ModelRegistry] = None


class ChatMessage(BaseModel):
	role: str
	content: str


class ChatCompletionRequest(BaseModel):
	model: str
	messages: list[ChatMessage]
	temperature: Optional[float] = None
	max_tokens: Optional[int] = None
	max_completion_tokens: Optional[int] = None
	top_p: Optional[float] = None
	stop: Optional[Union[str, list[str]]] = None
	stream: bool = False


class ChatMessage_Response(BaseModel):
	role: str
	content: str


class Choice(BaseModel):
	index: int
	message: ChatMessage_Response
	finish_reason: str


class Usage(BaseModel):
	prompt_tokens: int
	completion_tokens: int
	total_tokens: int


class ChatCompletionResponse(BaseModel):
	id: str
	object: str
	created: int
	model: str
	choices: list[Choice]
	usage: Usage


class ModelInfo(BaseModel):
	id: str
	object: str
	created: int
	owned_by: str


class ModelListResponse(BaseModel):
	object: str
	data: list[ModelInfo]


app = FastAPI(title="OpenAI Proxy")


@app.on_event("startup")
async def startup_event():
	global registry
	registry = ModelRegistry()
	registry.load_from_config("config/config.yaml")


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
	if registry is None:
		raise HTTPException(status_code=500, detail="Registry not initialized")

	model = registry.get_model(request.model)
	if not model:
		raise HTTPException(status_code=404, detail=f"Model not found: {request.model}")

	messages = [msg.dict() for msg in request.messages]

	kwargs = {}
	if request.temperature is not None:
		kwargs["temperature"] = request.temperature
	if request.max_tokens is not None:
		kwargs["max_tokens"] = request.max_tokens
	if request.max_completion_tokens is not None:
		kwargs["max_completion_tokens"] = request.max_completion_tokens
	if request.top_p is not None:
		kwargs["top_p"] = request.top_p
	if request.stop is not None:
		kwargs["stop"] = request.stop

	available_providers = model.get_available_providers()

	if not available_providers:
		raise HTTPException(status_code=503, detail="No available providers for this model")

	last_error = None

	for provider_instance in available_providers:
		provider_instance.reset_retry_count()

		while provider_instance.should_retry_request():
			try:
				api_key = provider_instance.get_current_api_key()

				if not api_key:
					last_error = "No API keys available"
					break

				# Apply exponential backoff before retry
				if provider_instance.retry_count > 0:
					delay = provider_instance.get_backoff_delay()
					await asyncio.sleep(delay)

				# Make request and time it
				start_time = time.time()

				response = provider_instance.provider.chat_completion(
					messages=messages,
					model_id=provider_instance.model_id,
					api_key=api_key,
					**kwargs,
				)

				duration = time.time() - start_time

				# Extract token counts
				input_tokens = response.get("usage", {}).get("prompt_tokens", 0)
				output_tokens = response.get("usage", {}).get("completion_tokens", 0)
				total_tokens = input_tokens + output_tokens

				# Record metrics
				provider_instance.record_response(duration, total_tokens, api_key)
				provider_instance.mark_api_key_success(api_key)
				provider_instance.mark_success()

				# Ensure response has required fields
				if "id" not in response:
					response["id"] = f"chatcmpl-{uuid.uuid4().hex[:24]}"
				if "created" not in response:
					response["created"] = int(time.time())

				return ChatCompletionResponse(**response)

			except Exception as e:
				last_error = str(e)

				if api_key:
					provider_instance.mark_api_key_failure(api_key)

				provider_instance.mark_failure()
				provider_instance.increment_retry_count()

				if not provider_instance.should_retry_request():
					break

	error_detail = (
		f"All providers failed. Last error: {last_error}"
		if last_error
		else "All providers failed"
	)
	raise HTTPException(status_code=503, detail=error_detail)


@app.get("/v1/models", response_model=ModelListResponse)
async def list_models():
	if registry is None:
		raise HTTPException(status_code=500, detail="Registry not initialized")

	models = registry.list_models()
	model_data = [ModelInfo(**model.to_dict()) for model in models]
	return ModelListResponse(object="list", data=model_data)


@app.get("/v1/providers/stats")
async def provider_stats():
	"""Get detailed statistics about provider performance."""
	if registry is None:
		raise HTTPException(status_code=500, detail="Registry not initialized")

	stats = {}
	for model in registry.list_models():
		model_stats = {
			"model_id": model.id,
			"providers": []
		}

		for pi in model.provider_instances:
			provider_stat = pi.get_stats()
			if pi.api_key_rotation:
				provider_stat["api_keys"] = pi.api_key_rotation.get_status()
			model_stats["providers"].append(provider_stat)

		stats[model.id] = model_stats

	return stats


@app.get("/health")
async def health_check():
	return {"status": "ok"}