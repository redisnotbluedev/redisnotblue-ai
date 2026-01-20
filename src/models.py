from dataclasses import dataclass, field
from typing import Optional, List
import time


@dataclass
class Message:
    """Represents a chat message."""
    role: str
    content: str


@dataclass
class ProviderInstance:
    """Represents a provider instance for a specific model."""
    provider: 'Provider'  # Type hint as string to avoid circular import
    priority: int
    model_id: str
    enabled: bool = True
    consecutive_failures: int = 0
    last_failure: Optional[float] = None

    def mark_failure(self) -> None:
        """Mark this provider instance as having failed."""
        self.consecutive_failures += 1
        self.last_failure = time.time()
        if self.consecutive_failures >= 3:
            self.enabled = False

    def mark_success(self) -> None:
        """Mark this provider instance as having succeeded."""
        self.consecutive_failures = 0
        self.last_failure = None
        self.enabled = True

    def should_retry(self, cooldown_seconds: int = 600) -> bool:
        """Check if enough time has passed to retry this provider."""
        if self.enabled:
            return True
        if self.last_failure is None:
            return True
        time_since_failure = time.time() - self.last_failure
        return time_since_failure >= cooldown_seconds


@dataclass
class Model:
    """Represents a unified model with multiple provider instances."""
    id: str
    provider_instances: List[ProviderInstance] = field(default_factory=list)
    created: int = 1234567890
    owned_by: str = "system"

    def get_available_providers(self) -> List[ProviderInstance]:
        """Return enabled providers sorted by priority."""
        available = [
            pi for pi in self.provider_instances
            if pi.enabled and pi.should_retry()
        ]
        return sorted(available, key=lambda x: x.priority)

    def to_dict(self) -> dict:
        """Return dict matching OpenAI model object format."""
        return {
            "id": self.id,
            "object": "model",
            "created": self.created,
            "owned_by": self.owned_by,
        }