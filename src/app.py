"""FastAPI application for the OpenAI-compatible proxy server."""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Union
from dotenv import load_dotenv
from pathlib import Path

from .registry import ModelRegistry
from .metrics import GlobalMetrics
import json as json_module

load_dotenv()

registry: Optional[ModelRegistry] = None
global_metrics: Optional[GlobalMetrics] = None


def on_metrics_change():
	"""Callback when metrics change - save to disk immediately."""
	try:
		if registry:
			registry.save_metrics()
		if global_metrics:
			registry.metrics.save_global_metrics(global_metrics)
	except Exception as e:
		print(f"Error saving metrics on change: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Manage application lifespan events."""
	global registry, global_metrics
	try:
		# Startup
		registry = ModelRegistry()
		global_metrics = GlobalMetrics(on_change=on_metrics_change)
		config_path = os.getenv("CONFIG_PATH", "config/config.yaml")
		print(f"Loading config from: {config_path}")
		registry.load_from_config(config_path)

		# Load persisted global metrics
		persisted_global = registry.metrics.load_global_metrics()
		if persisted_global:
			global_metrics.from_dict(persisted_global)

		print("Registry initialized successfully")
	except Exception as e:
		print(f"Error initializing registry: {e}")
		import traceback
		traceback.print_exc()
		raise
	yield
	# Final save on shutdown
	if registry:
		registry.save_metrics()
		print("Metrics saved")
	if global_metrics:
		registry.metrics.save_global_metrics(global_metrics)
		print("Global metrics saved")


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


async def _stream_response(response: dict):
	"""Convert a complete response to SSE streaming format."""
	choices = response.get("choices", [])
	if not choices:
		return

	content = choices[0].get("message", {}).get("content", "")
	finish_reason = choices[0].get("finish_reason", "stop")

	# Stream tokens one by one
	for char in content:
		chunk = {
			"id": response.get("id"),
			"object": "chat.completion.chunk",
			"created": response.get("created"),
			"model": response.get("model"),
			"choices": [
				{
					"index": 0,
					"delta": {"content": char},
					"finish_reason": None
				}
			]
		}
		yield f"data: {json_module.dumps(chunk)}\n\n"
		await asyncio.sleep(0)

	# Send final chunk
	final_chunk = {
		"id": response.get("id"),
		"object": "chat.completion.chunk",
		"created": response.get("created"),
		"model": response.get("model"),
		"choices": [
			{
				"index": 0,
				"delta": {},
				"finish_reason": finish_reason
			}
		]
	}
	yield f"data: {json_module.dumps(final_chunk)}\n\n"
	yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
	if registry is None:
		raise HTTPException(status_code=500, detail="Registry not initialized")

	model = registry.get_model(request.model)
	if not model:
		raise HTTPException(status_code=404, detail=f"Model not found: {request.model}")

	messages = [msg.model_dump() for msg in request.messages]

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

	# Prioritize: providers with no data first, then by health score
	no_data_providers = [p for p in available_providers if len(p.speed_tracker.response_times) == 0]
	has_data_providers = [p for p in available_providers if len(p.speed_tracker.response_times) > 0]

	# Try no-data providers first, then data providers
	providers_to_try = no_data_providers + has_data_providers

	last_error = None
	validation_errors = None

	# Try all available providers until success or exhaustion
	for provider_instance in providers_to_try:
		provider_instance.reset_retry_count()

		while provider_instance.should_retry_request():
			api_key = None
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

				# Extract token counts and TTFT
				input_tokens = response.get("usage", {}).get("prompt_tokens", 0)
				output_tokens = response.get("usage", {}).get("completion_tokens", 0)
				total_tokens = input_tokens + output_tokens
				ttft = response.get("ttft", 0.0)

				# Calculate TTFT relative to start if it's an absolute timestamp
				if ttft and isinstance(ttft, (int, float)):
					# If TTFT is a large timestamp, subtract start_time to get duration
					if ttft > 1000000000:
						ttft = max(0.0, ttft - start_time)

				# Calculate credits based on tracker configuration (if needed)
				# Note: Credits are auto-calculated in RateLimitTracker based on token counts
				# Pass 0 here - the tracker will calculate from tokens and configured rates
				credits = 0.0

				# Record metrics (multipliers handled in RateLimitTracker.add_request)
				provider_instance.record_response(
					duration=duration,
					tokens=total_tokens,
					api_key=api_key,
					prompt_tokens=input_tokens,
					completion_tokens=output_tokens,
					credits=credits,
					ttft=ttft
				)
				provider_instance.mark_api_key_success(api_key)
				provider_instance.mark_success()

				# Record global metrics
				if global_metrics:
					global_metrics.record_request(
						duration=duration,
						tokens=total_tokens,
						prompt_tokens=input_tokens,
						completion_tokens=output_tokens,
						credits=credits,
						ttft=ttft
					)

				# Return response (streaming or non-streaming based on request)
				if request.stream:
					return StreamingResponse(
						_stream_response(response),
						media_type="text/event-stream"
					)
				else:
					return response

			except ValueError as e:
				# Validation error - save it and continue to next provider
				validation_errors = str(e)
				last_error = validation_errors
				provider_instance.mark_failure()
				provider_instance.increment_retry_count()
				if global_metrics:
					global_metrics.record_error()

			except Exception as e:
				last_error = str(e)

				if api_key:
					provider_instance.mark_api_key_failure(api_key)

				provider_instance.mark_failure()
				provider_instance.increment_retry_count()
				if global_metrics:
					global_metrics.record_error()

				if not provider_instance.should_retry_request():
					break

	# Determine which error to return
	if validation_errors:
		error_detail = f"Request validation failed: {validation_errors}"
		raise HTTPException(status_code=400, detail=error_detail)

	error_detail = (
		f"All providers failed for model {request.model}. Last error: {last_error}"
		if last_error
		else f"All providers failed for model {request.model}."
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
			# Add extra metrics for dashboard display
			provider_stat["tokens_per_second"] = pi.speed_tracker.get_tokens_per_second()
			provider_stat["average_ttft"] = provider_stat.get("avg_ttft", 0)

			if pi.api_key_rotation:
				provider_stat["api_keys"] = pi.api_key_rotation.get_status()
			model_stats["providers"].append(provider_stat)

		stats[model.id] = model_stats

	return stats


@app.get("/v1/health")
async def health_check():
	"""Get comprehensive health and statistics."""
	if registry is None:
		return {
			"status": "error",
			"detail": "Registry not initialized"
		}

	models = registry.list_models()

	# Calculate aggregate provider statistics
	unique_providers = set()
	total_provider_instances = 0
	total_enabled_providers = 0
	health_scores = []

	for model in models:
		for pi in model.provider_instances:
			total_provider_instances += 1
			unique_providers.add(pi.provider.name)

			if pi.enabled:
				total_enabled_providers += 1

			health_scores.append(pi.get_health_score())

	# Calculate average provider health
	avg_health_score = sum(health_scores) / len(health_scores) if health_scores else 0.0

	# Calculate average providers per model
	avg_providers_per_model = total_provider_instances / len(models) if models else 0.0

	# Prepare global statistics
	global_stats = {}
	if global_metrics:
		global_stats = {
			"total_requests": global_metrics.total_requests,
			"total_tokens": global_metrics.total_tokens,
			"total_prompt_tokens": global_metrics.total_prompt_tokens,
			"total_completion_tokens": global_metrics.total_completion_tokens,
			"total_errors": global_metrics.errors_count,
			"error_rate_percent": (global_metrics.errors_count / global_metrics.total_requests * 100) if global_metrics.total_requests > 0 else 0.0,
			"total_credits_used": global_metrics.total_credits_used,
			"uptime_seconds": global_metrics.get_uptime_seconds(),
			"avg_response_time_ms": global_metrics.get_average_response_time() * 1000,
			"p95_response_time_ms": global_metrics.get_p95_response_time() * 1000,
			"avg_ttft_ms": global_metrics.get_average_ttft() * 1000,
			"p95_ttft_ms": global_metrics.get_p95_ttft() * 1000,
			"tokens_per_second": global_metrics.total_completion_tokens / global_metrics.get_uptime_seconds() if global_metrics.get_uptime_seconds() > 0 else 0.0,
		}

	# Determine overall system status
	if not models or len(unique_providers) == 0:
		system_status = "degraded"
	elif total_enabled_providers == 0:
		system_status = "down"
	elif avg_health_score >= 80:
		system_status = "healthy"
	elif avg_health_score >= 50:
		system_status = "degraded"
	else:
		system_status = "unhealthy"

	return {
		"status": system_status,
		"registry_initialized": True,
		"timestamp": int(time.time()),
		"global_stats": global_stats,
		"provider_summary": {
			"total_providers": len(unique_providers),
			"total_provider_instances": total_provider_instances,
			"enabled_provider_instances": total_enabled_providers,
			"disabled_provider_instances": total_provider_instances - total_enabled_providers,
			"avg_provider_health_score": round(avg_health_score, 2),
			"avg_providers_per_model": round(avg_providers_per_model, 2),
		},
	}


# Mount static files for dashboard AFTER all API routes
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
	app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
