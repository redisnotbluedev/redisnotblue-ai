# Provider Defaults and Multipliers

Quick reference for using provider-level defaults and per-instance multipliers.

## Overview

You can now configure rate limits at two levels:

1. **Provider-level defaults** - Set once, applies to all models using that provider
2. **Instance-level overrides** - Per model/provider, can completely override defaults or apply a multiplier

## Provider-Level Defaults

Set rate limits at the provider level in `config.yaml`:

```yaml
providers:
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-key-1
      - sk-key-2
    rate_limits:                    # ← Provider default
      requests_per_minute: 3500
      tokens_per_day: 90000000
```

Now all models using this provider automatically get these limits (unless overridden).

## Instance-Level Overrides

Override provider defaults for a specific model/provider combo:

```yaml
models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        rate_limits:                # ← Overrides provider defaults
          requests_per_minute: 100
          tokens_per_day: 100000
```

These limits completely replace the provider defaults.

## Multipliers

Apply a multiplier to the provider defaults without overriding them:

```yaml
models:
  gpt-4-turbo:
    providers:
      openai:
        priority: 0
        model_id: gpt-4-turbo-preview
        rate_limits:
          multiplier: 2.0           # ← Double the provider defaults
```

With provider defaults of `3500 req/min` and `90M tokens/day`:
- `multiplier: 2.0` → `7000 req/min` and `180M tokens/day`
- `multiplier: 3.0` → `10500 req/min` and `270M tokens/day`
- `multiplier: 0.5` → `1750 req/min` and `45M tokens/day`

## Priority/Hierarchy

When loading configuration, limits are applied in this order:

1. **Start with provider defaults** (if defined)
2. **Override with instance-specific limits** (if `rate_limits` has non-multiplier keys)
3. **Apply multiplier** (if `multiplier` key is present)

### Examples

#### Example 1: Use Provider Default
```yaml
providers:
  openai:
    rate_limits:
      requests_per_minute: 3500
      tokens_per_day: 90000000

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        # No rate_limits specified → uses provider defaults
```

**Result:** `3500 req/min`, `90M tokens/day`

#### Example 2: Override Provider Default
```yaml
providers:
  openai:
    rate_limits:
      requests_per_minute: 3500
      tokens_per_day: 90000000

models:
  gpt-3.5-turbo:
    providers:
      openai:
        priority: 0
        model_id: gpt-3.5-turbo
        rate_limits:
          requests_per_day: 1000   # ← Specific override
          tokens_per_day: 100000
```

**Result:** `1000 req/day`, `100k tokens/day` (provider defaults ignored)

#### Example 3: Multiply Provider Default
```yaml
providers:
  openai:
    rate_limits:
      requests_per_minute: 3500
      tokens_per_day: 90000000

models:
  high-volume:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        rate_limits:
          multiplier: 2.0          # ← Double the defaults
```

**Result:** `7000 req/min`, `180M tokens/day`

#### Example 4: Mix Override and Multiplier
```yaml
providers:
  openai:
    rate_limits:
      requests_per_minute: 3500
      tokens_per_day: 90000000

models:
  special-case:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        rate_limits:
          requests_per_hour: 500000  # ← Specific override
          multiplier: 2.0            # ← Applied to overridden value
```

**Result:** `1000000 req/hour` (500k × 2.0), `180M tokens/day` (90M × 2.0, not overridden)

## Common Patterns

### Pattern 1: One Standard Provider with Multiple Models

```yaml
providers:
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys: [sk-key-1, sk-key-2]
    rate_limits:
      requests_per_minute: 3500
      tokens_per_day: 90000000

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        # Uses provider defaults

  gpt-4-turbo:
    providers:
      openai:
        priority: 0
        model_id: gpt-4-turbo-preview
        # Uses provider defaults

  gpt-3.5-turbo:
    providers:
      openai:
        priority: 0
        model_id: gpt-3.5-turbo
        rate_limits:
          multiplier: 2.0  # Double for this model
```

### Pattern 2: Different Providers with Different Defaults

```yaml
providers:
  fast:
    type: openai
    base_url: https://api.fast.com/v1
    api_keys: [sk-fast-1]
    rate_limits:
      requests_per_minute: 5000
      tokens_per_day: 150000000

  budget:
    type: openai
    base_url: https://api.budget.com/v1
    api_keys: [sk-budget-1]
    rate_limits:
      requests_per_day: 1000
      tokens_per_day: 50000

models:
  premium:
    providers:
      fast:
        priority: 0
        model_id: gpt-4
        # Uses fast provider defaults: 5k req/min, 150M tokens/day

  budget:
    providers:
      budget:
        priority: 0
        model_id: gpt-4
        # Uses budget provider defaults: 1k req/day, 50k tokens/day
```

### Pattern 3: High-Volume Setup with Multiple Keys and Multiplier

```yaml
providers:
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys:
      - sk-key-1
      - sk-key-2
      - sk-key-3
    rate_limits:
      requests_per_minute: 3500
      tokens_per_day: 90000000

models:
  high-volume-app:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
        rate_limits:
          multiplier: 3.0  # 3 keys × 3.5k req/min = 10.5k req/min
```

## Configuration Tips

**Do use provider defaults when:**
- All models with that provider should have the same limits
- You want to change limits in one place for all models
- You're using the same provider multiple times

**Do use overrides when:**
- A specific model needs different limits
- You want to be explicit about limits for a model
- You're mixing provider defaults with custom limits

**Do use multipliers when:**
- You have multiple API keys and want proportional scaling
- You want to express limits relative to provider defaults
- You're setting up different tiers (e.g., 1x, 2x, 3x)

## Behavior Details

- **Multiplier only**: Provider defaults are multiplied by the factor
- **Override only**: Provider defaults are completely ignored
- **Both multiplier and override**: Override is applied first, then multiplier
- **Neither**: Provider defaults are used as-is
- **No defaults, no overrides**: No rate limits configured (unlimited)

## Example: Complete Real-World Setup

```yaml
providers:
  primary:
    type: openai
    base_url: https://api.openai.com/v1
    api_keys: [sk-primary-1, sk-primary-2, sk-primary-3]
    rate_limits:
      requests_per_minute: 3500
      tokens_per_day: 90000000

  budget:
    type: openai
    base_url: https://api.budget-provider.com/v1
    api_keys: [sk-budget-1]
    rate_limits:
      requests_per_day: 1000
      tokens_per_day: 50000

  backup:
    type: openai
    base_url: https://api.backup.com/v1
    api_keys: [sk-backup-1]
    # No rate limits defined at provider level

models:
  # Standard - uses primary provider defaults
  gpt-4:
    providers:
      primary:
        priority: 0
        model_id: gpt-4

  # High volume - multiplies primary defaults by 2x
  gpt-4-turbo:
    providers:
      primary:
        priority: 0
        model_id: gpt-4-turbo-preview
        rate_limits:
          multiplier: 2.0

  # Budget constrained - overrides with tight limits
  gpt-3.5-turbo:
    providers:
      budget:
        priority: 0
        model_id: gpt-3.5-turbo
        # Uses budget provider defaults (1k req/day, 50k tokens/day)

      backup:
        priority: 1
        model_id: gpt-3.5-turbo
        rate_limits:
          requests_per_hour: 100  # Custom fallback limits
          tokens_per_day: 10000
```

In this setup:
- `gpt-4` gets primary limits: 3.5k req/min, 90M tokens/day
- `gpt-4-turbo` gets 2× primary limits: 7k req/min, 180M tokens/day
- `gpt-3.5-turbo` uses budget provider (1k req/day, 50k tokens/day) with a backup provider having custom limits