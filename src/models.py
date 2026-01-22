"""Data models for the proxy server."""

import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
	from .providers.base import Provider

@dataclass
class Message:
	"""Represents a chat message."""
	role: str
	content: str


@dataclass
class RateLimitTracker:
	"""Tracks rate limiting and usage for an API key with flexible time periods."""
	limits: dict = field(default_factory=dict)  # {"requests_per_minute": 3500, "tokens_per_hour": 90000, "credits_per_day": 1000, ...}
	requests: List[float] = field(default_factory=list)
	token_usage: List[tuple] = field(default_factory=list)  # Total tokens (prompt + completion)
	prompt_token_usage: List[tuple] = field(default_factory=list)  # Prompt tokens only
	completion_token_usage: List[tuple] = field(default_factory=list)  # Completion tokens only
	credit_usage: List[tuple] = field(default_factory=list)  # (timestamp, credits) - for time-window tracking
	calendar_credits: dict = field(default_factory=dict)  # {period: credits_used} for calendar-based resets
	calendar_reset_times: dict = field(default_factory=dict)  # {period: next_reset_timestamp}
	token_multiplier: float = 1.0  # How much each token counts (e.g., 2.0 = counts as 2x)
	request_multiplier: float = 1.0  # How much each request counts (e.g., 2.0 = counts as 2x)
	credits_per_token: float = 0.0  # How many credits per token (0 = disabled)
	credits_per_million_tokens: float = 0.0  # How many credits per million tokens (0 = disabled)
	credits_per_request: float = 0.0  # How many credits per request (0 = disabled)

	def add_request(self, tokens: int = 0, prompt_tokens: int = 0, completion_tokens: int = 0, credits: float = 0.0) -> None:
		"""Record a request. Applies multipliers to token/request counting.
		
		Args:
			tokens: Total tokens (legacy, used if prompt_tokens/completion_tokens not provided)
			prompt_tokens: Number of prompt tokens
			completion_tokens: Number of completion tokens
			credits: Credits used (pre-calculated, or will be calculated from tokens)
		"""
		current_time = time.time()
		# Apply request multiplier
		for _ in range(int(self.request_multiplier)):
			self.requests.append(current_time)
		if len(self.requests) > 1000:
			self.requests.pop(0)
		
		# Calculate total tokens for credit computation
		total_tokens = 0
		
		# Track tokens
		if prompt_tokens > 0 or completion_tokens > 0:
			# Use separate prompt/completion tracking
			if prompt_tokens > 0:
				counted_prompt = int(prompt_tokens * self.token_multiplier)
				self.prompt_token_usage.append((current_time, counted_prompt))
				if len(self.prompt_token_usage) > 1000:
					self.prompt_token_usage.pop(0)
			
			if completion_tokens > 0:
				counted_completion = int(completion_tokens * self.token_multiplier)
				self.completion_token_usage.append((current_time, counted_completion))
				if len(self.completion_token_usage) > 1000:
					self.completion_token_usage.pop(0)
			
			# Also track total for legacy limits
			total = prompt_tokens + completion_tokens
			if total > 0:
				counted_total = int(total * self.token_multiplier)
				self.token_usage.append((current_time, counted_total))
				if len(self.token_usage) > 1000:
					self.token_usage.pop(0)
				total_tokens = counted_total
		elif tokens > 0:
			# Legacy: use total tokens parameter
			counted_tokens = int(tokens * self.token_multiplier)
			self.token_usage.append((current_time, counted_tokens))
			if len(self.token_usage) > 1000:
				self.token_usage.pop(0)
			total_tokens = counted_tokens
		
		# Track credits
		self._record_credits(current_time, total_tokens, credits)

	def _get_time_window_seconds(self, period: str) -> int:
		"""Get the time window in seconds for a period."""
		windows = {
			"minute": 60,
			"hour": 3600,
			"day": 86400,
			"month": 2592000,  # 30 days
		}
		return windows.get(period, 60)

	def _count_in_window(self, items: List[float], window_seconds: int) -> int:
		"""Count items in the specified time window."""
		current_time = time.time()
		return sum(1 for t in items if current_time - t < window_seconds)

	def _count_tokens_in_window(self, window_seconds: int) -> int:
		"""Count total tokens used in the specified time window."""
		current_time = time.time()
		return sum(tokens for t, tokens in self.token_usage if current_time - t < window_seconds)

	def _count_prompt_tokens_in_window(self, window_seconds: int) -> int:
		"""Count prompt tokens used in the specified time window."""
		current_time = time.time()
		return sum(tokens for t, tokens in self.prompt_token_usage if current_time - t < window_seconds)

	def _count_completion_tokens_in_window(self, window_seconds: int) -> int:
		"""Count completion tokens used in the specified time window."""
		current_time = time.time()
		return sum(tokens for t, tokens in self.completion_token_usage if current_time - t < window_seconds)

	def is_rate_limited(self) -> bool:
		"""Check if rate limited by any configured limit."""
		for limit_key, limit_value in self.limits.items():
			if "_per_" not in limit_key:
				continue

			parts = limit_key.split("_per_")
			if len(parts) != 2:
				continue

			limit_type, period = parts
			window_seconds = self._get_time_window_seconds(period)

			if limit_type == "requests":
				count = self._count_in_window(self.requests, window_seconds)
				if count >= limit_value:
					return True

			elif limit_type == "tokens":
				count = self._count_tokens_in_window(window_seconds)
				if count >= limit_value:
					return True

			elif limit_type == "prompt_tokens":
				count = self._count_prompt_tokens_in_window(window_seconds)
				if count >= limit_value:
					return True

			elif limit_type == "completion_tokens":
				count = self._count_completion_tokens_in_window(window_seconds)
				if count >= limit_value:
					return True

			elif limit_type == "credits":
				# Use calendar-based resets for credit limits
				count = self._get_calendar_credits(period)
				if count >= limit_value:
					return True

		return False

	def get_usage_stats(self) -> dict:
		"""Get current usage statistics across all configured limits."""
		stats = {}

		for limit_key, limit_value in self.limits.items():
			if "_per_" not in limit_key:
				continue

			parts = limit_key.split("_per_")
			if len(parts) != 2:
				continue

			limit_type, period = parts
			window_seconds = self._get_time_window_seconds(period)

			if limit_type == "requests":
				count = self._count_in_window(self.requests, window_seconds)
				stats[limit_key] = {"used": count, "limit": limit_value}

			elif limit_type == "tokens":
				count = self._count_tokens_in_window(window_seconds)
				stats[limit_key] = {"used": count, "limit": limit_value}

			elif limit_type == "prompt_tokens":
				count = self._count_prompt_tokens_in_window(window_seconds)
				stats[limit_key] = {"used": count, "limit": limit_value}

			elif limit_type == "completion_tokens":
				count = self._count_completion_tokens_in_window(window_seconds)
				stats[limit_key] = {"used": count, "limit": limit_value}

			elif limit_type == "credits":
				count = self._get_calendar_credits(period)
				stats[limit_key] = {"used": count, "limit": limit_value}

		return stats

	def _get_calendar_reset_time(self, period: str, now: datetime) -> datetime:
		"""Calculate the next calendar reset time for a period.
		
		Args:
			period: 'minute', 'hour', 'day', or 'month'
			now: Current datetime
		
		Returns:
			datetime of next reset
		"""
		if period == "minute":
			# Reset at next :00 seconds
			return now.replace(second=0, microsecond=0) + timedelta(minutes=1)
		elif period == "hour":
			# Reset at next top of hour
			return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
		elif period == "day":
			# Reset at next midnight
			return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
		elif period == "month":
			# Reset on 1st of next month at 00:00
			if now.month == 12:
				return now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
			else:
				return now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
		return now
	
	def _record_credits(self, current_time: float, tokens: int, credits_param: float = 0.0) -> None:
		"""Record credit usage based on configuration."""
		credits = credits_param  # Use pre-calculated credits if provided
		
		# Calculate credits from token-based rates if not provided
		if credits_param <= 0 and tokens > 0:
			if self.credits_per_token > 0:
				credits = tokens * self.credits_per_token
			elif self.credits_per_million_tokens > 0:
				credits = (tokens / 1_000_000) * self.credits_per_million_tokens
		
		# Add request-based credits
		if self.credits_per_request > 0:
			credits += self.credits_per_request
		
		if credits > 0:
			# Track for sliding window limits (like credits_per_minute)
			self.credit_usage.append((current_time, credits))
			if len(self.credit_usage) > 1000:
				self.credit_usage.pop(0)
			
			# Track for calendar-based limits
			now = datetime.now(timezone.utc)
			for limit_key in self.limits.keys():
				if not limit_key.startswith("credits_per_"):
					continue
				
				period = limit_key.replace("credits_per_", "")
				if period not in ("minute", "hour", "day", "month"):
					continue
				
				# Initialize or check reset
				if period not in self.calendar_credits:
					self.calendar_credits[period] = 0.0
					self.calendar_reset_times[period] = self._get_calendar_reset_time(period, now).timestamp()
				
				# Reset if needed
				if current_time >= self.calendar_reset_times[period]:
					self.calendar_credits[period] = 0.0
					next_reset = self._get_calendar_reset_time(period, datetime.fromtimestamp(current_time, tz=timezone.utc))
					self.calendar_reset_times[period] = next_reset.timestamp()
				
				# Add to current period
				self.calendar_credits[period] += credits
	
	def _count_credits_in_window(self, window_seconds: int) -> float:
		"""Count credits used in the specified time window."""
		current_time = time.time()
		return sum(credits for t, credits in self.credit_usage if current_time - t < window_seconds)
	
	def _get_calendar_credits(self, period: str) -> float:
		"""Get credits used in current calendar period."""
		if period not in self.calendar_credits:
			return 0.0
		
		# Check if reset is needed
		current_time = time.time()
		if current_time >= self.calendar_reset_times.get(period, 0):
			now = datetime.fromtimestamp(current_time, tz=timezone.utc)
			self.calendar_credits[period] = 0.0
			next_reset = self._get_calendar_reset_time(period, now)
			self.calendar_reset_times[period] = next_reset.timestamp()
		
		return self.calendar_credits[period]

	def time_until_available(self) -> float:
		"""Seconds until next request can be made (based on first limit hit)."""
		if not self.is_rate_limited():
			return 0

		min_time = float('inf')
		current_time = time.time()

		for limit_key, limit_value in self.limits.items():
			if "_per_" not in limit_key:
				continue

			parts = limit_key.split("_per_")
			if len(parts) != 2:
				continue

			limit_type, period = parts
			window_seconds = self._get_time_window_seconds(period)

			if limit_type == "requests":
				count = self._count_in_window(self.requests, window_seconds)
				if count >= limit_value and self.requests:
					oldest = min(self.requests)
					time_to_available = max(0, window_seconds - (current_time - oldest))
					min_time = min(min_time, time_to_available)

			elif limit_type == "tokens":
				count = self._count_tokens_in_window(window_seconds)
				if count >= limit_value and self.token_usage:
					oldest = min(t for t, _ in self.token_usage)
					time_to_available = max(0, window_seconds - (current_time - oldest))
					min_time = min(min_time, time_to_available)

		return max(0, min_time if min_time != float('inf') else 0)


