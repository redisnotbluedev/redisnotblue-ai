"""Model registry for managing providers and models."""

import yaml
from typing import Optional, Dict
from models import Model, ProviderInstance, ApiKeyRotation
from providers.base import Provider
from providers.openai import OpenAIProvider


PROVIDER_CLASSES = {
	"openai": OpenAIProvider,
}


class ModelRegistry:
	"""Registry for managing models and their provider instances."""

	def __init__(self):
		self.models: Dict[str, Model] = {}
		self.providers: Dict[str, Provider] = {}

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

	def load_from_config(self, path: str) -> None:
		"""Load providers and models from YAML configuration."""
		with open(path, "r") as f:
			config = yaml.safe_load(f)

		if not config:
			raise ValueError("Config file is empty")

		providers_config = config.get("providers", {})
		for provider_name, provider_config in providers_config.items():
			provider_type = provider_config.get("type")

			if provider_type not in PROVIDER_CLASSES:
				raise ValueError(f"Unknown provider type: {provider_type}")

			provider_class = PROVIDER_CLASSES[provider_type]
			provider = provider_class(provider_name, provider_config)
			self.register_provider(provider_name, provider)

		models_config = config.get("models", {})
		for model_id, model_config in models_config.items():
			provider_instances = []

			for provider_name, instance_config in model_config.get("providers", {}).items():
				if provider_name not in self.providers:
					raise ValueError(f"Provider not found: {provider_name}")

				provider = self.providers[provider_name]
				priority = instance_config.get("priority", 0)
				model_id_for_provider = instance_config.get("model_id", model_id)

				api_keys_config = instance_config.get("api_keys")
				api_key_rotation = None

				if api_keys_config:
					if isinstance(api_keys_config, list):
						api_keys = api_keys_config
					else:
						api_keys = [api_keys_config]
					api_key_rotation = ApiKeyRotation(api_keys=api_keys)
				elif "api_key" in instance_config:
					api_key = instance_config.get("api_key")
					if api_key:
						api_key_rotation = ApiKeyRotation(api_keys=[api_key])

				pi = ProviderInstance(
					provider=provider,
					priority=priority,
					model_id=model_id_for_provider,
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