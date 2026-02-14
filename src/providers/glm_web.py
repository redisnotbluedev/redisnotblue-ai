import requests
import time
import uuid
import json
from .base import Provider, TransformedRequest, TransformedResponse

class GLMWebProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://chat.z.ai/api"
		self.fe_version = "prod-fe-1.0.240"

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		# Z.ai v2 requires a unique request_id and message_id
		request_id = str(uuid.uuid4())
		msg_id = str(uuid.uuid4())

		# Telemetry / Browser fingerprint mimicry
		payload = {
			"stream": True,
			"model": model_id,
			"messages": messages,
			"signature_prompt": messages[-1]["content"],
			"params": {},
			"extra": {},
			"features": {
				"image_generation": False,
				"web_search": False,
				"auto_web_search": False,
				"preview_mode": True,
				"enable_thinking": True
			},
			"id": request_id,
			"current_user_message_id": msg_id,
			"background_tasks": {"title_generation": True, "tags_generation": True}
		}
		return TransformedRequest(data=payload, original_model_id=model_id, provider_model_id=model_id)

	def make_request(self, request_data, api_key) -> dict:
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json",
			"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0",
			"X-FE-Version": self.fe_version,
			"Origin": "https://chat.z.ai",
			"Referer": "https://chat.z.ai/",
			"Priority": "u=4"
		}

		try:
			# STEP 1: Initialize Chat (Required for chat_id)
			new_chat_payload = {
				"chat": {
					"id": "",
					"title": "New Chat",
					"models": [request_data["model"]],
					"history": {"messages": {}, "currentId": ""},
					"enable_thinking": True
				}
			}
			init_resp = requests.post(f"{self.base_url}/v1/chats/new", json=new_chat_payload, headers=headers, timeout=10).json()
			chat_id = init_resp.get("id")

			# STEP 2: Completions v2
			request_data["chat_id"] = chat_id
			ts = int(time.time() * 1000)

			# Query params found in your HAR
			params = {
				"timestamp": ts,
				"requestId": request_data["id"],
				"platform": "web",
				"version": "0.0.1",
				"signature_timestamp": ts
			}

			# Signature Note: If Z.ai rejects this, you may need to
			# extract the 'X-Signature' from your browser and hardcode it temporarily.
			# But usually, providing the correct timestamp and FE-Version is enough.
			url = f"{self.base_url}/v2/chat/completions"
			resp = requests.post(url, json=request_data, headers=headers, params=params, timeout=self.timeout)

			if resp.status_code != 200:
				raise Exception(f"GLM Error {resp.status_code}: {resp.text}")

			full_content = ""
			for line in resp.text.split("\n"):
				if line.startswith("data: "):
					try:
						chunk = json.loads(line[6:])
						# Z.ai v2 structure: data.delta_content
						delta = chunk.get("data", {}).get("delta_content", "")
						phase = chunk.get("data", {}).get("phase", "")
						if phase in ["answer", "thinking"]: # We collect both for completeness
							full_content += delta
					except: continue

			return {"content": full_content}
		except Exception as e:
			raise Exception(f"GLM Request Failed: {e}")

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		return TransformedResponse(
			data={
				"choices": [{"message": {"role": "assistant", "content": response_data["content"]}}],
				"model": original_model_id,
				"provider": self.name
			},
			provider_name=self.name
		)
