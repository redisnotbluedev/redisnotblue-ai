import requests
import json
import time
from .base import Provider, TransformedRequest, TransformedResponse

class LambdaProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://lambda.chat/conversation"

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		history = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
		# data is a dict
		return TransformedRequest(
			data={"model": model_id, "prompt": history},
			original_model_id=model_id,
			provider_model_id=model_id
		)

	def make_request(self, request_data, api_key) -> dict:
		s = requests.Session()
		s.cookies.set("hf-chat", api_key)
		init = s.post(self.base_url, json={"model": request_data["model"]}, timeout=self.timeout)
		cid = init.json().get("conversationId")

		resp = s.post(f"{self.base_url}/{cid}", json={"text": request_data["prompt"], "conversation": cid}, timeout=self.timeout)
		full_text = "".join([json.loads(l).get("text", "") for l in resp.text.split("\n") if l.strip()])
		return {"content": full_text}

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		return TransformedResponse(
			data={"choices": [{"message": {"role": "assistant", "content": response_data["content"]}}], "model": original_model_id, "provider": self.name},
			provider_name=self.name
		)
