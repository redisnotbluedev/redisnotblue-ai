import requests
from .base import Provider, TransformedRequest, TransformedResponse

class GLMWebProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://chat.z.ai/api/chat/completions"

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		# data is a dict
		return TransformedRequest(
			data={"model": model_id, "messages": messages, "stream": False},
			original_model_id=model_id,
			provider_model_id=model_id
		)

	def make_request(self, request_data, api_key) -> dict:
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Platform": "web",
			"Sec-Ch-Ua": '"Not(A:Brand";v="99", "Google Chrome";v="137", "Chromium";v="137"',
			"Sec-Ch-Ua-Mobile": "?0",
			"Sec-Ch-Ua-Platform": '"Windows"',
			"Sec-Fetch-Dest": "empty",
			"Sec-Fetch-Mode": "cors",
			"Sec-Fetch-Site": "same-origin",
			"Priority": "u=1, i",
			"Pragma": "no-cache",
			"Cache-Control": "no-cache"
		}
		resp = requests.post(self.base_url, json=request_data, headers=headers, timeout=self.timeout)
		return resp.json()

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		response_data["provider"] = self.name
		return TransformedResponse(data=response_data, provider_name=self.name)