@dataclass
class CircuitBreaker:
	"""Circuit breaker pattern for provider health."""
	failure_threshold: int = 5
	success_threshold: int = 2
	timeout_seconds: int = 60
	state: str = "closed"  # closed, open, half_open
	failure_count: int = 0
	success_count: int = 0
	last_failure_time: Optional[float] = None

	def record_success(self) -> None:
		"""Record a successful request."""
		if self.state == "half_open":
			self.success_count += 1
			if self.success_count >= self.success_threshold:
				self.state = "closed"
				self.failure_count = 0
				self.success_count = 0
		elif self.state == "closed":
			self.failure_count = max(0, self.failure_count - 1)

	def record_failure(self) -> None:
		"""Record a failed request."""
		self.last_failure_time = time.time()
		self.failure_count += 1

		if self.state == "closed":
			if self.failure_count >= self.failure_threshold:
				self.state = "open"
		elif self.state == "half_open":
			self.state = "open"
			self.success_count = 0

	def can_attempt_request(self) -> bool:
		"""Check if request can be attempted."""
		if self.state == "closed":
			return True
		elif self.state == "open":
			if self.last_failure_time and time.time() - self.last_failure_time >= self.timeout_seconds:
				self.state = "half_open"
				self.failure_count = 0
				self.success_count = 0
				return True
			return False
		else:  # half_open
			return True

	def is_open(self) -> bool:
		"""Check if circuit is open."""
		return self.state == "open"

	def is_half_open(self) -> bool:
		"""Check if circuit is half-open."""
		return self.state == "half_open"


