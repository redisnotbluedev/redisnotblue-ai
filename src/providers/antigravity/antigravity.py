"""
Antigravity Provider for Google's internal API.

Supports:
- Claude models (Opus 4.5, Sonnet 4.5)
- Gemini 3 models (Pro, Flash)
- Gemini 2.5 models
- Thinking models with configurable budgets
- OAuth token management with automatic refresh
- Multi-account support with rotation
"""

import json
import re
import time
import uuid
import requests
from typing import List, Dict, Any, Optional, Tuple
from ..base import Provider, TransformedRequest, TransformedResponse


class AntigravityProvider(Provider):
    """Provider for Google Antigravity API with OAuth authentication."""

    # Antigravity OAuth credentials (extracted from official client)
    ANTIGRAVITY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
    ANTIGRAVITY_CLIENT_SECRET = "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"

    # Endpoints in fallback order (sandbox first for newer models)
    ENDPOINTS = [
        "https://daily-cloudcode-pa.sandbox.googleapis.com",
        "https://autopush-cloudcode-pa.sandbox.googleapis.com",
        "https://cloudcode-pa.googleapis.com",
    ]

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)

        self.timeout = config.get("timeout", 120)

        # Get refresh tokens from api_keys
        self.refresh_tokens = config.get("api_keys", [])
        if not self.refresh_tokens:
            raise ValueError(f"Provider '{name}' requires at least one api_key (refresh token)")

        # Token cache: {refresh_token: {"access_token": str, "expires": int, "project_id": str}}
        self.token_cache: Dict[str, Dict[str, Any]] = {}

        # Current account index for rotation
        self.current_account = 0

    def get_access_token(self, refresh_token: str) -> str:
        """Get valid access token, refreshing if expired."""
        now = time.time()

        # Check cache
        if refresh_token in self.token_cache:
            cache = self.token_cache[refresh_token]
            # Check if token expires in more than 60 seconds
            if cache.get("expires", 0) > now + 60:
                return cache["access_token"]

        # Refresh token
        try:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.ANTIGRAVITY_CLIENT_ID,
                    "client_secret": self.ANTIGRAVITY_CLIENT_SECRET
                },
                timeout=10
            )

            if response.status_code != 200:
                raise Exception(f"Token refresh failed: {response.text}")

            data = response.json()

            # Cache new token
            self.token_cache[refresh_token] = {
                "access_token": data["access_token"],
                "expires": now + data.get("expires_in", 3600)
            }

            return data["access_token"]

        except Exception as e:
            raise Exception(f"Failed to refresh access token: {e}")

    def fetch_project_id(self, access_token: str) -> str:
        """Fetch project ID from Google Cloud API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "google-api-nodejs-client/9.15.1",
            "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1"
        }

        body = {
            "metadata": {
                "ideType": "IDE_UNSPECIFIED",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI"
            }
        }

        # Try multiple endpoints
        for endpoint in ["https://cloudcode-pa.googleapis.com",
                        "https://daily-cloudcode-pa.sandbox.googleapis.com"]:
            try:
                response = requests.post(
                    f"{endpoint}/v1internal:loadCodeAssist",
                    headers=headers,
                    json=body,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    project_id = data.get("cloudaicompanionProject")

                    # Handle nested project ID
                    if isinstance(project_id, dict):
                        project_id = project_id.get("id")

                    if project_id:
                        return project_id
            except:
                continue

        # Fallback to default project ID
        return "rising-fact-p41fc"

    def resolve_model(self, model_id: str) -> Tuple[str, Optional[str], Optional[Dict[str, Any]]]:
        """
        Resolve model name and thinking configuration.

        Returns:
            (api_model_name, thinking_level, thinking_config)
        """
        # Strip antigravity- prefix
        model = re.sub(r'^antigravity-', '', model_id, flags=re.IGNORECASE)

        # Extract tier suffix
        tier_match = re.search(r'-(minimal|low|medium|high)$', model)
        tier = tier_match.group(1) if tier_match else None
        base_model = re.sub(r'-(minimal|low|medium|high)$', '', model) if tier else model

        lower_base = base_model.lower()

        # Determine model family
        is_claude = 'claude' in lower_base
        is_gemini3_pro = lower_base.startswith('gemini-3-pro')
        is_gemini3_flash = lower_base.startswith('gemini-3-flash')
        is_gemini3 = is_gemini3_pro or is_gemini3_flash
        is_gemini25 = lower_base.startswith('gemini-2.5')

        thinking_level = None
        thinking_config = None

        # === GEMINI 3 PRO ===
        # Requires tier suffix in API model name
        if is_gemini3_pro:
            if tier:
                # Keep tier in model name: gemini-3-pro-low, gemini-3-pro-high
                api_model = f"{base_model}-{tier}"
            else:
                # Default to -low
                api_model = f"{base_model}-low"

            # No separate thinking config needed (tier is in model name)
            thinking_level = tier or "low"

        # === GEMINI 3 FLASH ===
        # Uses bare model name + thinkingLevel parameter
        elif is_gemini3_flash:
            api_model = base_model  # Always bare: gemini-3-flash
            thinking_level = tier or "low"
            # Thinking level will be added to generationConfig

        # === GEMINI 2.5 ===
        # Can use thinking levels via generationConfig
        elif is_gemini25:
            api_model = base_model  # gemini-2.5-flash, gemini-2.5-pro
            if tier:
                thinking_level = tier

        # === CLAUDE THINKING ===
        # Uses thinkingConfig with budget
        elif is_claude and 'thinking' in lower_base:
            api_model = base_model  # claude-sonnet-4-5-thinking

            # Map tier to token budget
            budget_map = {
                'minimal': 1024,
                'low': 8192,
                'medium': 16384,
                'high': 32768
            }
            budget = budget_map.get(tier, 32768)  # Default to high

            thinking_config = {
                "thinkingBudget": budget,
                "includeThoughts": True
            }

        # === OTHER MODELS ===
        # No special handling (claude-sonnet-4-5, gpt-oss-120b-medium, etc.)
        else:
            api_model = base_model

        return api_model, thinking_level, thinking_config

    def translate_request(
        self,
        messages: List[Dict[str, Any]],
        model_id: str,
        **kwargs
    ) -> TransformedRequest:
        """Transform OpenAI format to Antigravity format."""

        # Resolve model
        api_model, thinking_level, thinking_config = self.resolve_model(model_id)

        # Convert OpenAI messages to Gemini contents format
        contents = []
        system_instruction = None

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                # System messages go in systemInstruction
                system_instruction = content
                continue

            # Map assistant -> model for Gemini
            if role == "assistant":
                role = "model"

            # Convert content to parts
            if isinstance(content, str):
                parts = [{"text": content}]
            elif isinstance(content, list):
                # Multi-modal content
                parts = []
                for item in content:
                    if item["type"] == "text":
                        parts.append({"text": item["text"]})
                    elif item["type"] == "image_url":
                        # Handle images (simplified - you may need base64 decoding)
                        parts.append({
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": item["image_url"]["url"]
                            }
                        })
            else:
                parts = [{"text": str(content)}]

            contents.append({
                "role": role,
                "parts": parts
            })

        # Build request payload
        request_payload = {
            "contents": contents
        }

        # Add system instruction
        if system_instruction:
            request_payload["systemInstruction"] = {
                "role": "user",  # Antigravity requires "user" role
                "parts": [{"text": system_instruction}]
            }

        # Add thinking configuration
        if thinking_config:
            request_payload["thinkingConfig"] = thinking_config

        # Add thinking level for Gemini models
        if thinking_level:
            if "generationConfig" not in request_payload:
                request_payload["generationConfig"] = {}
            request_payload["generationConfig"]["thinkingLevel"] = thinking_level

        # Add tools if provided
        if kwargs.get("tools"):
            # Convert OpenAI tools to Gemini functionDeclarations
            function_declarations = []
            for tool in kwargs["tools"]:
                if tool.get("type") == "function":
                    func = tool["function"]
                    declaration = {
                        "name": func["name"],
                        "description": func.get("description", "")
                    }
                    if "parameters" in func:
                        declaration["parameters"] = self._clean_schema(func["parameters"])
                    function_declarations.append(declaration)

            if function_declarations:
                request_payload["tools"] = [{"functionDeclarations": function_declarations}]

        # Add optional parameters
        if kwargs.get("temperature") is not None:
            if "generationConfig" not in request_payload:
                request_payload["generationConfig"] = {}
            request_payload["generationConfig"]["temperature"] = kwargs["temperature"]

        if kwargs.get("top_p") is not None:
            if "generationConfig" not in request_payload:
                request_payload["generationConfig"] = {}
            request_payload["generationConfig"]["topP"] = kwargs["top_p"]

        max_tokens = kwargs.get("max_tokens") or kwargs.get("max_completion_tokens")
        if max_tokens:
            if "generationConfig" not in request_payload:
                request_payload["generationConfig"] = {}
            request_payload["generationConfig"]["maxOutputTokens"] = max_tokens

        if kwargs.get("stop"):
            stops = kwargs["stop"] if isinstance(kwargs["stop"], list) else [kwargs["stop"]]
            if "generationConfig" not in request_payload:
                request_payload["generationConfig"] = {}
            request_payload["generationConfig"]["stopSequences"] = stops

        # Get project ID
        refresh_token = self.refresh_tokens[self.current_account]
        access_token = self.get_access_token(refresh_token)

        # Fetch project ID if not cached
        if refresh_token not in self.token_cache or "project_id" not in self.token_cache[refresh_token]:
            project_id = self.fetch_project_id(access_token)
            if refresh_token in self.token_cache:
                self.token_cache[refresh_token]["project_id"] = project_id
        else:
            project_id = self.token_cache[refresh_token]["project_id"]

        # Wrap in Antigravity envelope
        wrapped_request = {
            "project": project_id,
            "model": api_model,
            "request": request_payload,
            "requestType": "agent",
            "userAgent": "antigravity",
            "requestId": f"agent-{uuid.uuid4().hex}"
        }

        return TransformedRequest(
            data=wrapped_request,
            original_model_id=model_id,
            provider_model_id=api_model
        )

    def _clean_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean JSON schema for Antigravity compatibility.

        Removes unsupported fields like $ref, $defs, const, etc.
        """
        if not isinstance(schema, dict):
            return schema

        # Copy to avoid modifying original
        cleaned = {}

        # Remove unsupported keywords
        unsupported = {
            "$ref", "$defs", "definitions", "const",
            "examples", "default", "deprecated",
            "readOnly", "writeOnly", "contentEncoding",
            "contentMediaType", "if", "then", "else",
            "not", "contains", "patternProperties"
        }

        for key, value in schema.items():
            if key in unsupported:
                continue

            # Recursively clean nested schemas
            if key == "properties" and isinstance(value, dict):
                cleaned[key] = {k: self._clean_schema(v) for k, v in value.items()}
            elif key == "items" and isinstance(value, dict):
                cleaned[key] = self._clean_schema(value)
            elif key == "additionalProperties" and isinstance(value, dict):
                cleaned[key] = self._clean_schema(value)
            else:
                cleaned[key] = value

        # Add placeholder for empty object schemas
        if cleaned.get("type") == "object" and not cleaned.get("properties"):
            cleaned["properties"] = {
                "_placeholder": {
                    "type": "boolean",
                    "description": "Placeholder for empty object"
                }
            }

        return cleaned

    def make_request(self, request_data: Dict[str, Any], api_key: str) -> Dict[str, Any]:
        """Make request to Antigravity API with endpoint fallback."""

        # Get current account
        refresh_token = self.refresh_tokens[self.current_account]
        access_token = self.get_access_token(refresh_token)

        # Extract model from wrapped request
        model = request_data.get("model")

        # Determine if streaming (we'll default to non-streaming for now)
        streaming = False  # You can add stream detection logic here

        # Build URL
        action = "streamGenerateContent" if streaming else "generateContent"
        path = f"/v1/models/{model}:{action}"
        if streaming:
            path += "?alt=sse"

        # Build headers (impersonate Antigravity)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity/1.11.5 windows/amd64",
            "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
            "Client-Metadata": '{"ideType":"IDE_UNSPECIFIED","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}'
        }

        # Try each endpoint
        last_error = None
        for endpoint in self.ENDPOINTS:
            url = endpoint + path

            try:
                response = requests.post(
                    url,
                    json=request_data,
                    headers=headers,
                    timeout=self.timeout
                )

                # Check response status
                if response.status_code == 200:
                    # Success!
                    return response.json()

                elif response.status_code == 404:
                    # Model not found at this endpoint, try next
                    last_error = Exception(
                        f"Model '{model}' not found at {endpoint} (404)\n"
                        f"Full URL: {url}\n"
                        f"This might mean:\n"
                        f"  1. Model name is incorrect\n"
                        f"  2. Account doesn't have access to this model\n"
                        f"  3. Model not available on this endpoint"
                    )
                    continue

                elif response.status_code == 429:
                    # Rate limited - try next account or endpoint
                    print(f"Rate limited at {endpoint}, trying next...")
                    last_error = Exception(f"Rate limited at {endpoint}")
                    # Rotate to next account
                    self.current_account = (self.current_account + 1) % len(self.refresh_tokens)
                    continue

                else:
                    # Other error
                    error_text = response.text
                    try:
                        error_json = response.json()
                        error_msg = error_json.get("error", {}).get("message", error_text)
                    except:
                        error_msg = error_text

                    last_error = Exception(
                        f"Antigravity API error {response.status_code} at {endpoint}: {error_msg}"
                    )
                    # Don't continue for non-recoverable errors
                    if response.status_code not in [429, 500, 502, 503, 504]:
                        raise last_error
                    continue

            except requests.exceptions.Timeout:
                last_error = Exception(f"Request timeout after {self.timeout}s at {endpoint}")
                continue
            except Exception as e:
                if "404" in str(e) or "Model" in str(e):
                    # Don't retry 404s across all endpoints
                    raise
                last_error = e
                continue

        # All endpoints failed
        raise last_error or Exception("All Antigravity endpoints failed")

    def translate_response(
        self,
        response_data: Dict[str, Any],
        original_request: TransformedRequest
    ) -> TransformedResponse:
        """Transform Antigravity response to OpenAI format."""

        # Unwrap Antigravity envelope
        inner_response = response_data.get("response", response_data)

        # Extract candidates
        candidates = inner_response.get("candidates", [])
        choices = []

        for idx, candidate in enumerate(candidates):
            content_obj = candidate.get("content", {})
            parts = content_obj.get("parts", [])

            # Separate reasoning and regular content
            reasoning_parts = []
            text_parts = []
            tool_calls = []

            for part in parts:
                # Check for thinking/reasoning
                if part.get("thought") or part.get("type") == "reasoning":
                    reasoning_parts.append(part.get("text", ""))
                # Regular text
                elif "text" in part:
                    text_parts.append(part["text"])
                # Function call
                elif "functionCall" in part:
                    func_call = part["functionCall"]
                    tool_calls.append({
                        "id": part.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                        "type": "function",
                        "function": {
                            "name": func_call["name"],
                            "arguments": json.dumps(func_call.get("args", {}))
                        }
                    })

            # Build message content
            content = "".join(text_parts)

            # Optionally append reasoning
            if reasoning_parts:
                reasoning_text = "".join(reasoning_parts)
                if content:
                    content += f"\n\n[Reasoning]\n{reasoning_text}"
                else:
                    content = reasoning_text

            # Build message
            message = {
                "role": "assistant",
                "content": content or None
            }

            if tool_calls:
                message["tool_calls"] = tool_calls

            # Build choice
            finish_reason = candidate.get("finishReason", "stop")
            if finish_reason:
                finish_reason = finish_reason.lower()

            choices.append({
                "index": idx,
                "message": message,
                "finish_reason": finish_reason
            })

        # Extract usage
        usage_metadata = inner_response.get("usageMetadata", {})
        usage = {
            "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
            "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
            "total_tokens": usage_metadata.get("totalTokenCount", 0)
        }

        # Build OpenAI response
        response = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": original_request.original_model_id,
            "choices": choices,
            "usage": usage,
            "provider": self.name
        }

        return TransformedResponse(
            data=response,
            provider_name=self.name,
            original_request=original_request.data
        )
