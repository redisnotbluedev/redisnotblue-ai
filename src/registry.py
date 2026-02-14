"""Model registry for managing providers and models."""

import yaml
from typing import Optional, Dict
from .providers.github_copilot import GitHubCopilotProvider
from .models import Model, ProviderInstance, ApiKeyRotation, RateLimitTracker
from .providers.base import Provider
from .providers.openai import OpenAIProvider
from .providers.antigravity import AntigravityProvider
from .providers.deepseek_web import DeepSeekWebProvider
from .providers.glm_web import GLMWebProvider
from .providers.kimi_web import KimiWebProvider
from .providers.yupp import YuppProvider
from .metrics import MetricsPersistence


PROVIDER_CLASSES = {
	"openai": OpenAIProvider,
	"github_copilot": GitHubCopilotProvider,
	"antigravity": AntigravityProvider,
	"deepseek_web": DeepSeekWebProvider,
	"glm_web": GLMWebProvider,
	"kimi_web": KimiWebProvider,
	"yupp": YuppProvider,
}


class ModelRegistry:
	"""Registry for managing models and their provider instances."""

	def __init__(self):
		self.models: Dict[str, Model] = {}
		self.providers: Dict[str, Provider] = {}
		self.provider_defaults: Dict[str, dict] = {}  # Provider-level default rate limits
		self.provider_api_keys: Dict[str, list] = {}  # Provider-level default API keys
		self.provider_credit_config: Dict[str, tuple] = {}  # Provider-level credit gain and max config
		self.global_key_trackers: Dict[str, "RateLimitTracker"] = {}  # Global per-key rate limit trackers
		self.metrics = MetricsPersistence()

	def register_provider(self, name: str, provider: Provider) -> None:
		"""Register a provider instance."""
		self.providers[name] = provider

	def register_model(self, model: Model) -> None:
		"""Register a model."""
		self.models[model.id] = model

	def get_model(self, model_id: str) -> Optional[Model]:
		"""Get a model by ID."""
		return self.models.get(model_id)

	def list_models(self) -> list[Model]:
		"""Get all registered models."""
		return list(self.models.values())

	def save_metrics(self) -> None:
		"""Save all provider metrics to disk."""
		metrics_data = {}
		for model_id, model in self.models.items():
			metrics_data[model_id] = {}
			for pi in model.provider_instances:
				provider_key = f"{pi.provider.name}"
				metrics_data[model_id][provider_key] = self.metrics.extract_provider_metrics(pi)
		self.metrics.save_metrics(metrics_data)

	def load_metrics(self) -> None:
		"""Load all provider metrics from disk."""
		metrics_data = self.metrics.load_metrics()
		for model_id, model in self.models.items():
			if model_id not in metrics_data:
				continue
			for pi in model.provider_instances:
				provider_key = f"{pi.provider.name}"
				if provider_key in metrics_data[model_id]:
					self.metrics.restore_provider_metrics(pi, metrics_data[model_id][provider_key])

	def _apply_multiplier(self, limits: dict, multiplier: float = 1.0, token_multiplier: float = 1.0, request_multiplier: float = 1.0) -> dict:
		"""
		Apply multipliers to rate limits.
		Multipliers represent how much each item counts (e.g., 2.0 = counts as 2x).

		Args:
			limits: Dict of rate limits
			multiplier: General multiplier (applies to all limits)
			token_multiplier: Token-specific multiplier (how much each token counts)
			request_multiplier: Request-specific multiplier (how much each request counts)

		Returns:
			New dict with adjusted limits (divided by multiplier since items count for more)
		"""
		if not limits:
			return limits

		multiplied = {}
		for key, value in limits.items():
			if not isinstance(value, (int, float)) or value <= 0:
				multiplied[key] = value
				continue

			# Determine which multiplier to apply
			final_multiplier = multiplier
			if key.startswith("tokens_per_"):
				final_multiplier *= token_multiplier
			elif key.startswith("requests_per_"):
				final_multiplier *= request_multiplier

			# Divide limit by multiplier since items count for more
			if final_multiplier > 0:
				multiplied[key] = int(value / final_multiplier)
			else:
				multiplied[key] = value

		return multiplied

	def _merge_limits(self, defaults: dict, overrides: dict, multiplier: float = 1.0, token_multiplier: float = 1.0, request_multiplier: float = 1.0) -> dict:
		"""
		Merge default limits with instance-specific overrides.
		Apply multipliers if specified.

		Priority:
		1. Instance-specific rate_limits (highest priority)
		2. Default rate_limits from provider (if no instance override)
		3. Multipliers applied to final result (if specified)

		Args:
			defaults: Default limits from provider config
			overrides: Instance-specific limits override
			multiplier: Optional general multiplier (how much each item counts)
			token_multiplier: Optional multiplier for tokens (how much each token counts)
			request_multiplier: Optional multiplier for requests (how much each request counts)

		Returns:
			Merged and adjusted limits based on multipliers
		"""
		# Start with provider defaults
		merged = dict(defaults) if defaults else {}

		# Override with instance-specific limits
		if overrides:
			merged.update(overrides)

		# Apply multipliers if specified
		if multiplier != 1.0 or token_multiplier != 1.0 or request_multiplier != 1.0:
			merged = self._apply_multiplier(merged, multiplier, token_multiplier, request_multiplier)

		return merged

	def _build_rate_limits(self, rate_limit_config: dict) -> dict:
		"""
		Convert rate limit config to limits dict format.

		Accepts config like:
		{
			"requests_per_minute": 3500,
			"tokens_per_day": 90000,
			"requests_per_hour": 100000,
		}

		Returns a dict with the same keys that can be checked by RateLimitTracker.
		"""
		limits = {}
		if rate_limit_config:
			for key, value in rate_limit_config.items():
				if value is not None and value > 0:
					limits[key] = value
		return limits

	def _extract_credit_rates(self, config: dict) -> tuple:
		"""Extract credit rate configuration from instance config.

		Returns:
			Tuple of (credits_per_token, credits_per_million_tokens,
			          credits_per_in_token, credits_per_out_token,
			          credits_per_million_in_tokens, credits_per_million_out_tokens,
			          credits_per_request)
		"""
		credits_per_token = config.get("credits_per_token", 0.0)
		credits_per_million_tokens = config.get("credits_per_million_tokens", 0.0)
		credits_per_in_token = config.get("credits_per_in_token", 0.0)
		credits_per_out_token = config.get("credits_per_out_token", 0.0)
		credits_per_million_in_tokens = config.get("credits_per_million_in_tokens", 0.0)
		credits_per_million_out_tokens = config.get("credits_per_million_out_tokens", 0.0)
		credits_per_request = config.get("credits_per_request", 0.0)
		return (credits_per_token, credits_per_million_tokens,
		        credits_per_in_token, credits_per_out_token,
		        credits_per_million_in_tokens, credits_per_million_out_tokens,
		        credits_per_request)

	def _extract_credit_gain_and_max(self, config: dict) -> tuple:
		"""Extract provider-level credit gain and max configuration.

		Returns:
			Tuple of (credit_gains_dict, credit_maxes_dict)
		"""
		credit_gains = {}
		credit_maxes = {}

		for period in ("minute", "hour", "day", "month"):
			gain_key = f"credits_gain_per_{period}"
			max_key = f"credits_max_per_{period}"

			gain = config.get(gain_key, 0.0)
			if gain > 0:
				credit_gains[period] = gain
				# Default max to gain amount if not specified
				credit_maxes[period] = config.get(max_key, gain)

		return credit_gains, credit_maxes

	def _ensure_global_trackers(self, api_keys: list) -> None:
		"""Create global rate limit trackers for API keys if they don't exist."""
		from .models import RateLimitTracker
		for key in api_keys:
			if key not in self.global_key_trackers:
				self.global_key_trackers[key] = RateLimitTracker()

	def load_from_config(self, path: str) -> None:
		"""Load providers and models from YAML configuration."""
		with open(path, "r") as f:
			config = yaml.safe_load(f)

		if not config:
			raise ValueError("Config file is empty")

		# Load providers and store their default rate limits and API keys
		providers_config = config.get("providers", {})
		for provider_name, provider_config in providers_config.items():
			provider_type = provider_config.get("type")

			if provider_type not in PROVIDER_CLASSES:
				raise ValueError(f"Unknown provider type: {provider_type}")

			provider_class = PROVIDER_CLASSES[provider_type]
			provider = provider_class(provider_name, provider_config)
			self.register_provider(provider_name, provider)

			# Store provider-level default rate limits
			provider_defaults = provider_config.get("rate_limits")
			if provider_defaults:
				self.provider_defaults[provider_name] = self._build_rate_limits(provider_defaults)

			# Store provider-level default API keys
			provider_api_keys = provider_config.get("api_keys")
			if provider_api_keys:
				if isinstance(provider_api_keys, list):
					self.provider_api_keys[provider_name] = provider_api_keys
				else:
					self.provider_api_keys[provider_name] = [provider_api_keys]

			# Store provider-level credit gain and max configuration
			credit_gains, credit_maxes = self._extract_credit_gain_and_max(provider_config)
			if credit_gains:
				self.provider_credit_config[provider_name] = (credit_gains, credit_maxes)

		models_config = config.get("models", {})
		for model_id, model_config in models_config.items():
			provider_instances = []

			for provider_name, instance_config in model_config.get("providers", {}).items():
				if provider_name not in self.providers:
					raise ValueError(f"Provider not found: {provider_name}")

				provider = self.providers[provider_name]
				priority = instance_config.get("priority", 0)

				# Support both single model_id and list of model_ids (for round-robin)
				model_id_config = instance_config.get("model_id", model_id)
				if isinstance(model_id_config, list):
					model_ids_for_provider = model_id_config
				else:
					model_ids_for_provider = [model_id_config]

				# Get rate limits with defaults and multiplier support
				provider_defaults = self.provider_defaults.get(provider_name, {})
				instance_limits = self._build_rate_limits(instance_config.get("rate_limits", {}))
				# Multipliers are at instance level
				multiplier = instance_config.get("multiplier", 1.0)
				token_multiplier = instance_config.get("token_multiplier", 1.0)
				in_token_multiplier = instance_config.get("in_token_multiplier", 1.0)
				out_token_multiplier = instance_config.get("out_token_multiplier", 1.0)
				request_multiplier = instance_config.get("request_multiplier", 1.0)

				# Merge: provider defaults + instance overrides + multipliers (for limits)
				rate_limits = self._merge_limits(provider_defaults, instance_limits, multiplier, token_multiplier, request_multiplier)

				# Get API keys: instance config overrides provider defaults
				api_keys_config = instance_config.get("api_keys")
				if not api_keys_config:
					# Fall back to provider-level API keys
					api_keys_config = self.provider_api_keys.get(provider_name)

				api_key_rotation = None

				if api_keys_config:
					if isinstance(api_keys_config, list):
						api_keys = api_keys_config
					else:
						api_keys = [api_keys_config]

					# Ensure global trackers exist for all keys
					self._ensure_global_trackers(api_keys)

					api_key_rotation = ApiKeyRotation(api_keys=api_keys, global_rate_limiters=self.global_key_trackers)

					# Set rate limits (with defaults and multiplier applied)
					if rate_limits:
						api_key_rotation.set_rate_limits(rate_limits)

					# Set usage multipliers (how much each token/request counts)
					if token_multiplier != 1.0 or in_token_multiplier != 1.0 or out_token_multiplier != 1.0 or request_multiplier != 1.0:
						api_key_rotation.set_multipliers(token_multiplier, in_token_multiplier, out_token_multiplier, request_multiplier)

					# Set credit rates if configured
					credit_rates = self._extract_credit_rates(instance_config)
					if any(rate > 0 for rate in credit_rates):
						api_key_rotation.set_credit_rates(*credit_rates)

					# Set provider-level credit gain and max if configured
					if provider_name in self.provider_credit_config:
						credit_gains, credit_maxes = self.provider_credit_config[provider_name]
						api_key_rotation.set_credit_gain_and_max(credit_gains, credit_maxes)
				elif "api_key" in instance_config:
					api_key = instance_config.get("api_key")
					if api_key:
						# Ensure global tracker exists for this key
						self._ensure_global_trackers([api_key])

						api_key_rotation = ApiKeyRotation(api_keys=[api_key], global_rate_limiters=self.global_key_trackers)
						if rate_limits:
							api_key_rotation.set_rate_limits(rate_limits)

						# Set usage multipliers (how much each token/request counts)
						if token_multiplier != 1.0 or in_token_multiplier != 1.0 or out_token_multiplier != 1.0 or request_multiplier != 1.0:
							api_key_rotation.set_multipliers(token_multiplier, in_token_multiplier, out_token_multiplier, request_multiplier)

						# Set credit rates if configured
						credit_rates = self._extract_credit_rates(instance_config)
						if any(rate > 0 for rate in credit_rates):
							api_key_rotation.set_credit_rates(*credit_rates)

						# Set provider-level credit gain and max if configured
						if provider_name in self.provider_credit_config:
							credit_gains, credit_maxes = self.provider_credit_config[provider_name]
							api_key_rotation.set_credit_gain_and_max(credit_gains, credit_maxes)

				pi = ProviderInstance(
					provider=provider,
					priority=priority,
					model_ids=model_ids_for_provider,
					api_key_rotation=api_key_rotation,
					enabled=True,
					max_retries=instance_config.get("max_retries", 3),
				)
				provider_instances.append(pi)

			provider_instances.sort(key=lambda pi: pi.priority)

			model = Model(
				id=model_id,
				provider_instances=provider_instances,
				created=model_config.get("created", 1234567890),
				owned_by=model_config.get("owned_by", "system"),
			)
			self.register_model(model)

		# Load metrics from disk after all models are registered
		self.load_metrics()
