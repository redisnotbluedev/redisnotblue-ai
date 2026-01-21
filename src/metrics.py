"""Metrics persistence for provider performance tracking."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


class MetricsPersistence:
	"""Handle saving and loading provider metrics to/from disk."""

	def __init__(self, metrics_file: str = "metrics/provider_metrics.json"):
		self.metrics_file = Path(metrics_file)
		self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

	def save_metrics(self, metrics: Dict[str, Any]) -> None:
		"""Save provider metrics to disk."""
		try:
			with open(self.metrics_file, "w") as f:
				json.dump(metrics, f, indent=2)
		except Exception as e:
			print(f"Error saving metrics: {e}")

	def load_metrics(self) -> Dict[str, Any]:
		"""Load provider metrics from disk."""
		if not self.metrics_file.exists():
			return {}
		try:
			with open(self.metrics_file, "r") as f:
				return json.load(f)
		except Exception as e:
			print(f"Error loading metrics: {e}")
			return {}

	def extract_provider_metrics(self, provider_instance: "ProviderInstance") -> Dict[str, Any]:
		"""Extract metrics from a ProviderInstance for persistence."""
		return {
			"consecutive_failures": provider_instance.consecutive_failures,
			"last_failure": provider_instance.last_failure,
			"circuit_breaker_state": provider_instance.circuit_breaker.state,
			"circuit_breaker_fail_count": provider_instance.circuit_breaker.fail_count,
			"circuit_breaker_success_count": provider_instance.circuit_breaker.success_count,
			"average_response_time": provider_instance.speed_tracker.get_average_time(),
			"p95_response_time": provider_instance.speed_tracker.get_percentile_95(),
		}

	def restore_provider_metrics(self, provider_instance: "ProviderInstance", metrics: Dict[str, Any]) -> None:
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
			print(f"Error restoring metrics: {e}")