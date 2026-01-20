"""Model registry for managing providers and models."""

import yaml
from typing import Optional, Dict
from models import Model, ProviderInstance, Message
from providers.base import Provider
from providers.openai import OpenAIProvider


# Mapping of provider names to their classes
PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
}


class ModelRegistry:
    """Registry for managing models and their provider instances."""

    def __init__(self) -> None:
        """Initialize the registry."""
        self.models: Dict[str, Model] = {}
        self.providers: Dict[str, Provider] = {}

    def register_provider(self, name: str, provider: Provider) -> None:
        """Register a provider instance.
        
        Args:
            name: Provider name (e.g., "openai", "openai-backup")
            provider: Provider instance
        """
        self.providers[name] = provider

    def register_model(self, model: Model) -> None:
        """Register a model.
        
        Args:
            model: Model instance
        """
        self.models[model.id] = model

    def get_model(self, model_id: str) -> Optional[Model]:
        """Get a model by ID.
        
        Args:
            model_id: Model ID
            
        Returns:
            Model instance or None if not found
        """
        return self.models.get(model_id)

    def list_models(self) -> list[Model]:
        """Get all registered models.
        
        Returns:
            List of Model instances
        """
        return list(self.models.values())

    def load_from_config(self, path: str) -> None:
        """Load providers and models from YAML configuration file.
        
        Args:
            path: Path to YAML config file
            
        Raises:
            ValueError: If config is invalid
            FileNotFoundError: If config file not found
        """
        with open(path, "r") as f:
            config = yaml.safe_load(f)

        if not config:
            raise ValueError("Config file is empty")

        # Load providers first
        providers_config = config.get("providers", {})
        for provider_name, provider_config in providers_config.items():
            provider_type = provider_config.get("type")

            if provider_type not in PROVIDER_CLASSES:
                raise ValueError(f"Unknown provider type: {provider_type}")

            provider_class = PROVIDER_CLASSES[provider_type]
            provider = provider_class(provider_name, provider_config)
            self.register_provider(provider_name, provider)

        # Load models
        models_config = config.get("models", {})
        for model_id, model_config in models_config.items():
            provider_instances = []

            # Create provider instances for this model
            for provider_name, instance_config in model_config.get(
                "providers", {}
            ).items():
                if provider_name not in self.providers:
                    raise ValueError(f"Provider not found: {provider_name}")

                provider = self.providers[provider_name]
                priority = instance_config.get("priority", 0)
                model_id_for_provider = instance_config.get(
                    "model_id", model_id
                )  # Default to unified model_id

                pi = ProviderInstance(
                    provider=provider,
                    priority=priority,
                    model_id=model_id_for_provider,
                    enabled=True,
                )
                provider_instances.append(pi)

            # Sort by priority
            provider_instances.sort(key=lambda pi: pi.priority)

            model = Model(
                id=model_id,
                provider_instances=provider_instances,
                created=model_config.get("created", 1234567890),
                owned_by=model_config.get("owned_by", "system"),
            )
            self.register_model(model)