@dataclass
class ExponentialBackoff:
	"""Exponential backoff with jitter."""
	base_delay: float = 1.0
	max_delay: float = 300.0
	multiplier: float = 2.0
	jitter: float = 0.1
	current_attempt: int = 0

	def get_delay(self) -> float:
		"""Get delay for current attempt."""
		delay = min(self.base_delay * (self.multiplier ** self.current_attempt), self.max_delay)
		return delay

	def record_attempt(self) -> None:
		"""Record an attempt."""
		self.current_attempt += 1

	def reset(self) -> None:
		"""Reset backoff."""
		self.current_attempt = 0


@dataclass
class ApiKeyRotation:
	"""Manages multiple API keys with round-robin rotation."""
	api_keys: List[str]
	current_index: int = 0
	consecutive_failures: dict = field(default_factory=dict)
	disabled_keys: dict = field(default_factory=dict)
	rate_limiters: dict = field(default_factory=dict)
	cooldown_seconds: int = 600
	global_rate_limiters: Optional[dict] = None  # Shared trackers across all models

	def __post_init__(self):
		"""Initialize failure tracking and rate limiters for all keys."""
		for key in self.api_keys:
			self.consecutive_failures[key] = 0
			self.disabled_keys[key] = None
			# Use global tracker if provided, otherwise create local one
			if self.global_rate_limiters is not None and key in self.global_rate_limiters:
				self.rate_limiters[key] = self.global_rate_limiters[key]
			else:
				self.rate_limiters[key] = RateLimitTracker()

	def set_rate_limits(self, limits: dict) -> None:
		"""Set rate limits for all API keys."""
		for key in self.api_keys:
			self.rate_limiters[key].limits = limits.copy()

	def set_multipliers(self, token_multiplier: float = 1.0, request_multiplier: float = 1.0) -> None:
		"""Set token and request multipliers for all API keys."""
		for key in self.api_keys:
			self.rate_limiters[key].token_multiplier = token_multiplier
			self.rate_limiters[key].request_multiplier = request_multiplier

	def set_credit_rates(self, credits_per_token: float = 0.0, credits_per_million_tokens: float = 0.0, credits_per_request: float = 0.0) -> None:
		"""Set credit rate configuration for all API keys.
		
		Args:
			credits_per_token: Credit cost per token
			credits_per_million_tokens: Credit cost per million tokens
			credits_per_request: Credit cost per request
		"""
		for key in self.api_keys:
			self.rate_limiters[key].credits_per_token = credits_per_token
			self.rate_limiters[key].credits_per_million_tokens = credits_per_million_tokens
			self.rate_limiters[key].credits_per_request = credits_per_request

	def get_next_key(self) -> Optional[str]:
		"""Get the next available API key using round-robin."""
		if not self.api_keys:
			raise ValueError("No API keys configured")

		self._check_cooldowns()

		available_keys = [
			key for key in self.api_keys
			if self.disabled_keys.get(key) is None and not self.rate_limiters[key].is_rate_limited()
		]

		if not available_keys:
			oldest_key = min(
				self.disabled_keys.items(),
				key=lambda x: x[1] if x[1] else float('inf')
			)[0]
			self.disabled_keys[oldest_key] = None
			self.consecutive_failures[oldest_key] = 0
			available_keys = [oldest_key]

		for _ in range(len(self.api_keys)):
			key = self.api_keys[self.current_index % len(self.api_keys)]
			self.current_index = (self.current_index + 1) % len(self.api_keys)

			if key in available_keys:
				return key

		return available_keys[0] if available_keys else None

	def mark_failure(self, api_key: str) -> None:
		"""Mark an API key as having failed."""
		if api_key not in self.api_keys:
			return
		self.consecutive_failures[api_key] += 1
		self.disabled_keys[api_key] = time.time()

	def mark_success(self, api_key: str) -> None:
		"""Mark an API key as having succeeded."""
		if api_key not in self.api_keys:
			return
		self.consecutive_failures[api_key] = 0
		self.disabled_keys[api_key] = None

	def record_usage(self, api_key: Optional[str], tokens: int = 0, prompt_tokens: int = 0, completion_tokens: int = 0, credits: float = 0.0) -> None:
		"""Record token/request usage.

		Args:
			api_key: API key used
			tokens: Total tokens (legacy parameter)
			prompt_tokens: Number of prompt tokens
			completion_tokens: Number of completion tokens
			credits: Pre-calculated credits (optional, will be calculated from tokens if not provided)
		"""
		if api_key and api_key in self.rate_limiters:
			self.rate_limiters[api_key].add_request(tokens, prompt_tokens, completion_tokens, credits)

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
		"""Get detailed status of all API keys."""
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
					"rate_limited": self.rate_limiters[key].is_rate_limited(),
					"usage": self.rate_limiters[key].get_usage_stats(),
				}
				for i, key in enumerate(self.api_keys)
			]
		}


