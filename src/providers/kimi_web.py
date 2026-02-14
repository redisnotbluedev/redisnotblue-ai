import requests
from .base import Provider, TransformedRequest, TransformedResponse

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
		stealth_headers = {
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
		auth_headers = {"Authorization": f"Bearer {api_key}", **stealth_headers}
		auth = requests.post(f"{self.base_url}/auth/token", headers=auth_headers).json()
		headers = {"Authorization": f"Bearer {auth.get('access_token')}", **stealth_headers}
		chat = requests.post(f"{self.base_url}/chat", headers=headers, json={"name": "Proxy"}).json()
		resp = requests.post(f"{self.base_url}/chat/{chat['id']}/completion", headers=headers, json={"messages": request_data["messages"]})
		return resp.json()

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		return TransformedResponse(
			data={"choices": [{"message": {"role": "assistant", "content": response_data.get("content", "")}}], "model": original_model_id, "provider": self.name},
			provider_name=self.name
		)
