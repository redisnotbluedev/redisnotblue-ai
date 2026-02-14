import requests
from .base import Provider, TransformedRequest, TransformedResponse
from .browser_evasion import get_browser_headers

class DeepSeekWebProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://chat.deepseek.com/api/v0/chat/completions"

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		# data is a dict
		return TransformedRequest(
			data={"model": model_id, "messages": messages, "stream": False},
			original_model_id=model_id,
			provider_model_id=model_id
		)

	def make_request(self, request_data, api_key) -> dict:
		headers = get_browser_headers("https://chat.deepseek.com/")
		headers.update({
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json"
		})
		resp = requests.post(self.base_url, json=request_data, headers=headers, timeout=self.timeout)
		return resp.json()

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		response_data["provider"] = self.name
		return TransformedResponse(data=response_data, provider_name=self.name)