@dataclass
class SpeedTracker:
	"""Tracks response speed for a provider."""
	response_times: List[float] = field(default_factory=list)
	min_response_time: float = float('inf')
	max_response_time: float = 0.0

	def record_response(self, duration: float) -> None:
		"""Record a response time."""
		self.response_times.append(duration)
		if len(self.response_times) > 100:
			self.response_times.pop(0)
		self.min_response_time = min(self.min_response_time, duration)
		self.max_response_time = max(self.max_response_time, duration)

	def get_average_time(self) -> float:
		"""Get average response time."""
		if not self.response_times:
			return 0
		return sum(self.response_times) / len(self.response_times)

	def get_percentile_95(self) -> float:
		"""Get 95th percentile response time."""
		if not self.response_times:
			return 0
		sorted_times = sorted(self.response_times)
		idx = int(len(sorted_times) * 0.95)
		return sorted_times[idx] if idx < len(sorted_times) else sorted_times[-1]


@dataclass
class ProviderInstance:
	"""Represents a provider instance for a specific model."""
	provider: "Provider"
	priority: int
	model_ids: List[str]  # Model IDs to round-robin through when calling the provider
	api_key_rotation: Optional[ApiKeyRotation] = None
	enabled: bool = True
	consecutive_failures: int = 0
	last_failure: Optional[float] = None
	retry_count: int = 0
	max_retries: int = 3
	circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
	backoff: ExponentialBackoff = field(default_factory=ExponentialBackoff)
	speed_tracker: SpeedTracker = field(default_factory=SpeedTracker)
	_model_id_index: int = field(default=0, init=False, repr=False)  # Tracks current position in model_ids rotation

	def mark_failure(self) -> None:
		"""Mark a failure and potentially disable the provider."""
		self.consecutive_failures += 1
		self.last_failure = time.time()
		self.circuit_breaker.record_failure()
		if self.consecutive_failures >= 3:
			self.enabled = False

	def mark_success(self) -> None:
		"""Mark a success and reset failure counter."""
		self.consecutive_failures = 0
		self.last_failure = None
		self.circuit_breaker.record_success()
		self.backoff.reset()

	def should_retry(self, cooldown_seconds: int = 600) -> bool:
		"""Check if enough time has passed to retry a failed provider."""
		if not self.last_failure:
			return True
		return time.time() - self.last_failure >= cooldown_seconds

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
		self.backoff.record_attempt()

	def reset_retry_count(self) -> None:
		"""Reset the retry counter."""
		self.retry_count = 0
		self.backoff.reset()

	def should_retry_request(self) -> bool:
		"""Check if we should retry the request."""
		if not self.circuit_breaker.can_attempt_request():
			return False
		return self.retry_count < self.max_retries

	def get_backoff_delay(self) -> float:
		"""Get current backoff delay."""
		return self.backoff.get_delay()

	def record_response(self, duration: float, tokens: int = 0, api_key: Optional[str] = None, prompt_tokens: int = 0, completion_tokens: int = 0, credits: float = 0.0) -> None:
		"""Record response metrics.

		Args:
			duration: Response time in seconds
			tokens: Total tokens (legacy parameter)
			api_key: API key used for the request
			prompt_tokens: Number of prompt tokens
			completion_tokens: Number of completion tokens
			credits: Pre-calculated credits (optional)
		"""
		self.speed_tracker.record_response(duration)
		if self.api_key_rotation:
			self.api_key_rotation.record_usage(api_key, tokens, prompt_tokens, completion_tokens, credits)

	def get_next_model_id(self) -> str:
		"""Get the next model ID in round-robin rotation."""
		current = self.model_ids[self._model_id_index]
		self._model_id_index = (self._model_id_index + 1) % len(self.model_ids)
		return current

	def get_health_score(self) -> float:
		"""
		Calculate provider health score (0-100).
		Higher is better. Considers success rate, speed, availability, and priority.
		"""
		base_score = 100.0

		# Factor in circuit breaker state
		if self.circuit_breaker.is_open():
			return 0.0
		if self.circuit_breaker.is_half_open():
			base_score -= 50

		# Factor in failure rate
		base_score -= min(self.consecutive_failures * 10, 40)

		# Factor in speed (prefer faster providers)
		avg_time = self.speed_tracker.get_average_time()
		if avg_time > 0:
			speed_penalty = min(avg_time * 10, 30)
			base_score -= speed_penalty

		final_score = max(0, min(base_score, 100))

		# Apply priority as multiplier (lower priority = higher multiplier boost)
		# Priority 0 gets 1.0x, Priority 1 gets 0.9x, Priority 2 gets 0.8x, etc.
		priority_multiplier = max(0.1, 1.0 - (self.priority * 0.1))
		final_score *= priority_multiplier

		return final_score

	def get_stats(self) -> dict:
		"""Get comprehensive statistics."""
		return {
			"enabled": self.enabled,
			"priority": self.priority,
			"model_ids": self.model_ids,
			"consecutive_failures": self.consecutive_failures,
			"circuit_breaker": self.circuit_breaker.state,
			"health_score": self.get_health_score(),
			"avg_response_time": self.speed_tracker.get_average_time(),
			"p95_response_time": self.speed_tracker.get_percentile_95(),
		}


@dataclass
class Model:
	"""Represents a model available through the proxy."""
	id: str
	provider_instances: list[ProviderInstance] = field(default_factory=list)
	created: int = 1234567890
	owned_by: str = "system"

	def get_available_providers(self) -> list[ProviderInstance]:
		"""Return enabled providers sorted by health score (priority factored in)."""
		available = [
			pi
			for pi in self.provider_instances
			if pi.enabled or pi.should_retry()
		]
		# Re-enable if cooldown has passed
		for pi in available:
			if not pi.enabled and pi.should_retry():
				pi.enabled = True
		# Sort by health score (best first) - priority already factored into score
		return sorted(available, key=lambda pi: -pi.get_health_score())

	def get_best_provider(self) -> Optional[ProviderInstance]:
		"""Get the single best provider based on health and speed."""
		available = self.get_available_providers()
		return available[0] if available else None

	def to_dict(self) -> dict:
		"""Return dict in OpenAI model format."""
		return {
			"id": self.id,
			"object": "model",
			"created": self.created,
			"owned_by": self.owned_by,
		}
