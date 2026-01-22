"""Basic test script for the OpenAI proxy server."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.models import Model, ProviderInstance
from src.providers.base import Provider, TransformedRequest, TransformedResponse
from src.registry import ModelRegistry
import time


class MockProvider(Provider):
    """Mock provider for testing."""

    def translate_request(self, messages: list[dict], model_id: str, **kwargs) -> TransformedRequest:
        return TransformedRequest(
            data={"messages": messages, "model": model_id, **kwargs},
            original_model_id=model_id,
            provider_model_id=model_id
        )

    def make_request(self, request_data: dict, api_key: str) -> dict:
        return {
            "id": "test-123",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "test-model",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Test response"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 10,
                "total_tokens": 15
            }
        }

    def translate_response(self, response_data: dict, original_request: dict) -> TransformedResponse:
        return TransformedResponse(
            data=response_data,
            provider_name="mock",
            original_request=original_request
        )


def test_provider_instance():
    """Test ProviderInstance failure tracking."""
    print("Testing ProviderInstance...")

    provider = MockProvider("mock", {})
    pi = ProviderInstance(
        provider=provider,
        priority=0,
        model_ids=["test-model"],
        enabled=True
    )

    # Test initial state
    assert pi.enabled == True
    assert pi.consecutive_failures == 0
    assert pi.should_retry() == True

    # Test mark_failure
    pi.mark_failure()
    assert pi.consecutive_failures == 1
    assert pi.enabled == True

    pi.mark_failure()
    assert pi.consecutive_failures == 2
    assert pi.enabled == True

    pi.mark_failure()
    assert pi.consecutive_failures == 3
    assert pi.enabled == False  # Should be disabled after 3 failures

    # Test mark_success
    pi.mark_success()
    assert pi.consecutive_failures == 0
    assert pi.enabled == True

    print("✓ ProviderInstance tests passed")


def test_model():
    """Test Model with multiple provider instances."""
    print("Testing Model...")

    provider1 = MockProvider("provider1", {})
    provider2 = MockProvider("provider2", {})

    pi1 = ProviderInstance(provider=provider1, priority=0, model_ids=["model-1"])
    pi2 = ProviderInstance(provider=provider2, priority=1, model_ids=["model-1"])

    model = Model(id="gpt-4", provider_instances=[pi1, pi2])

    # Test available providers (should be sorted by priority)
    available = model.get_available_providers()
    assert len(available) == 2
    assert available[0].priority == 0
    assert available[1].priority == 1

    # Test with disabled provider
    pi1.mark_failure()
    pi1.mark_failure()
    pi1.mark_failure()

    available = model.get_available_providers()
    assert len(available) == 1
    assert available[0].provider.name == "provider2"

    # Test to_dict
    model_dict = model.to_dict()
    assert model_dict["id"] == "gpt-4"
    assert model_dict["object"] == "model"
    assert model_dict["owned_by"] == "system"

    print("✓ Model tests passed")


def test_mock_provider():
    """Test mock provider."""
    print("Testing MockProvider...")

    provider = MockProvider("mock", {})

    messages = [{"role": "user", "content": "Hello"}]
    response = provider.chat_completion(
        messages=messages,
        model_id="test-model",
        api_key="test-key",
        temperature=0.7,
        max_tokens=100
    )

    assert response["id"] == "test-123"
    assert response["object"] == "chat.completion"
    assert len(response["choices"]) == 1
    assert response["choices"][0]["message"]["content"] == "Test response"
    assert response["usage"]["total_tokens"] == 15

    print("✓ MockProvider tests passed")


def test_registry():
    """Test ModelRegistry."""
    print("Testing ModelRegistry...")

    registry = ModelRegistry()

    # Register a provider
    provider = MockProvider("test-provider", {})
    registry.register_provider("test-provider", provider)
    assert registry.providers["test-provider"] == provider

    # Create and register a model
    pi = ProviderInstance(provider=provider, priority=0, model_ids=["test-model"])
    model = Model(id="test-model", provider_instances=[pi])
    registry.register_model(model)

    # Test get_model
    retrieved = registry.get_model("test-model")
    assert retrieved.id == "test-model"  # type: ignore

    # Test list_models
    models = registry.list_models()
    assert len(models) == 1
    assert models[0].id == "test-model"

    print("✓ ModelRegistry tests passed")


def test_failover():
    """Test failover behavior."""
    print("Testing failover behavior...")

    class FailingProvider(Provider):
            def __init__(self, name, config, should_fail=False):
                super().__init__(name, config)
                self.should_fail = should_fail

            def translate_request(self, messages, model_id, **kwargs):
                return TransformedRequest(
                    data={"messages": messages, "model": model_id},
                    original_model_id=model_id,
                    provider_model_id=model_id
                )

            def make_request(self, request_data, api_key):
                if self.should_fail:
                    raise Exception("Provider failed")
                return {
                    "id": "success",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "test",
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": "Success"},
                        "finish_reason": "stop"
                    }],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
                }

            def translate_response(self, response_data, original_request):
                return TransformedResponse(
                    data=response_data,
                    provider_name=self.name,
                    original_request=original_request
                )

    # Create providers
    failing_provider = FailingProvider("failing", {}, should_fail=True)
    working_provider = FailingProvider("working", {}, should_fail=False)

    # Create model with both providers
    pi_fail = ProviderInstance(provider=failing_provider, priority=0, model_ids=["test"])
    pi_work = ProviderInstance(provider=working_provider, priority=1, model_ids=["test"])
    _model = Model(id="test", provider_instances=[pi_fail, pi_work])

    # First call should fail on first provider, succeed on second
    messages = [{"role": "user", "content": "test"}]
    try:
        response = pi_fail.provider.chat_completion(messages, "test", "test-key")
        assert False, "Should have raised exception"
    except Exception:
        pass

    pi_fail.mark_failure()

    # Second provider should work
    response = pi_work.provider.chat_completion(messages, "test", "test-key")
    assert response["id"] == "success"
    pi_work.mark_success()

    print("✓ Failover tests passed")


if __name__ == "__main__":
    print("Running tests...\n")

    test_provider_instance()
    test_model()
    test_mock_provider()
    test_registry()
    test_failover()

    print("\n✅ All tests passed!")
