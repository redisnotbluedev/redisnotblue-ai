"""FastAPI application for the LLM provider proxy."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Union, List
import uuid
import time
import os

from registry import ModelRegistry
from models import Message

# Initialize FastAPI app
app = FastAPI(title="LLM Provider Proxy", version="1.0.0")

# Global registry
registry: Optional[ModelRegistry] = None


# Pydantic models for request/response validation
class MessageRequest(BaseModel):
    """Message in a chat completion request."""
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """Chat completion request matching OpenAI format."""
    model: str
    messages: List[MessageRequest]
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    top_p: Optional[float] = 1.0
    stop: Optional[Union[str, List[str]]] = None
    stream: Optional[bool] = False


class ModelInfo(BaseModel):
    """Model information in list response."""
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ListModelsResponse(BaseModel):
    """Response for GET /v1/models."""
    object: str = "list"
    data: List[ModelInfo]


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize the registry on startup."""
    global registry
    registry = ModelRegistry()
    
    config_path = os.getenv("CONFIG_PATH", "config/config.yaml")
    try:
        registry.load_from_config(config_path)
    except FileNotFoundError:
        raise RuntimeError(f"Config file not found at {config_path}")
    except Exception as e:
        raise RuntimeError(f"Failed to load config: {e}")


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> dict:
    """Handle chat completion requests.
    
    Args:
        request: Chat completion request
        
    Returns:
        Chat completion response in OpenAI format
        
    Raises:
        HTTPException: If model not found or all providers fail
    """
    if registry is None:
        raise HTTPException(status_code=500, detail="Registry not initialized")
    
    # Get the model
    model = registry.get_model(request.model)
    if not model:
        raise HTTPException(
            status_code=404,
            detail=f"Model not found: {request.model}"
        )
    
    # Convert messages to dicts (they're already in dict format from Pydantic)
    messages = [msg.dict() for msg in request.messages]
    
    # Prepare kwargs for provider
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
    
    # Try each provider in order
    last_error = None
    for provider_instance in model.get_available_providers():
        try:
            response = provider_instance.provider.chat_completion(
                messages=messages,
                model_id=provider_instance.model_id,
                **kwargs
            )
            
            # Mark success
            provider_instance.mark_success()
            
            return response
            
        except Exception as e:
            last_error = e
            provider_instance.mark_failure()
            continue
    
    # All providers failed
    raise HTTPException(
        status_code=503,
        detail=f"All providers failed. Last error: {str(last_error)}"
    )


@app.get("/v1/models")
async def list_models() -> dict:
    """List all available models.
    
    Returns:
        List of available models in OpenAI format
    """
    if registry is None:
        raise HTTPException(status_code=500, detail="Registry not initialized")
    
    models = registry.list_models()
    return {
        "object": "list",
        "data": [model.to_dict() for model in models]
    }


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"message": exc.detail, "type": "error"}},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)