"""FastAPI application for the OpenAI-compatible proxy server."""

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Union
from dotenv import load_dotenv
import signal

from .registry import ModelRegistry
from .models import Message

load_dotenv()

registry: Optional[ModelRegistry] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Manage application lifespan events."""
	global registry
	try:
		# Startup
		registry = ModelRegistry()
		config_path = os.getenv("CONFIG_PATH", "config/config.yaml")
		print(f"Loading config from: {config_path}")
		registry.load_from_config(config_path)
		print("Registry initialized successfully")
	except Exception as e:
		print(f"Error initializing registry: {e}")
		import traceback
		traceback.print_exc()
		raise
	yield
	# Shutdown - save metrics to disk
	if registry:
		registry.save_metrics()
		print("Metrics saved")


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
	provider: Optional[str] = None


class ModelInfo(BaseModel):
	id: str
	object: str
	created: int
	owned_by: str


class ModelListResponse(BaseModel):
	object: str
	data: list[ModelInfo]


app = FastAPI(title="OpenAI Proxy", lifespan=lifespan)


@app.post("/v1/chat/completions")
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
	validation_errors = None

	# Limit to 2 providers before failing
	for provider_instance in available_providers[:2]:
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
					model_id=provider_instance.get_next_model_id(),
					api_key=api_key,
					**kwargs,
				)

				duration = time.time() - start_time

				# Extract token counts
				input_tokens = response.get("usage", {}).get("prompt_tokens", 0)
				output_tokens = response.get("usage", {}).get("completion_tokens", 0)
				total_tokens = input_tokens + output_tokens

				# Record metrics (multipliers handled in RateLimitTracker.add_request)
				provider_instance.record_response(duration, total_tokens, api_key)
				provider_instance.mark_api_key_success(api_key)
				provider_instance.mark_success()

				# Ensure response has required fields
				if "id" not in response:
					response["id"] = f"chatcmpl-{uuid.uuid4().hex[:24]}"
				if "created" not in response:
					response["created"] = int(time.time())

				# Clean up internal metadata fields before returning
				response.pop("_metadata", None)

				return response

			except ValueError as e:
				# Validation error - save it and continue to next provider
				validation_errors = str(e)
				last_error = validation_errors
				provider_instance.mark_failure()
				provider_instance.increment_retry_count()

			except Exception as e:
				last_error = str(e)

				if api_key:
					provider_instance.mark_api_key_failure(api_key)

				provider_instance.mark_failure()
				provider_instance.increment_retry_count()

				if not provider_instance.should_retry_request():
					break

	# Determine which error to return
	if validation_errors:
		error_detail = f"Request validation failed: {validation_errors}"
		raise HTTPException(status_code=400, detail=error_detail)
	
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
	if registry is None:
		return {
			"status": "error",
			"detail": "Registry not initialized"
		}
	
	models = registry.list_models()
	providers_info = []
	
	for model in models:
		model_info = {
			"model_id": model.id,
			"providers": []
		}
		for pi in model.provider_instances:
			provider_info = {
				"name": pi.provider.name,
				"model_ids": pi.model_ids,
				"enabled": pi.enabled,
				"has_api_keys": pi.api_key_rotation is not None and len(pi.api_key_rotation.api_keys) > 0 if pi.api_key_rotation else False
			}
			if pi.api_key_rotation:
				provider_info["api_key_count"] = len(pi.api_key_rotation.api_keys)
			model_info["providers"].append(provider_info)
		providers_info.append(model_info)
	
	return {
		"status": "ok",
		"registry_initialized": True,
		"total_models": len(models),
		"total_providers": sum(len(m["providers"]) for m in providers_info),
		"models": providers_info
	}