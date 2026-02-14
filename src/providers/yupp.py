import requests
import time
import uuid
import json
import random
from .base import Provider, TransformedRequest, TransformedResponse

class YuppProvider(Provider):
	def __init__(self, name, config):
		super().__init__(name, config)
		self.base_url = "https://yupp.ai/api"
		# Randomize User-Agent to avoid "Proxy Cluster" flagging
		self.ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/13{random.randint(0,9)}.0.0.0 Safari/537.36"

	def translate_request(self, messages, model_id, **kwargs) -> TransformedRequest:
		convo_id = str(uuid.uuid4())
		turn_id = str(uuid.uuid4())

		# ADDED: Random delay to mimic human "thinking/typing" time
		time.sleep(random.uniform(0.5, 1.5))

		trpc_payload = [
			convo_id,
			turn_id,
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
			data={"trpc_payload": trpc_payload, "convo_id": convo_id, "turn_id": turn_id},
			original_model_id=model_id,
			provider_model_id=model_id
		)

	def make_request(self, request_data, api_key) -> dict:
		payload = request_data["trpc_payload"]
		convo_id = request_data["convo_id"]

		headers = {
			"cookie": f"__Secure-yupp.session-token={api_key}",
			"content-type": "text/plain;charset=UTF-8",
			"accept": "text/x-component",
			"next-action": "d6dcb36c50a0282ee9aa466903ba1f02fa093f87",
			"user-agent": self.ua,
			"origin": "https://yupp.ai",
			"referer": f"https://yupp.ai/chat/{convo_id}", # CRITICAL: Must match convo_id
			"sec-ch-ua-platform": '"Windows"',
			"sec-fetch-dest": "empty",
			"sec-fetch-mode": "cors",
			"sec-fetch-site": "same-origin"
		}

		try:
			resp = requests.post(f"{self.base_url}/chat/{convo_id}?stream=true", json=payload, headers=headers, timeout=self.timeout)
			if resp.status_code == 403 or "disabled" in resp.text:
				raise Exception("ACCOUNT_BANNED: Please refresh api_key in config.")

			full_content = ""
			right_msg_id = None
			for line in resp.text.split("\n"):
				if ':"curr":"' in line:
					try:
						chunk = json.loads(line.split(":", 1)[1])
						full_content += chunk.get("curr", "")
						if not right_msg_id: right_msg_id = chunk.get("messageId")
					except: continue

			if right_msg_id:
				# Mimic human pause before giving feedback
				time.sleep(random.uniform(2, 4))
				self._renew_credits(api_key, request_data["turn_id"], right_msg_id, convo_id)

			return {"content": full_content}
		except Exception as e:
			raise Exception(f"Yupp request failed: {e}")

	def _renew_credits(self, token, turn_id, msg_id, convo_id):
		h = {
			"cookie": f"__Secure-yupp.session-token={token}",
			"content-type": "application/json",
			"referer": f"https://yupp.ai/chat/{convo_id}",
			"user-agent": self.ua
		}
		fb_url = f"{self.base_url}/trpc/evals.recordModelFeedback?batch=1"
		fb_data = {"0": {"json": {"turnId": turn_id, "evalType": "SELECTION", "messageEvals": [{"messageId": msg_id, "rating": "GOOD", "reasons": ["Fast"]}]}}}
		try:
			fb_resp = requests.post(fb_url, json=fb_data, headers=h).json()
			eval_id = fb_resp[0]["result"]["data"]["json"].get("evalId")
			if eval_id:
				# Final step to "Claim" the money
				requests.post(f"{self.base_url}/trpc/reward.claim?batch=1", json={"0": {"json": {"evalId": eval_id}}}, headers=h)
		except: pass

	def translate_response(self, response_data, original_model_id) -> TransformedResponse:
		content = response_data.get("content", "")
		return TransformedResponse(
			data={
				"id": f"yupp-{uuid.uuid4().hex[:12]}",
				"choices": [{"message": {"role": "assistant", "content": content}}],
				"model": original_model_id,
				"provider": self.name
			},
			provider_name=self.name
		)
