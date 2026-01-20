"""FastAPI application for the OpenAI proxy server."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Union
import uuid
import time

from registry import ModelRegistry
from models import Message

# Global registry
registry: Optional[ModelRegistry] = None


class ChatMessage(BaseModel):
    """Chat message for requests."""

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """Chat completion request."""

    model: str
    messages: list[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stop: Optional[Union[str, list[str]]] = None
    stream: bool = False


class ChatMessage_Response(BaseModel):
    """Chat message in response."""

    role: str
    content: str


class Choice(BaseModel):
    """Choice in chat completion response."""

    index: int
    message: ChatMessage_Response
    finish_reason: str


class Usage(BaseModel):
    """Token usage info."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """Chat completion response."""

    id: str
    object: str
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


class ModelInfo(BaseModel):
    """Model information."""

    id: str
    object: str
    created: int
    owned_by: str


class ModelListResponse(BaseModel):
    """Model list response."""

    object: str
    data: list[ModelInfo]


class ProviderStatus(BaseModel):
    """Provider status information."""

    model_id: str
    providers: list[dict]


app = FastAPI(title="OpenAI Proxy Server")


@app.on_event("startup")
async def startup_event() -> None:
    """Load configuration on startup."""
    global registry
    registry = ModelRegistry()
    registry.load_from_config("config/config.yaml")


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """Handle chat completion requests with round-robin API key retry logic."""
    if registry is None:
        raise HTTPException(status_code=500, detail="Registry not initialized")

    # Get the model
    model = registry.get_model(request.model)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model not found: {request.model}")

    # Convert request messages to dicts
    messages = [msg.dict() for msg in request.messages]

    # Build kwargs for provider
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

    # Try each available provider with retry logic
    available_providers = model.get_available_providers()

    if not available_providers:
        raise HTTPException(
            status_code=503,
            detail="No available providers for this model",
        )

    last_error = None
    
    for provider_instance in available_providers:
        # Reset retry counter for this provider
        provider_instance.reset_retry_count()
        
        while provider_instance.should_retry_request():
            try:
                # Get next API key (round-robin)
                api_key = provider_instance.get_current_api_key()
                
                if not api_key:
                    last_error = "No API keys available"
                    break
                
                # Make the request
                response = provider_instance.provider.chat_completion(
                    messages=messages,
                    model_id=provider_instance.model_id,
                    api_key=api_key,
                    **kwargs,
                )
                
                # Mark success on both API key and provider
                provider_instance.mark_api_key_success(api_key)
                provider_instance.mark_success()
                
                # Return response with generated ID and timestamp
                if "id" not in response:
                    response["id"] = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                if "created" not in response:
                    response["created"] = int(time.time())
                
                return ChatCompletionResponse(**response)

            except Exception as e:
                last_error = str(e)
                
                # Mark failure on API key
                if api_key:
                    provider_instance.mark_api_key_failure(api_key)
                
                provider_instance.increment_retry_count()
                
                # If we have more retries left, try next API key
                if provider_instance.should_retry_request():
                    continue
                else:
                    break
        
        # Provider exhausted, try next provider
        provider_instance.mark_failure()

    # All providers and keys failed
    error_detail = (
        f"All providers and API keys failed. Last error: {last_error}"
        if last_error
        else "All providers and API keys failed"
    )
    raise HTTPException(status_code=503, detail=error_detail)


@app.get("/v1/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """Handle model list requests."""
    if registry is None:
        raise HTTPException(status_code=500, detail="Registry not initialized")

    models = registry.list_models()
    model_data = [ModelInfo(**model.to_dict()) for model in models]
    return ModelListResponse(object="list", data=model_data)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/v1/providers/status")
async def provider_status(model_id: Optional[str] = None) -> dict:
    """Get status of all providers and their API keys."""
    if registry is None:
        raise HTTPException(status_code=500, detail="Registry not initialized")

    if model_id:
        model = registry.get_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")
        
        return registry.get_provider_status(model_id)
    else:
        # Return status for all models
        all_status = {}
        for model in registry.list_models():
            all_status[model.id] = registry.get_provider_status(model.id)
        return all_status


@app.get("/v1/providers/stats")
async def provider_stats() -> dict:
    """Get statistics about provider performance."""
    if registry is None:
        raise HTTPException(status_code=500, detail="Registry not initialized")

    stats = {}
    
    for model in registry.list_models():
        model_stats = {
            "model_id": model.id,
            "providers": []
        }
        
        for pi in model.provider_instances:
            provider_stats = {
                "provider_name": pi.provider.name,
                "priority": pi.priority,
                "model_id": pi.model_id,
                "enabled": pi.enabled,
                "consecutive_failures": pi.consecutive_failures,
                "last_failure": pi.last_failure,
            }
            
            if pi.api_key_rotation:
                key_stats = pi.api_key_rotation.get_status()
                provider_stats["api_keys"] = key_stats
            
            model_stats["providers"].append(provider_stats)
        
        stats[model.id] = model_stats
    
    return stats