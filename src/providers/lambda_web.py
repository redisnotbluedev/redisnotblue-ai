import requests
import json
from .base import Provider, TransformedRequest, TransformedResponse
from .browser_evasion import get_browser_headers

class LambdaProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://lambda.chat/conversation"

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		history = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
		return TransformedRequest(
			data={"model": model_id, "prompt": history},
			original_model_id=model_id,
			provider_model_id=model_id
		)

	def make_request(self, request_data, api_key) -> dict:
		s = requests.Session()
		s.headers.update(get_browser_headers("https://lambda.chat/"))
		s.cookies.set("hf-chat", api_key)

		# 1. SvelteKit Pre-Flight (Evasiveness)
		s.get("https://lambda.chat/", timeout=10)
		init = s.post(self.base_url, json={"model": request_data["model"]}, timeout=self.timeout)
		cid = init.json().get("conversationId")

		# Fetch conversation metadata like a real browser
		s.get(f"{self.base_url}/{cid}/__data.json?x-sveltekit-invalidated=11", timeout=10)

		# 2. Actual Completion
		resp = s.post(f"{self.base_url}/{cid}", json={"text": request_data["prompt"], "conversation": cid}, timeout=self.timeout)
		full_text = "".join([json.loads(l).get("text", "") for l in resp.text.split("\n") if l.strip()])
		return {"content": full_text}

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		return TransformedResponse(
			data={"choices": [{"message": {"role": "assistant", "content": response_data["content"]}}], "model": original_model_id, "provider": self.name},
			provider_name=self.name
		)
