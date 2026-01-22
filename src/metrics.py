"""Metrics persistence for provider performance tracking."""

import json
import time
from pathlib import Path
from typing import Dict, Any


class GlobalMetrics:
	"""Track global system metrics."""

	def __init__(self):
		self.total_requests: int = 0
		self.total_tokens: int = 0
		self.total_prompt_tokens: int = 0
		self.total_completion_tokens: int = 0
		self.total_credits_used: float = 0.0
		self.response_times: list = []  # Keep last 1000 response times
		self.first_token_times: list = []  # TTFT tracking
		self.start_time: float = time.time()
		self.errors_count: int = 0

	def record_request(self, duration: float, tokens: int = 0, prompt_tokens: int = 0,
	                   completion_tokens: int = 0, credits: float = 0.0, ttft: float = 0.0) -> None:
		"""Record a successful request."""
		self.total_requests += 1
		self.total_tokens += tokens
		self.total_prompt_tokens += prompt_tokens
		self.total_completion_tokens += completion_tokens
		self.total_credits_used += credits

		# Keep rolling window of last 1000 response times
		self.response_times.append(duration)
		if len(self.response_times) > 1000:
			self.response_times.pop(0)

		# Track TTFT if provided
		if ttft > 0:
			self.first_token_times.append(ttft)
			if len(self.first_token_times) > 1000:
				self.first_token_times.pop(0)

	def record_error(self) -> None:
		"""Record a failed request."""
		self.errors_count += 1

	def get_average_response_time(self) -> float:
		"""Get average response time in seconds."""
		if not self.response_times:
			return 0.0
		return sum(self.response_times) / len(self.response_times)

	def get_average_ttft(self) -> float:
		"""Get average time to first token in seconds."""
		if not self.first_token_times:
			return 0.0
		return sum(self.first_token_times) / len(self.first_token_times)

	def get_p95_response_time(self) -> float:
		"""Get 95th percentile response time."""
		if not self.response_times:
			return 0.0
		sorted_times = sorted(self.response_times)
		idx = int(len(sorted_times) * 0.95)
		return sorted_times[idx] if idx < len(sorted_times) else sorted_times[-1]

	def get_p95_ttft(self) -> float:
		"""Get 95th percentile TTFT."""
		if not self.first_token_times:
			return 0.0
		sorted_times = sorted(self.first_token_times)
		idx = int(len(sorted_times) * 0.95)
		return sorted_times[idx] if idx < len(sorted_times) else sorted_times[-1]

	def get_uptime_seconds(self) -> float:
		"""Get uptime in seconds."""
		return time.time() - self.start_time

	def to_dict(self) -> Dict[str, Any]:
		"""Convert metrics to dictionary for persistence."""
		return {
			"total_requests": self.total_requests,
			"total_tokens": self.total_tokens,
			"total_prompt_tokens": self.total_prompt_tokens,
			"total_completion_tokens": self.total_completion_tokens,
			"total_credits_used": self.total_credits_used,
			"errors_count": self.errors_count,
			"avg_response_time": self.get_average_response_time(),
			"p95_response_time": self.get_p95_response_time(),
			"avg_ttft": self.get_average_ttft(),
			"p95_ttft": self.get_p95_ttft(),
			"uptime_seconds": self.get_uptime_seconds(),
		}

	def from_dict(self, data: Dict[str, Any]) -> None:
		"""Restore metrics from persisted data."""
		if not data:
			return
		# Note: We don't restore historical response times/ttft lists
		# but we can restore the aggregate counts
		self.total_requests = data.get("total_requests", 0)
		self.total_tokens = data.get("total_tokens", 0)
		self.total_prompt_tokens = data.get("total_prompt_tokens", 0)
		self.total_completion_tokens = data.get("total_completion_tokens", 0)
		self.total_credits_used = data.get("total_credits_used", 0.0)
		self.errors_count = data.get("errors_count", 0)


class MetricsPersistence:
	"""Handle saving and loading provider metrics to/from disk."""

	def __init__(self, metrics_file: str = "metrics/provider_metrics.json", global_metrics_file: str = "metrics/global_metrics.json"):
		self.metrics_file = Path(metrics_file)
		self.global_metrics_file = Path(global_metrics_file)
		self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
		self.global_metrics_file.parent.mkdir(parents=True, exist_ok=True)

	def save_metrics(self, metrics: Dict[str, Any]) -> None:
		"""Save provider metrics to disk."""
		try:
			with open(self.metrics_file, "w") as f:
				json.dump(metrics, f, indent=2)
		except Exception as e:
			print(f"Error saving provider metrics: {e}")

	def load_metrics(self) -> Dict[str, Any]:
		"""Load provider metrics from disk."""
		if not self.metrics_file.exists():
			return {}
		try:
			with open(self.metrics_file, "r") as f:
				return json.load(f)
		except Exception as e:
			print(f"Error loading provider metrics: {e}")
			return {}

	def save_global_metrics(self, global_metrics: GlobalMetrics) -> None:
		"""Save global metrics to disk."""
		try:
			with open(self.global_metrics_file, "w") as f:
				json.dump(global_metrics.to_dict(), f, indent=2)
		except Exception as e:
			print(f"Error saving global metrics: {e}")

	def load_global_metrics(self) -> Dict[str, Any]:
		"""Load global metrics from disk."""
		if not self.global_metrics_file.exists():
			return {}
		try:
			with open(self.global_metrics_file, "r") as f:
				return json.load(f)
		except Exception as e:
			print(f"Error loading global metrics: {e}")
			return {}

	def extract_provider_metrics(self, provider_instance) -> Dict[str, Any]:
		"""Extract metrics from a ProviderInstance for persistence."""
		return {
			"consecutive_failures": provider_instance.consecutive_failures,
			"last_failure": provider_instance.last_failure,
			"circuit_breaker_state": provider_instance.circuit_breaker.state,
			"circuit_breaker_fail_count": provider_instance.circuit_breaker.failure_count,
			"circuit_breaker_success_count": provider_instance.circuit_breaker.success_count,
			"average_response_time": provider_instance.speed_tracker.get_average_time(),
			"p95_response_time": provider_instance.speed_tracker.get_percentile_95(),
		}

	def restore_provider_metrics(self, provider_instance, metrics: Dict[str, Any]) -> None:
		"""Restore metrics from disk to a ProviderInstance."""
		try:
			provider_instance.consecutive_failures = metrics.get("consecutive_failures", 0)
			provider_instance.last_failure = metrics.get("last_failure")

			# Restore circuit breaker state
			cb = provider_instance.circuit_breaker
			cb.state = metrics.get("circuit_breaker_state", "closed")
			cb.fail_count = metrics.get("circuit_breaker_fail_count", 0)
			cb.success_count = metrics.get("circuit_breaker_success_count", 0)
		except Exception as e:
			print(f"Error restoring provider metrics: {e}")
