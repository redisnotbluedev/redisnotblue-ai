import requests
from .base import Provider, TransformedRequest, TransformedResponse
from .browser_evasion import get_browser_headers

class KimiWebProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://kimi.moonshot.cn/api"

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		# data is a dict
		return TransformedRequest(
			data={"messages": messages, "model": model_id},
			original_model_id=model_id,
			provider_model_id=model_id
		)

	def make_request(self, request_data, api_key) -> dict:
		base_headers = get_browser_headers("https://kimi.moonshot.cn/")
		auth_headers = {"Authorization": f"Bearer {api_key}", **base_headers}
		auth = requests.post(f"{self.base_url}/auth/token", headers=auth_headers).json()
		headers = {"Authorization": f"Bearer {auth.get('access_token')}", **base_headers}
		chat = requests.post(f"{self.base_url}/chat", headers=headers, json={"name": "Proxy"}).json()
		resp = requests.post(f"{self.base_url}/chat/{chat['id']}/completion", headers=headers, json={"messages": request_data["messages"]})
		return resp.json()

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		return TransformedResponse(
			data={"choices": [{"message": {"role": "assistant", "content": response_data.get("content", "")}}], "model": original_model_id, "provider": self.name},
			provider_name=self.name
		)
