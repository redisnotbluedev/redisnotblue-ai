import requests
import uuid
import time
from .base import Provider, TransformedRequest, TransformedResponse

class BlackboxProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://www.blackbox.ai/api/chat"

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		payload = {
			"messages": messages,
			"id": str(uuid.uuid4()),
			"userSelectedModel": model_id,
			"codeModelMode": True,
			"agentMode": {},
			"trendingAgentMode": {},
			"isMicMode": False,
			"isChromeExt": False,
			"githubToken": None,
			"validated": "00000000-0000-0000-0000-000000000000" # Stealth bypass
		}
		return TransformedRequest(data=payload, original_model_id=model_id, provider_model_id=model_id)

	def make_request(self, request_data, api_key) -> dict:
		headers = get_browser_headers("https://www.blackbox.ai/", "https://www.blackbox.ai")

		# If you provide a session token, we use it.
		# If you don't, we chat as a guest.
		if api_key:
			headers["Cookie"] = f"sessionId={api_key}"

		# Jitter to avoid bot-spam flags
		time.sleep(random.uniform(0.5, 1.2))
		resp = requests.post(self.base_url, json=request_data, headers=headers, timeout=self.timeout)

		if resp.status_code == 429:
			raise Exception("Blackbox Rate Limited: Please provide/refresh sessionId in config.")

		content = resp.text
		if "$$$" in content: content = content.split("$$$")[-1]

		# Check if we were told to sign in (happens when using gpt-5.2 without a key)
		if "Please sign in" in content or "reached your daily limit" in content:
			raise Exception("Blackbox Premium Limit: sessionId required for this model.")

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
