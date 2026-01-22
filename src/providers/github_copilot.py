from .openai import OpenAIProvider
import requests, time, uuid, json

class GitHubCopilotProvider(OpenAIProvider):
	"""Provider for the internal GitHub Copilot API with streaming support."""

	def __init__(self, name: str, config: dict):
		config.setdefault("base_url", "https://api.githubcopilot.com")
		super().__init__(name, config)
		self.expires_at = -1
		self.copilot_key = None
		self.base_renew_url = config.get("base_renew_url", "https://api.github.com")

	def get_key(self, api_key: str):
		if time.time() < self.expires_at:
			return self.copilot_key

		try:
			response = requests.get(f"{self.base_renew_url}/copilot_internal/v2/token", headers={
				"Authorization": f"token {api_key}",
				"Content-Type": "application/json",
				"Accept": "application/json",
				"User-Agent": "GitHubCopilotChat/0.26.7",
				"Editor-Version": "vscode/1.96.5",
				"Editor-Plugin-Version": "copilot-chat/0.26.7",
				"X-GitHub-Api-Version": "2025-04-01"
			})

			if response.status_code != 200:
				error_msg = response.text
				try:
					error_data = response.json()
					if "error" in error_data:
						error_msg = str(error_data["error"])
				except Exception:
					pass

				raise Exception(
					f"GitHub API error when requesting token renewal {response.status_code}: {error_msg}"
				)

			data = response.json()
			self.expires_at = data.get("expires_at", -1)
			self.copilot_key = data.get("token", None)
			if data.get("sku", "individual") not in ["individual", "free_educational_quota"]:
				self.base_url = f"https://api.{data.get('sku')}.githubcopilot.com"
			return data.get("token", None)

		except requests.exceptions.Timeout:
			raise Exception(f"GitHub API timeout after {self.timeout}s when requesting token renewal")
		except requests.exceptions.ConnectionError as e:
			raise Exception(f"GitHub API connection error when requesting token renewal: {e}")
		except requests.exceptions.RequestException as e:
			raise Exception(f"GitHub API request error when requesting token renewal: {e}")

	def make_request(self, request_data: dict, api_key: str):
		"""Make streaming request to GitHub Copilot API and collect all chunks."""
		url = f"{self.base_url}/chat/completions"
		token = self.get_key(api_key)
		headers = {
			"Authorization": f"Bearer {token}",
			"Content-Type": "application/json",
			"Accept": "application/json",
			"User-Agent": "GitHubCopilotChat/0.26.7",
			"Editor-Version": "vscode/1.96.5",
			"Editor-Plugin-Version": "copilot-chat/0.26.7",
			"Copilot-Integration-Id": "vscode-chat",
			"OpenAI-Intent": "conversation-panel",
			"X-GitHub-Api-Version": "2025-04-01",
			"X-Request-Id": str(uuid.uuid4()),
			"X-Initiator": "user"
		}

		start_time = time.time()
		try:
			response = requests.post(
				url,
				json=request_data,
				headers=headers,
				timeout=self.timeout,
				stream=True
			)

			if response.status_code != 200:
				error_msg = response.text
				try:
					error_data = response.json()
					if "error" in error_data:
						error_msg = str(error_data["error"])
				except Exception:
					pass

				raise Exception(
					f"Copilot API error {response.status_code}: {error_msg}"
				)

			return self._process_stream(response, start_time)
		except requests.exceptions.Timeout:
			raise Exception(f"Copilot API timeout after {self.timeout}s")
		except requests.exceptions.ConnectionError as e:
			raise Exception(f"Copilot API connection error: {e}")
		except requests.exceptions.RequestException as e:
			raise Exception(f"Copilot API request error: {e}")