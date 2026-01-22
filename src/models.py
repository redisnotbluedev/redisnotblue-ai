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
	"""Tracks rate limiting and usage for an API key with calendar-based periods."""
	limits: dict = field(default_factory=dict)  # {"requests_per_minute": 3500, "tokens_per_day": 90000, "credits_per_day": 1000, ...}
	calendar_usage: dict = field(default_factory=dict)  # {period: count} for requests/tokens with calendar resets
	calendar_reset_times: dict = field(default_factory=dict)  # {period: next_reset_timestamp}
	token_multiplier: float = 1.0  # How much each token counts (e.g., 2.0 = counts as 2x)
	request_multiplier: float = 1.0  # How much each request counts (e.g., 2.0 = counts as 2x)
	credits_per_token: float = 0.0  # How many credits per token (0 = disabled)
	credits_per_million_tokens: float = 0.0  # How many credits per million tokens (0 = disabled)
	credits_per_in_token: float = 0.0  # How many credits per input token (0 = disabled)
	credits_per_out_token: float = 0.0  # How many credits per output token (0 = disabled)
	credits_per_million_in_tokens: float = 0.0  # How many credits per million input tokens (0 = disabled)
	credits_per_million_out_tokens: float = 0.0  # How many credits per million output tokens (0 = disabled)
	credits_per_request: float = 0.0  # How many credits per request (0 = disabled)
	credit_gains: dict = field(default_factory=dict)  # {"minute": 100, "hour": 1000, ...} - credits gained per interval (provider-level)
	credit_maxes: dict = field(default_factory=dict)  # {"minute": 100, "hour": 1000, ...} - max credits that can accumulate (provider-level)
	credit_balance: dict = field(default_factory=dict)  # {"minute": 50.0, "hour": 500.0, ...} - current credit balance per interval

	def add_request(self, tokens: int = 0, in_tokens: int = 0, out_tokens: int = 0, credits: float = 0.0) -> None:
		"""Record a request with calendar-based period tracking.
		
		Args:
			tokens: Total tokens (legacy, used if in_tokens/out_tokens not provided)
			in_tokens: Number of input tokens
			out_tokens: Number of output tokens
			credits: Pre-calculated credits (optional, will be calculated from tokens if not provided)
		"""
		current_time = time.time()
		now = datetime.fromtimestamp(current_time, tz=timezone.utc)
		
		# Calculate tokens
		if in_tokens > 0 or out_tokens > 0:
			total_tokens = in_tokens + out_tokens
			counted_in = int(in_tokens * self.token_multiplier)
			counted_out = int(out_tokens * self.token_multiplier)
			counted_total = int(total_tokens * self.token_multiplier)
		elif tokens > 0:
			counted_total = int(tokens * self.token_multiplier)
			counted_in = 0
			counted_out = 0
		else:
			counted_total = 0
			counted_in = 0
			counted_out = 0
		
		# Calculate requests
		counted_requests = int(self.request_multiplier)
		
		# Calculate credits
		if credits <= 0:
			credits = 0.0
			# Total token rates
			if self.credits_per_token > 0:
				credits += counted_total * self.credits_per_token
			elif self.credits_per_million_tokens > 0:
				credits += (counted_total / 1_000_000) * self.credits_per_million_tokens
			# Input token rates
			if self.credits_per_in_token > 0:
				credits += counted_in * self.credits_per_in_token
			elif self.credits_per_million_in_tokens > 0:
				credits += (counted_in / 1_000_000) * self.credits_per_million_in_tokens
			# Output token rates
			if self.credits_per_out_token > 0:
				credits += counted_out * self.credits_per_out_token
			elif self.credits_per_million_out_tokens > 0:
				credits += (counted_out / 1_000_000) * self.credits_per_million_out_tokens
			# Request rate
			if self.credits_per_request > 0:
				credits += self.credits_per_request
		
		# Update calendar usage for all periods
		for limit_key in self.limits.keys():
			if "_per_" not in limit_key:
				continue
			
			parts = limit_key.split("_per_")
			if len(parts) != 2:
				continue
			
			limit_type, period = parts
			if period not in ("minute", "hour", "day", "month"):
				continue
			
			# Initialize period if needed
			if period not in self.calendar_usage:
				self.calendar_usage[period] = {"requests": 0, "tokens": 0, "in_tokens": 0, "out_tokens": 0, "credits": 0.0}
				self.calendar_reset_times[period] = self._get_calendar_reset_time(period, now).timestamp()
			
			# Reset if needed
			if current_time >= self.calendar_reset_times[period]:
				self.calendar_usage[period] = {"requests": 0, "tokens": 0, "in_tokens": 0, "out_tokens": 0, "credits": 0.0}
				next_reset = self._get_calendar_reset_time(period, datetime.fromtimestamp(current_time, tz=timezone.utc))
				self.calendar_reset_times[period] = next_reset.timestamp()
			
			# Add usage
			if limit_type == "requests":
				self.calendar_usage[period]["requests"] += counted_requests
			elif limit_type == "tokens":
				self.calendar_usage[period]["tokens"] += counted_total
			elif limit_type == "in_tokens":
				self.calendar_usage[period]["in_tokens"] += counted_in
			elif limit_type == "out_tokens":
				self.calendar_usage[period]["out_tokens"] += counted_out
			elif limit_type == "credits":
				self.calendar_usage[period]["credits"] += credits

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



	def is_rate_limited(self) -> bool:
		"""Check if rate limited by any configured limit."""
		current_time = time.time()
		
		for limit_key, limit_value in self.limits.items():
			if "_per_" not in limit_key:
				continue

			parts = limit_key.split("_per_")
			if len(parts) != 2:
				continue

			limit_type, period = parts
			if period not in ("minute", "hour", "day", "month"):
				continue
			
			# Check if reset needed
			if period in self.calendar_reset_times and current_time >= self.calendar_reset_times[period]:
				now = datetime.fromtimestamp(current_time, tz=timezone.utc)
				self.calendar_usage[period] = {"requests": 0, "tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "credits": 0.0}
				next_reset = self._get_calendar_reset_time(period, now)
				self.calendar_reset_times[period] = next_reset.timestamp()
			
			# Get current usage
			if period not in self.calendar_usage:
				continue
			
			if limit_type == "requests":
				count = self.calendar_usage[period]["requests"]
			elif limit_type == "tokens":
				count = self.calendar_usage[period]["tokens"]
			elif limit_type == "in_tokens":
				count = self.calendar_usage[period]["in_tokens"]
			elif limit_type == "out_tokens":
				count = self.calendar_usage[period]["out_tokens"]
			elif limit_type == "credits":
				count = self.calendar_usage[period]["credits"]
			else:
				continue
			
			if count >= limit_value:
				return True

		return False

	def get_usage_stats(self) -> dict:
		"""Get current usage statistics across all configured limits."""
		stats = {}
		current_time = time.time()

		for limit_key, limit_value in self.limits.items():
			if "_per_" not in limit_key:
				continue

			parts = limit_key.split("_per_")
			if len(parts) != 2:
				continue

			limit_type, period = parts
			if period not in ("minute", "hour", "day", "month"):
				continue
			
			# Check if reset needed
			if period in self.calendar_reset_times and current_time >= self.calendar_reset_times[period]:
				now = datetime.fromtimestamp(current_time, tz=timezone.utc)
				self.calendar_usage[period] = {"requests": 0, "tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "credits": 0.0}
				next_reset = self._get_calendar_reset_time(period, now)
				self.calendar_reset_times[period] = next_reset.timestamp()
			
			# Get current usage
			if period not in self.calendar_usage:
				stats[limit_key] = {"used": 0, "limit": limit_value}
				continue
			
			if limit_type == "requests":
				count = self.calendar_usage[period]["requests"]
			elif limit_type == "tokens":
				count = self.calendar_usage[period]["tokens"]
			elif limit_type == "in_tokens":
				count = self.calendar_usage[period]["in_tokens"]
			elif limit_type == "out_tokens":
				count = self.calendar_usage[period]["out_tokens"]
			elif limit_type == "credits":
				count = self.calendar_usage[period]["credits"]
			else:
				continue
			
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

	def time_until_available(self) -> float:
		"""Seconds until next request can be made (based on first limit hit)."""
		if not self.is_rate_limited():
			return 0

		min_time = float('inf')
		current_time = time.time()

		for period, reset_time in self.calendar_reset_times.items():
			time_to_reset = max(0, reset_time - current_time)
			if time_to_reset > 0:
				min_time = min(min_time, time_to_reset)

		return max(0, min_time if min_time != float('inf') else 0)

	def set_credit_gain_and_max(self, credit_gains: dict, credit_maxes: dict) -> None:
		"""Set provider-level credit gain rates and max balances.
		
		Args:
			credit_gains: Dict of {"minute": X, "hour": Y, "day": Z, "month": W}
			credit_maxes: Dict of max credits per interval; if not specified, defaults to gain amount
		"""
		self.credit_gains = dict(credit_gains) if credit_gains else {}
		
		# Set maxes to equal gains by default
		self.credit_maxes = {}
		for period in self.credit_gains:
			self.credit_maxes[period] = credit_maxes.get(period, self.credit_gains[period])
		
		# Initialize balances to max (start fully charged)
		self.credit_balance = dict(self.credit_maxes)

	def update_credit_balance(self) -> None:
		"""Update credit balances by resetting on period boundaries.
		
		This should be called periodically (e.g., at start of each request) to
		check if a new period has started and reset the balance if needed.
		"""
		current_time = time.time()
		now = datetime.fromtimestamp(current_time, tz=timezone.utc)
		
		for period in self.credit_gains:
			gain_amount = self.credit_gains[period]
			max_amount = self.credit_maxes.get(period, gain_amount)
			
			# Initialize period tracking if needed
			if period not in self.calendar_reset_times:
				self.calendar_reset_times[period] = self._get_calendar_reset_time(period, now).timestamp()
				self.credit_balance[period] = max_amount
			
			# Check if reset needed (new period started)
			if current_time >= self.calendar_reset_times[period]:
				# New period started, reset balance to max (full credits available for new period)
				self.credit_balance[period] = max_amount
				next_reset = self._get_calendar_reset_time(period, datetime.fromtimestamp(current_time, tz=timezone.utc))
				self.calendar_reset_times[period] = next_reset.timestamp()

	def has_sufficient_credits(self, required_credits: float) -> bool:
		"""Check if there are sufficient credits for a request.
		
		Args:
			required_credits: Number of credits needed
		
		Returns:
			True if sufficient credits across all intervals, False otherwise
		"""
		if not self.credit_gains:  # No credit limits configured
			return True
		
		self.update_credit_balance()
		
		# Check if any single period would be exhausted
		for period in self.credit_gains:
			balance = self.credit_balance.get(period, 0)
			if balance < required_credits:
				return False
		
		return True

	def spend_credits(self, amount: float) -> None:
		"""Spend credits from the balance across all intervals.
		
		Args:
			amount: Number of credits to spend
		"""
		if not self.credit_gains:
			return
		
		for period in self.credit_balance:
			self.credit_balance[period] = max(0, self.credit_balance[period] - amount)

	def get_credit_balance(self) -> dict:
		"""Get current credit balance across all periods.
		
		Returns:
			Dict of {"minute": X, "hour": Y, ...} with current balances
		"""
		self.update_credit_balance()
		return dict(self.credit_balance)


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

	def set_credit_rates(self, credits_per_token: float = 0.0, credits_per_million_tokens: float = 0.0, 
	                      credits_per_in_token: float = 0.0, credits_per_out_token: float = 0.0,
	                      credits_per_million_in_tokens: float = 0.0, credits_per_million_out_tokens: float = 0.0,
	                      credits_per_request: float = 0.0) -> None:
		"""Set credit rate configuration for all API keys.
		
		Args:
			credits_per_token: Credit cost per token (total)
			credits_per_million_tokens: Credit cost per million tokens (total)
			credits_per_in_token: Credit cost per input token
			credits_per_out_token: Credit cost per output token
			credits_per_million_in_tokens: Credit cost per million input tokens
			credits_per_million_out_tokens: Credit cost per million output tokens
			credits_per_request: Credit cost per request
		"""
		for key in self.api_keys:
			self.rate_limiters[key].credits_per_token = credits_per_token
			self.rate_limiters[key].credits_per_million_tokens = credits_per_million_tokens
			self.rate_limiters[key].credits_per_in_token = credits_per_in_token
			self.rate_limiters[key].credits_per_out_token = credits_per_out_token
			self.rate_limiters[key].credits_per_million_in_tokens = credits_per_million_in_tokens
			self.rate_limiters[key].credits_per_million_out_tokens = credits_per_million_out_tokens
			self.rate_limiters[key].credits_per_request = credits_per_request

	def set_credit_gain_and_max(self, credit_gains: dict, credit_maxes: dict) -> None:
		"""Set provider-level credit gain rates and max balances for all API keys.
		
		Args:
			credit_gains: Dict of {"minute": X, "hour": Y, "day": Z, "month": W}
			credit_maxes: Dict of max credits per interval; if not specified, defaults to gain amount
		"""
		for key in self.api_keys:
			self.rate_limiters[key].set_credit_gain_and_max(credit_gains, credit_maxes)

	def get_next_key(self, required_credits: float = 0.0) -> Optional[str]:
		"""Get the next available API key using round-robin.
		
		Args:
			required_credits: Credits needed for the request (optional)
		"""
		if not self.api_keys:
			raise ValueError("No API keys configured")

		self._check_cooldowns()

		available_keys = [
			key for key in self.api_keys
			if self.disabled_keys.get(key) is None 
			and not self.rate_limiters[key].is_rate_limited()
			and (required_credits == 0.0 or self.rate_limiters[key].has_sufficient_credits(required_credits))
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

	def record_usage(self, api_key: Optional[str], tokens: int = 0, in_tokens: int = 0, out_tokens: int = 0, credits: float = 0.0) -> None:
		"""Record token/request usage.

		Args:
			api_key: API key used
			tokens: Total tokens (legacy parameter)
			in_tokens: Number of input tokens
			out_tokens: Number of output tokens
			credits: Pre-calculated credits (optional, will be calculated from tokens if not provided)
		"""
		if api_key and api_key in self.rate_limiters:
			self.rate_limiters[api_key].add_request(tokens, in_tokens, out_tokens, credits)
			# Spend credits if configured
			if credits > 0:
				self.rate_limiters[api_key].spend_credits(credits)

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
	token_counts: List[int] = field(default_factory=list)
	output_token_counts: List[int] = field(default_factory=list)
	ttft_times: List[float] = field(default_factory=list)
	min_response_time: float = float('inf')
	max_response_time: float = 0.0

	def record_response(self, duration: float, tokens: int = 0, output_tokens: int = 0, ttft: float = 0.0) -> None:
		"""Record a response time with token counts and TTFT."""
		self.response_times.append(duration)
		self.token_counts.append(tokens)
		self.output_token_counts.append(output_tokens)
		
		if ttft > 0:
			self.ttft_times.append(ttft)
		
		if len(self.response_times) > 100:
			self.response_times.pop(0)
			self.token_counts.pop(0)
			self.output_token_counts.pop(0)
			if self.ttft_times:
				self.ttft_times.pop(0)
		
		self.min_response_time = min(self.min_response_time, duration)
		self.max_response_time = max(self.max_response_time, duration)

	def get_average_time(self) -> float:
		"""Get average response time."""
		if not self.response_times:
			return 0
		return sum(self.response_times) / len(self.response_times)

	def get_tokens_per_second(self) -> float:
		"""Get average output tokens per second (output tokens only for fair TTFT comparison)."""
		if not self.response_times or not self.output_token_counts:
			return 0.0
		total_output_tokens = sum(self.output_token_counts)
		if total_output_tokens == 0:
			return 0.0
		total_time = sum(self.response_times)
		return total_output_tokens / total_time if total_time > 0 else 0.0

	def get_average_ttft(self) -> float:
		"""Get average time to first token."""
		if not self.ttft_times:
			return 0.0
		return sum(self.ttft_times) / len(self.ttft_times)

	def get_percentile_95(self) -> float:
		"""Get 95th percentile response time."""
		if not self.response_times:
			return 0
		sorted_times = sorted(self.response_times)
		idx = int(len(sorted_times) * 0.95)
		return sorted_times[idx] if idx < len(sorted_times) else sorted_times[-1]

	def get_p95_ttft(self) -> float:
		"""Get 95th percentile TTFT."""
		if not self.ttft_times:
			return 0.0
		sorted_times = sorted(self.ttft_times)
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
		self.enabled = True
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

	def record_response(self, duration: float, tokens: int = 0, api_key: Optional[str] = None, prompt_tokens: int = 0, completion_tokens: int = 0, credits: float = 0.0, ttft: float = 0.0) -> None:
		"""Record response metrics.

		Args:
			duration: Response time in seconds
			tokens: Total tokens (legacy parameter)
			api_key: API key used for the request
			prompt_tokens: Number of prompt tokens
			completion_tokens: Number of completion tokens
			credits: Pre-calculated credits (optional)
			ttft: Time to first token in seconds (optional)
		"""
		self.speed_tracker.record_response(duration, tokens=tokens, output_tokens=completion_tokens, ttft=ttft)
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
		Higher is better. Considers success rate, speed, and availability.
		Priority is applied separately as a relative ranking bonus.
		"""
		base_score = 100.0

		# Factor in circuit breaker state
		if self.circuit_breaker.is_open():
			return 0.0
		if self.circuit_breaker.is_half_open():
			base_score -= 50

		# Factor in failure rate
		base_score -= min(self.consecutive_failures * 10, 40)

		# Factor in speed (prefer faster throughput)
		tokens_per_sec = self.speed_tracker.get_tokens_per_second()
		if tokens_per_sec > 0:
			# Lower tokens/sec = slower = higher penalty (want high throughput)
			# Normalize by assuming 50 tokens/sec is baseline (good)
			speed_penalty = min(max(0, (50 - tokens_per_sec) / 50 * 30), 30)
			base_score -= speed_penalty
		
		# Factor in TTFT if available (lower TTFT is better)
		avg_ttft = self.speed_tracker.get_average_ttft()
		if avg_ttft > 0:
			# Higher TTFT = worse, penalize (baseline 0.5s is good)
			ttft_penalty = min(avg_ttft * 20, 20)
			base_score -= ttft_penalty

		final_score = max(0, min(base_score, 100))
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
		"""Return enabled providers sorted by health score with relative priority ranking."""
		available = [
			pi
			for pi in self.provider_instances
			if pi.enabled or pi.should_retry()
		]
		# Re-enable if cooldown has passed
		for pi in available:
			if not pi.enabled and pi.should_retry():
				pi.enabled = True
		
		# Calculate relative priority ranking: lower priority = better rank = higher bonus
		# Providers are ranked 0 to N-1 based on their priority value
		if available:
			sorted_by_priority = sorted(available, key=lambda pi: pi.priority)
			# Use id() to track rank since ProviderInstance isn't hashable
			priority_rank = {id(pi): idx for idx, pi in enumerate(sorted_by_priority)}
			
			# Number of providers determines bonus granularity
			num_providers = len(available)
			
			# Calculate adjusted scores with priority bonuses
			def score_with_priority(pi: ProviderInstance) -> float:
				base_score = pi.get_health_score()
				rank = priority_rank[id(pi)]
				# Best priority (lowest value) gets highest bonus, worst priority gets negative bonus
				# Formula: bonus ranges from +(num_providers-1) to -(num_providers-1)
				priority_bonus = (num_providers - 1) - (2 * rank)
				return base_score + priority_bonus
			
			return sorted(available, key=score_with_priority, reverse=True)
		
		return available

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
