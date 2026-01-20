"""Model registry for managing providers and models."""

import yaml
from typing import Optional, Dict
from models import Model, ProviderInstance, Message, ApiKeyRotation
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
                )

                # Get API keys - can be a single key or list of keys
                api_keys_config = instance_config.get("api_keys")
                api_key_rotation = None
                
                if api_keys_config:
                    # Multiple API keys provided
                    if isinstance(api_keys_config, list):
                        api_keys = api_keys_config
                    else:
                        api_keys = [api_keys_config]
                    
                    api_key_rotation = ApiKeyRotation(api_keys=api_keys)
                
                # Fallback to single api_key if provided (for backward compatibility)
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

            # Sort by priority
            provider_instances.sort(key=lambda pi: pi.priority)

            model = Model(
                id=model_id,
                provider_instances=provider_instances,
                created=model_config.get("created", 1234567890),
                owned_by=model_config.get("owned_by", "system"),
            )
            self.register_model(model)

    def get_provider_status(self) -> dict:
        """Get status of all providers and their API keys.
        
        Returns:
            Dictionary with provider and API key status
        """
        status = {}
        
        for model_id, model in self.models.items():
            model_status = {}
            
            for pi in model.provider_instances:
                provider_name = pi.provider.name
                key = f"{provider_name}:{pi.model_id}"
                
                key_status = {
                    "enabled": pi.enabled,
                    "priority": pi.priority,
                    "consecutive_failures": pi.consecutive_failures,
                    "retry_count": pi.retry_count,
                    "max_retries": pi.max_retries,
                }
                
                if pi.api_key_rotation:
                    key_status["api_key_status"] = pi.api_key_rotation.get_status()
                
                model_status[key] = key_status
            
            status[model_id] = model_status
        
        return status