"""Metrics persistence for provider performance tracking."""

import json
import time
from pathlib import Path
from typing import Dict, Any


class GlobalMetrics:
	"""Track global system metrics with advanced analytics."""

	def __init__(self, on_change=None):
		self.total_requests: int = 0
		self.total_tokens: int = 0
		self.total_prompt_tokens: int = 0
		self.total_completion_tokens: int = 0
		self.total_credits_used: float = 0.0
		self.response_times: list = []  # Keep last 1000 response times
		self.first_token_times: list = []  # TTFT tracking
		self.start_time: float = time.time()
		self.errors_count: int = 0
		self.on_change = on_change  # Callback when metrics change

		# Advanced analytics fields
		self.request_timestamps: list = []  # Timestamps for time-series analysis
		self.error_timestamps: list = []  # Error timestamps for anomaly detection
		self.cost_history: list = []  # Cost per request history
		self.performance_history: list = []  # (timestamp, response_time, tokens) tuples
		self.anomaly_scores: list = []  # Rolling anomaly detection scores
		self.baseline_metrics: dict = {}  # Baseline performance metrics
		self.trend_analysis: dict = {}  # Performance trend data

	def record_request(self, duration: float, tokens: int = 0, prompt_tokens: int = 0,
	                   completion_tokens: int = 0, credits: float = 0.0, ttft: float = 0.0) -> None:
		"""Record a successful request."""
		current_time = time.time()
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

		# Advanced analytics tracking
		self.request_timestamps.append(current_time)
		if len(self.request_timestamps) > 1000:
			self.request_timestamps.pop(0)

		if credits > 0:
			self.cost_history.append(credits)
			if len(self.cost_history) > 1000:
				self.cost_history.pop(0)

		self.performance_history.append((current_time, duration, tokens))
		if len(self.performance_history) > 1000:
			self.performance_history.pop(0)

		# Update baseline metrics periodically
		if self.total_requests % 100 == 0:
			self.update_baseline_metrics()

		# Trigger save callback
		if self.on_change:
			self.on_change()

	def record_error(self) -> None:
		"""Record a failed request."""
		current_time = time.time()
		self.errors_count += 1

		# Advanced analytics tracking
		self.error_timestamps.append(current_time)
		if len(self.error_timestamps) > 1000:
			self.error_timestamps.pop(0)

		# Trigger save callback
		if self.on_change:
			self.on_change()

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
			"baseline_metrics": self.baseline_metrics,
			"trend_analysis": self.trend_analysis,
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
		self.baseline_metrics = data.get("baseline_metrics", {})
		self.trend_analysis = data.get("trend_analysis", {})

	# Advanced Analytics Methods

	def detect_anomalies(self, window_size: int = 50) -> list:
		"""Detect anomalies in response times using statistical methods.

		Returns:
			List of (timestamp, response_time, anomaly_score) tuples for detected anomalies
		"""
		if len(self.response_times) < window_size:
			return []

		anomalies = []
		recent_times = self.response_times[-window_size:]
		mean = sum(recent_times) / len(recent_times)
		std_dev = (sum((x - mean) ** 2 for x in recent_times) / len(recent_times)) ** 0.5

		threshold = mean + 3 * std_dev  # 3-sigma rule

		for i, response_time in enumerate(self.response_times[-window_size:]):
			if response_time > threshold:
				timestamp = self.request_timestamps[-(window_size - i)] if len(self.request_timestamps) >= window_size else time.time()
				anomaly_score = (response_time - mean) / std_dev if std_dev > 0 else 0
				anomalies.append((timestamp, response_time, anomaly_score))

		return anomalies

	def predict_future_load(self, minutes_ahead: int = 5) -> dict:
		"""Predict future system load based on recent trends.

		Returns:
			Dict with predicted requests_per_minute, tokens_per_minute, etc.
		"""
		if len(self.request_timestamps) < 10:
			return {"requests_per_minute": 0, "tokens_per_minute": 0, "confidence": 0}

		# Simple linear regression on request intervals
		timestamps = self.request_timestamps[-100:]  # Last 100 requests
		if len(timestamps) < 2:
			return {"requests_per_minute": 0, "tokens_per_minute": 0, "confidence": 0}

		# Calculate request rate
		time_span = timestamps[-1] - timestamps[0]
		request_rate = len(timestamps) / (time_span / 60) if time_span > 0 else 0

		# Calculate token rate
		recent_tokens = self.performance_history[-len(timestamps):]
		total_tokens = sum(t[2] for t in recent_tokens if len(t) > 2)
		token_rate = total_tokens / (time_span / 60) if time_span > 0 else 0

		# Simple prediction: assume current rate continues
		predicted_requests = request_rate
		predicted_tokens = token_rate

		# Confidence based on data points
		confidence = min(len(timestamps) / 50, 1.0)

		return {
			"requests_per_minute": predicted_requests,
			"tokens_per_minute": predicted_tokens,
			"confidence": confidence
		}

	def calculate_cost_efficiency(self) -> dict:
		"""Calculate cost efficiency metrics.

		Returns:
			Dict with cost per token, cost per request, efficiency trends
		"""
		if self.total_requests == 0 or self.total_credits_used == 0:
			return {"cost_per_token": 0, "cost_per_request": 0, "efficiency_trend": "insufficient_data"}

		cost_per_token = self.total_credits_used / self.total_tokens if self.total_tokens > 0 else 0
		cost_per_request = self.total_credits_used / self.total_requests

		# Analyze efficiency trend (are costs decreasing over time?)
		if len(self.cost_history) >= 10:
			recent_avg = sum(self.cost_history[-10:]) / 10
			older_avg = sum(self.cost_history[-20:-10]) / 10 if len(self.cost_history) >= 20 else recent_avg
			if older_avg > 0:
				trend = (recent_avg - older_avg) / older_avg
				if trend < -0.05:
					efficiency_trend = "improving"
				elif trend > 0.05:
					efficiency_trend = "decreasing"
				else:
					efficiency_trend = "stable"
			else:
				efficiency_trend = "stable"
		else:
			efficiency_trend = "insufficient_data"

		return {
			"cost_per_token": cost_per_token,
			"cost_per_request": cost_per_request,
			"efficiency_trend": efficiency_trend
		}

	def get_performance_trends(self) -> dict:
		"""Analyze performance trends over time.

		Returns:
			Dict with trend analysis for response times, errors, throughput
		"""
		if len(self.performance_history) < 20:
			return {"response_time_trend": "insufficient_data", "error_rate_trend": "insufficient_data", "throughput_trend": "insufficient_data"}

		# Split data into two halves for comparison
		half_point = len(self.performance_history) // 2
		first_half = self.performance_history[:half_point]
		second_half = self.performance_history[half_point:]

		# Response time trend
		first_avg_rt = sum(t[1] for t in first_half) / len(first_half)
		second_avg_rt = sum(t[1] for t in second_half) / len(second_half)
		rt_trend = "stable"
		if second_avg_rt < first_avg_rt * 0.95:
			rt_trend = "improving"
		elif second_avg_rt > first_avg_rt * 1.05:
			rt_trend = "degrading"

		# Error rate trend (using error timestamps)
		total_first = len(first_half)
		total_second = len(second_half)
		errors_first = sum(1 for t in self.error_timestamps if any(abs(t - p[0]) < 300 for p in first_half))  # Within 5 min
		errors_second = sum(1 for t in self.error_timestamps if any(abs(t - p[0]) < 300 for p in second_half))
		error_rate_first = errors_first / total_first if total_first > 0 else 0
		error_rate_second = errors_second / total_second if total_second > 0 else 0
		error_trend = "stable"
		if error_rate_second < error_rate_first * 0.8:
			error_trend = "improving"
		elif error_rate_second > error_rate_first * 1.2:
			error_trend = "degrading"

		# Throughput trend (requests per minute)
		time_first = first_half[-1][0] - first_half[0][0] if first_half else 1
		time_second = second_half[-1][0] - second_half[0][0] if second_half else 1
		throughput_first = len(first_half) / (time_first / 60)
		throughput_second = len(second_half) / (time_second / 60)
		throughput_trend = "stable"
		if throughput_second > throughput_first * 1.1:
			throughput_trend = "increasing"
		elif throughput_second < throughput_first * 0.9:
			throughput_trend = "decreasing"

		return {
			"response_time_trend": rt_trend,
			"error_rate_trend": error_trend,
			"throughput_trend": throughput_trend
		}

	def update_baseline_metrics(self) -> None:
		"""Update baseline performance metrics for anomaly detection."""
		if len(self.response_times) >= 100:
			self.baseline_metrics = {
				"avg_response_time": self.get_average_response_time(),
				"p95_response_time": self.get_p95_response_time(),
				"avg_ttft": self.get_average_ttft(),
				"p95_ttft": self.get_p95_ttft(),
				"error_rate": self.errors_count / self.total_requests if self.total_requests > 0 else 0,
				"last_updated": time.time()
			}


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
			"tokens_per_second": provider_instance.speed_tracker.get_tokens_per_second(),
			"average_ttft": provider_instance.speed_tracker.get_average_ttft(),
			"p95_ttft": provider_instance.speed_tracker.get_p95_ttft(),
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

			# Restore persisted speed tracker aggregates
			st = provider_instance.speed_tracker
			st.persisted_avg_time = metrics.get("average_response_time", 0.0)
			st.persisted_p95 = metrics.get("p95_response_time", 0.0)
			st.persisted_tokens_per_sec = metrics.get("tokens_per_second", 0.0)
			st.persisted_avg_ttft = metrics.get("average_ttft", 0.0)
			st.persisted_p95_ttft = metrics.get("p95_ttft", 0.0)
		except Exception as e:
			print(f"Error restoring provider metrics: {e}")
