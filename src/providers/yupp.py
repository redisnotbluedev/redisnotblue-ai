import requests
import time
import uuid
import json
import base64
import random
from .base import Provider, TransformedRequest, TransformedResponse

class YuppProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://yupp.ai/api"
		self.token_map = {} # Cache for renewed tokens

	def _get_user_id(self, token):
		"""Extract userId from JWT token automatically."""
		try:
			payload = token.split('.')[1]
			data = json.loads(base64.b64decode(payload + '==').decode())
			return data.get('sub') or data.get('userId')
		except: return None

	def _refresh_session(self, token):
		"""Hits the session endpoint to rotate/validate token."""
		uid = self._get_user_id(token)
		if not uid: return token

		headers = {
			"cookie": f"__Secure-yupp.session-token={token}",
			"content-type": "application/json",
			"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
			"origin": "https://yupp.ai",
			"referer": "https://yupp.ai/"
		}
		try:
			resp = requests.post(f"{self.base_url}/authentication/session", json={"userId": uid}, headers=headers, timeout=10)
			new_token = resp.cookies.get("__Secure-yupp.session-token")
			return new_token if new_token else token
		except: return token

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		convo_id = str(uuid.uuid4())
		turn_id = str(uuid.uuid4())
		payload = [
			convo_id, turn_id, messages[-1]["content"],
			"$undefined", "$undefined", [], "$undefined",
			[{"modelName": model_id, "promptModifierId": "$undefined"}],
			"text", True, "$undefined"
		]
		return TransformedRequest(
			data={"trpc_payload": payload, "convo_id": convo_id, "turn_id": turn_id},
			original_model_id=model_id,
			provider_model_id=model_id
		)

	def make_request(self, request_data, api_key) -> dict:
		# 1. Automatic Renewal
		token = self.token_map.get(api_key, api_key)
		token = self._refresh_session(token)
		self.token_map[api_key] = token # Update cache

		convo_id = request_data["convo_id"]
		headers = {
			"cookie": f"__Secure-yupp.session-token={token}",
			"content-type": "text/plain;charset=UTF-8",
			"accept": "text/x-component",
			"next-action": "d6dcb36c50a0282ee9aa466903ba1f02fa093f87",
			"user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
			"referer": f"https://yupp.ai/chat/{convo_id}"
		}

		try:
			# Human-mimic jitter
			time.sleep(random.uniform(0.8, 2.0))
			resp = requests.post(f"{self.base_url}/chat/{convo_id}?stream=true", json=request_data["trpc_payload"], headers=headers, timeout=self.timeout)

			full_content = ""
			msg_id = None
			for line in resp.text.split("\n"):
				if ':"curr":"' in line:
					try:
						chunk = json.loads(line.split(":", 1)[1])
						full_content += chunk.get("curr", "")
						if not msg_id: msg_id = chunk.get("messageId")
					except: continue

			# 2. RENEW CREDITS (Farming Loop)
			if msg_id:
				self._farm_credits(token, request_data["turn_id"], msg_id, convo_id)

			return {"content": full_content}
		except Exception as e:
			raise Exception(f"Yupp Failure: {e}")

	def _farm_credits(self, token, turn_id, msg_id, convo_id):
		h = {"cookie": f"__Secure-yupp.session-token={token}", "content-type": "application/json", "referer": f"https://yupp.ai/chat/{convo_id}"}
		# Give a 'GOOD' rating to trigger reward
		fb_data = {"0": {"json": {"turnId": turn_id, "evalType": "SELECTION", "messageEvals": [{"messageId": msg_id, "rating": "GOOD", "reasons": ["Fast"]}]}}}
		try:
			fb_resp = requests.post(f"{self.base_url}/trpc/evals.recordModelFeedback?batch=1", json=fb_data, headers=h).json()
			eval_id = fb_resp[0]["result"]["data"]["json"].get("evalId")
			if eval_id:
				requests.post(f"{self.base_url}/trpc/reward.claim?batch=1", json={"0": {"json": {"evalId": eval_id}}}, headers=h)
		except: pass

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		return TransformedResponse(
			data={
				"choices": [{"message": {"role": "assistant", "content": response_data.get("content", "")}}],
				"model": original_model_id,
				"provider": self.name
			},
			provider_name=self.name
		)
