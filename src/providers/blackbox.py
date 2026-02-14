import requests
import uuid
from .base import Provider, TransformedRequest, TransformedResponse

class BlackboxProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://www.blackbox.ai/api/chat"

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		# payload is already a dict
		payload = {
			"messages": messages,
			"id": str(uuid.uuid4()),
			"userSelectedModel": model_id,
			"codeModelMode": True,
			"agentMode": {},
			"mobileClient": False
		}
		return TransformedRequest(data=payload, original_model_id=model_id, provider_model_id=model_id)

	def make_request(self, request_data, api_key) -> dict:
		headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
		if api_key: headers["Cookie"] = f"sessionId={api_key}"

		resp = requests.post(self.base_url, json=request_data, headers=headers, timeout=self.timeout)
		content = resp.text
		if "$$$" in content: content = content.split("$$$")[-1]
		return {"content": content.strip()}

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		return TransformedResponse(
			data={
				"id": str(uuid.uuid4()),
				"choices": [{"message": {"role": "assistant", "content": response_data["content"]}}],
				"model": original_model_id,
				"provider": self.name
			},
			provider_name=self.name
		)
