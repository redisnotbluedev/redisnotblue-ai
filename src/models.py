"""Data models for the proxy server."""

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, List
from collections import deque

if TYPE_CHECKING:
    from providers.base import Provider


@dataclass
class Message:
    """Represents a chat message."""

    role: str
    content: str


@dataclass
class ApiKeyRotation:
    """Manages multiple API keys with round-robin rotation."""

    api_keys: List[str]
    current_index: int = 0
    consecutive_failures: dict = field(default_factory=dict)  # Track failures per key
    disabled_keys: dict = field(default_factory=dict)  # Track disabled keys with timestamps
    cooldown_seconds: int = 600  # 10 minutes

    def __post_init__(self):
        """Initialize failure tracking for all keys."""
        for key in self.api_keys:
            self.consecutive_failures[key] = 0
            self.disabled_keys[key] = None

    def get_next_key(self) -> str:
        """Get the next available API key using round-robin."""
        if not self.api_keys:
            raise ValueError("No API keys configured")

        # Check and re-enable keys if cooldown passed
        self._check_cooldowns()

        # Get available keys (not disabled)
        available_keys = [
            key for key in self.api_keys
            if self.disabled_keys.get(key) is None
        ]

        if not available_keys:
            # All keys disabled, try to re-enable the oldest one
            oldest_key = min(
                self.disabled_keys.items(),
                key=lambda x: x[1] if x[1] else float('inf')
            )[0]
            self.disabled_keys[oldest_key] = None
            self.consecutive_failures[oldest_key] = 0
            available_keys = [oldest_key]

        # Find next available key starting from current index
        found = False
        for _ in range(len(self.api_keys)):
            key = self.api_keys[self.current_index % len(self.api_keys)]
            self.current_index = (self.current_index + 1) % len(self.api_keys)

            if key in available_keys:
                found = True
                return key

        # Fallback (shouldn't happen)
        return available_keys[0]

    def mark_failure(self, api_key: str) -> None:
        """Mark an API key as having failed."""
        if api_key not in self.api_keys:
            return

        self.consecutive_failures[api_key] += 1
        self.disabled_keys[api_key] = time.time()

        if self.consecutive_failures[api_key] >= 3:
            # Keep it disabled
            pass

    def mark_success(self, api_key: str) -> None:
        """Mark an API key as having succeeded."""
        if api_key not in self.api_keys:
            return

        self.consecutive_failures[api_key] = 0
        self.disabled_keys[api_key] = None

    def _check_cooldowns(self) -> None:
        """Check if any disabled keys can be re-enabled."""
        current_time = time.time()

        for key, disabled_time in self.disabled_keys.items():
            if disabled_time is None:
                continue

            if current_time - disabled_time >= self.cooldown_seconds:
                self.disabled_keys[key] = None
                self.consecutive_failures[key] = 0

    def get_status(self) -> dict:
        """Get status of all API keys."""
        self._check_cooldowns()
        return {
            "total_keys": len(self.api_keys),
            "available_keys": sum(
                1 for key in self.api_keys
                if self.disabled_keys.get(key) is None
            ),
            "keys": [
                {
                    "index": i,
                    "failures": self.consecutive_failures.get(key, 0),
                    "enabled": self.disabled_keys.get(key) is None,
                    "disabled_since": self.disabled_keys.get(key),
                }
                for i, key in enumerate(self.api_keys)
            ]
        }


@dataclass
class ProviderInstance:
    """Represents a provider instance for a specific model."""

    provider: "Provider"
    priority: int
    model_id: str
    api_key_rotation: Optional[ApiKeyRotation] = None
    enabled: bool = True
    consecutive_failures: int = 0
    last_failure: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3

    def mark_failure(self) -> None:
        """Mark a failure and potentially disable the provider."""
        self.consecutive_failures += 1
        self.last_failure = time.time()
        if self.consecutive_failures >= 3:
            self.enabled = False

    def mark_success(self) -> None:
        """Mark a success and reset failure counter."""
        self.consecutive_failures = 0
        self.last_failure = None

    def should_retry(self, cooldown_seconds: int = 600) -> bool:
        """Check if enough time has passed to retry a failed provider."""
        if not self.last_failure:
            return True
        return time.time() - self.last_failure >= cooldown_seconds

    def should_attempt_request(self) -> bool:
        """Check if we should attempt a request with this provider."""
        return self.enabled and self.should_retry()

    def get_current_api_key(self) -> Optional[str]:
        """Get the current API key for this provider."""
        if self.api_key_rotation is None:
            return None
        return self.api_key_rotation.get_next_key()

    def mark_api_key_failure(self, api_key: str) -> None:
        """Mark an API key as having failed."""
        if self.api_key_rotation:
            self.api_key_rotation.mark_failure(api_key)

    def mark_api_key_success(self, api_key: str) -> None:
        """Mark an API key as having succeeded."""
        if self.api_key_rotation:
            self.api_key_rotation.mark_success(api_key)

    def increment_retry_count(self) -> None:
        """Increment the retry counter."""
        self.retry_count += 1

    def reset_retry_count(self) -> None:
        """Reset the retry counter."""
        self.retry_count = 0

    def should_retry_request(self) -> bool:
        """Check if we should retry the request."""
        return self.retry_count < self.max_retries


@dataclass
class Model:
    """Represents a model available through the proxy."""

    id: str
    provider_instances: list[ProviderInstance] = field(default_factory=list)
    created: int = 1234567890
    owned_by: str = "system"

    def get_available_providers(self) -> list[ProviderInstance]:
        """Return enabled providers sorted by priority."""
        available = [
            pi
            for pi in self.provider_instances
            if pi.enabled or pi.should_retry()
        ]
        # Re-enable if cooldown has passed
        for pi in available:
            if not pi.enabled and pi.should_retry():
                pi.enabled = True
        return sorted(available, key=lambda pi: pi.priority)

    def to_dict(self) -> dict:
        """Return dict matching OpenAI model object format."""
        return {
            "id": self.id,
            "object": "model",
            "created": self.created,
            "owned_by": self.owned_by,
        }