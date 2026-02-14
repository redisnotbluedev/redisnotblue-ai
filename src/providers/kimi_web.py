import requests
import uuid
import time
import json
import struct
from .base import Provider, TransformedRequest, TransformedResponse

class KimiProvider(Provider):
    """Provider for Moonshot Kimi (Kimi-k2)."""

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.base_url = "https://www.kimi.com/apiv2/kimi.gateway.chat.v1.ChatService/Chat"

    def translate_request(self, messages: list[dict], model_id: str, **kwargs) -> TransformedRequest:
        # Kimi uses a specific 'blocks' structure inside the message
        last_user_msg = messages[-1]["content"] if messages else ""

        request_payload = {
            "scenario": "SCENARIO_K2D5",
            "tools": [{"type": "TOOL_TYPE_SEARCH", "search": {}}],
            "message": {
                "role": "user",
                "blocks": [{"text": {"content": last_user_msg}}],
                "scenario": "SCENARIO_K2D5"
            },
            "options": {"thinking": True}
        }

        return TransformedRequest(
            data=request_payload,
            original_model_id=model_id,
            provider_model_id=model_id
        )

    def make_request(self, request_data: dict, api_key: str) -> dict:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/connect+json",
            "connect-protocol-version": "1",
            "x-msh-platform": "web",
            "x-traffic-id": str(uuid.uuid4())[:8]
        }

        # Connect Protocol prefix: 1 byte flag (0) + 4 bytes length
        body_json = json.dumps(request_data).encode('utf-8')
        prefix = struct.pack(">BI", 0, len(body_json))

        try:
            response = requests.post(
                self.base_url,
                data=prefix + body_json,
                headers=headers,
                stream=True
            )
            return self._process_kimi_stream(response)
        except Exception as e:
            raise Exception(f"Kimi request failed: {e}")

    def _process_kimi_stream(self, response) -> dict:
        full_text = ""
        thinking_text = ""

        # Generator to read Connect protocol chunks
        def get_chunks():
            while True:
                header = response.raw.read(5)
                if not header: break
                _, length = struct.unpack(">BI", header)
                yield response.raw.read(length)

        for chunk in get_chunks():
            try:
                data = json.loads(chunk)
                op = data.get("op")
                block = data.get("block", {})

                # Extract text or thinking content
                if op in ["set", "append"]:
                    if "text" in block:
                        full_text += block["text"].get("content", "")
                    if "think" in block:
                        thinking_text += block["think"].get("content", "")
            except:
                continue

        return {
            "id": f"kimi-{uuid.uuid4()}",
            "content": full_text,
            "thinking": thinking_text
        }

    def translate_response(self, response_data: dict, original_model_id: str) -> TransformedResponse:
        return TransformedResponse(
            data={
                "id": response_data["id"],
                "object": "chat.completion",
                "created": int(time.time()),
                "model": original_model_id,
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": response_data["content"],
                        "reasoning_content": response_data["thinking"]
                    },
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "provider": self.name
            },
            provider_name=self.name
        )
