import requests
import time
import uuid
import json
from .base import Provider, TransformedRequest, TransformedResponse

class YuppProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://yupp.ai/api/chat"
		self.timeout = config.get("timeout", 90)

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		convo_id = str(uuid.uuid4())
		# We wrap the list in a dict to satisfy the data: dict type requirement
		trpc_payload = [
			convo_id,
			str(uuid.uuid4()), # turn_id
			messages[-1]["content"],
			"$undefined",
			"$undefined",
			[],
			"$undefined",
			[{"modelName": model_id, "promptModifierId": "$undefined"}],
			"text",
			True,
			"$undefined"
		]
		return TransformedRequest(
			data={
				"trpc_payload": trpc_payload,
				"convo_id": convo_id
			},
			original_model_id=model_id,
			provider_model_id=model_id
		)

	def make_request(self, request_data, api_key) -> dict:
		# Extract the list from the wrapper dict
		payload = request_data["trpc_payload"]
		convo_id = request_data["convo_id"]

		headers = {
			"cookie": f"__Secure-yupp.session-token={api_key}",
			"content-type": "text/plain;charset=UTF-8",
			"accept": "text/x-component",
			"next-action": "d6dcb36c50a0282ee9aa466903ba1f02fa093f87",
			"user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
		}

		url = f"{self.base_url}/{convo_id}?stream=true"
		try:
			# Pass the list 'payload' as the json body
			resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
			if resp.status_code != 200:
				raise Exception(f"Yupp API Error {resp.status_code}: {resp.text}")

			full_content = ""
			for line in resp.text.split("\n"):
				if ':"curr":"' in line:
					try:
						data = json.loads(line.split(":", 1)[1])
						full_content += data.get("curr", "")
					except: continue
			return {"content": full_content}
		except Exception as e:
			raise Exception(f"Yupp request failed: {e}")

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		content = response_data.get("content", "")
		return TransformedResponse(
			data={
				"id": f"yupp-{uuid.uuid4().hex[:12]}",
				"object": "chat.completion",
				"created": int(time.time()),
				"model": original_model_id,
				"choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
				"usage": {"prompt_tokens": 0, "completion_tokens": len(content)//4, "total_tokens": len(content)//4},
				"provider": self.name
			},
			provider_name=self.name
		)
