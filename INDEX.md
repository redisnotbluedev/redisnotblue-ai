# LLM Provider Proxy - Complete Project Index

## 📋 Project Overview

A production-ready FastAPI server that acts as an intelligent proxy and failover manager for Large Language Model (LLM) API requests. It provides a unified OpenAI-compatible interface to multiple LLM providers with automatic failover, provider prioritization, and comprehensive failure tracking.

**Total Project Size:** 3,016 lines of code and documentation
**Status:** ✅ Production Ready

---

## 📁 File Organization

### Core Application (`src/`)

| File | Lines | Purpose |
|------|-------|---------|
| `src/__init__.py` | 3 | Package initialization |
| `src/app.py` | 171 | FastAPI application with HTTP endpoints |
| `src/models.py` | 69 | Data models (Message, Model, ProviderInstance) |
| `src/registry.py` | 123 | Registry managing providers and models |
| `src/providers/__init__.py` | 6 | Provider package initialization |
| `src/providers/base.py` | 74 | Abstract Provider base class |
| `src/providers/openai.py` | 105 | OpenAI provider implementation |

**Total Application Code:** ~551 lines

### Configuration

| File | Lines | Purpose |
|------|-------|---------|
| `config/config.yaml` | 43 | Example configuration with multiple providers |

### Documentation

| File | Lines | Purpose |
|------|-------|---------|
| `README.md` | 416 | Complete documentation and API reference |
| `QUICKSTART.md` | 280 | 5-minute quick start guide |
| `ARCHITECTURE.md` | 590 | Detailed technical architecture |
| `PROJECT_SUMMARY.md` | 478 | High-level project overview |
| `INDEX.md` | This file | Complete project index |

**Total Documentation:** ~1,900+ lines

### Deployment & Infrastructure

| File | Lines | Purpose |
|------|-------|---------|
| `requirements.txt` | 6 | Python dependencies |
| `Dockerfile` | 59 | Multi-stage Docker image |
| `docker-compose.yml` | 42 | Docker Compose configuration |
| `deploy.sh` | 194 | Production deployment script |
| `.env.example` | 20 | Environment variables template |
| `.gitignore` | 140 | Git ignore rules |

### Testing

| File | Lines | Purpose |
|------|-------|---------|
| `test_basic.py` | 235 | Basic functionality tests |

---

## 🎯 Key Features

### ✅ Implemented

- [x] **Multi-Provider Support** - Route to multiple LLM providers simultaneously
- [x] **Automatic Failover** - Seamless switching between providers on failure
- [x] **Failure Tracking** - Track consecutive failures per provider
- [x] **Auto-Disable** - Disable providers after 3 consecutive failures
- [x] **Cooldown Recovery** - Re-enable after 10-minute cooldown period
- [x] **Priority Routing** - Configure provider priority (0 = highest)
- [x] **OpenAI-Compatible** - Drop-in replacement for OpenAI API
- [x] **YAML Configuration** - Easy-to-edit provider and model setup
- [x] **Environment Variables** - Secure API key management
- [x] **Docker Support** - Multi-stage optimized Docker image
- [x] **Production Ready** - Health checks, error handling, logging
- [x] **Comprehensive Docs** - 1,900+ lines of documentation
- [x] **Test Suite** - Basic functionality tests with mocks

---

## 🚀 API Endpoints

### POST `/v1/chat/completions`
Send a chat completion request (OpenAI-compatible)

**Parameters:**
- `model` (required): Model name
- `messages` (required): Array of message objects with `role` and `content`
- `temperature` (optional): 0-2, default 1.0
- `max_tokens` or `max_completion_tokens` (optional): Maximum tokens
- `top_p` (optional): 0-1, default 1.0
- `stop` (optional): Stop sequence(s)

**Response:** OpenAI-format chat completion

### GET `/v1/models`
List all available models

**Response:** OpenAI-format model list

### GET `/health`
Health check endpoint

**Response:** `{"status": "ok"}`

---

## 🔄 Architecture Overview

```
Client Request
    ↓
FastAPI App (app.py)
├─ Validate request
├─ Query registry for model
└─ Try providers in priority order
    ↓
ModelRegistry (registry.py)
├─ Load YAML config
├─ Store providers & models
└─ Route to correct model
    ↓
Model + ProviderInstances
├─ Get available providers (enabled, sorted by priority)
├─ Re-enable if cooldown expired
└─ Handle failures
    ↓
Provider Abstraction (base.py)
├─ translate_request() → provider format
├─ make_request() → HTTP call
└─ translate_response() → OpenAI format
    ↓
Concrete Providers
├─ OpenAI (openai.py)
├─ Anthropic (extensible)
└─ Custom providers...
    ↓
LLM Provider APIs
```

---

## 📊 Data Models

### Message
```python
@dataclass
class Message:
    role: str       # "user", "assistant", "system"
    content: str    # Message text
```

### ProviderInstance
Wraps a provider for a model with failure tracking:
- `provider`: Reference to Provider
- `priority`: Sort order (0 = highest)
- `model_id`: Provider-specific model name
- `enabled`: Currently available?
- `consecutive_failures`: Failure count
- `last_failure`: Unix timestamp of last failure

**Methods:**
- `mark_failure()` - Increment failures, disable if >= 3
- `mark_success()` - Reset failures to 0
- `should_retry(cooldown_seconds=600)` - Check if ready to retry

### Model
Unified model with multiple provider options:
- `id`: Model name (e.g., "gpt-4")
- `provider_instances`: List of ProviderInstance
- `created`: Unix timestamp
- `owned_by`: Provider name

**Methods:**
- `get_available_providers()` - Get enabled providers sorted by priority
- `to_dict()` - Convert to OpenAI format

---

## 🔌 Provider System

### Provider Base Class (base.py)
Abstract interface that all providers must implement:

```python
class Provider(ABC):
    def translate_request(messages, model_id, **kwargs) -> dict
    def make_request(request_data) -> dict
    def translate_response(response_data) -> dict
    def chat_completion(messages, model_id, **kwargs) -> dict
```

### OpenAI Provider (openai.py)
Concrete implementation for OpenAI's API:
- Config requires: `api_key`, optional `base_url`
- Request/response already in OpenAI format (mostly pass-through)
- Handles both `max_tokens` and `max_completion_tokens`

---

## ⚙️ Configuration

### Minimal Setup
```yaml
providers:
  openai:
    type: openai
    api_key: sk-...

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
```

### With Failover
```yaml
providers:
  primary:
    type: openai
    api_key: sk-primary-...
  backup:
    type: openai
    api_key: sk-backup-...

models:
  gpt-4:
    providers:
      primary:
        priority: 0
        model_id: gpt-4
      backup:
        priority: 1
        model_id: gpt-4
```

### With Environment Variables
```yaml
providers:
  openai:
    type: openai
    api_key: ${OPENAI_API_KEY}
    base_url: ${OPENAI_BASE_URL:-https://api.openai.com/v1}
```

---

## 🔄 Failover Mechanism

**Failure Tracking:**
```
Request arrives
    ↓
Get available providers (sorted by priority)
    ↓
For each provider:
  ├─ Try chat_completion()
  ├─ On success: mark_success() → return response
  └─ On failure: mark_failure() → try next
    ↓
All failed? Return 503 error
```

**Failure Counter:**
- 1st failure: `consecutive_failures = 1` (enabled)
- 2nd failure: `consecutive_failures = 2` (enabled)
- 3rd failure: `consecutive_failures = 3` (disabled)
- After 10-minute cooldown: re-enable and reset to 0

---

## 🚀 Getting Started

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Configuration
Edit `config/config.yaml` with your providers and API keys

### 3. Run Server
```bash
cd src
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### 4. Test
```bash
curl http://localhost:8000/v1/models
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4", "messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## 🐳 Docker Deployment

### Build and Run
```bash
docker build -t llm-proxy .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -v $(pwd)/config:/app/config:ro \
  llm-proxy
```

### With Docker Compose
```bash
export OPENAI_API_KEY=sk-...
docker-compose up -d
```

---

## 🔧 Production Deployment

### Using Deployment Script
```bash
./deploy.sh production                    # Start production server
./deploy.sh production --create-service   # Create systemd service
./deploy.sh dev                           # Development with auto-reload
```

### Using systemd
```bash
sudo systemctl start llm-proxy
sudo systemctl status llm-proxy
sudo systemctl logs llm-proxy
```

### Using gunicorn
```bash
gunicorn --workers 4 --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 src.app:app
```

---

## 🔌 Adding New Providers

### Step 1: Create Provider Class
Create `src/providers/anthropic.py`:
```python
from .base import Provider

class AnthropicProvider(Provider):
    def translate_request(self, messages, model_id, **kwargs):
        # Convert OpenAI → Anthropic format
        pass
    
    def make_request(self, request_data):
        # Call Anthropic API
        pass
    
    def translate_response(self, response_data):
        # Convert Anthropic → OpenAI format
        pass
```

### Step 2: Register in registry.py
```python
PROVIDER_CLASSES = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,  # Add this
}
```

### Step 3: Configure in config.yaml
```yaml
providers:
  anthropic:
    type: anthropic
    api_key: ${ANTHROPIC_API_KEY}

models:
  claude-3:
    providers:
      anthropic:
        priority: 0
        model_id: claude-3-opus
```

---

## 🧪 Testing

Run basic tests:
```bash
python test_basic.py
```

Tests cover:
- ProviderInstance failure tracking
- Model provider selection
- Mock provider implementation
- Registry structure
- Failover behavior

---

## 📚 Documentation Guide

### Start Here
1. **INDEX.md** (this file) - Project overview and quick reference
2. **QUICKSTART.md** - Get up and running in 5 minutes
3. **README.md** - Complete feature documentation

### Deep Dive
4. **ARCHITECTURE.md** - System design, data flow, performance considerations
5. **PROJECT_SUMMARY.md** - High-level overview and feature list

### Reference
- `src/app.py` - FastAPI endpoint implementations
- `src/models.py` - Data model definitions
- `src/registry.py` - Provider/model registry
- `config/config.yaml` - Configuration examples

---

## 🔒 Security Best Practices

1. **Never commit API keys** - Use environment variables
2. **Use .env files** - Copy `.env.example` to `.env` and fill in values
3. **Restrict network access** - Only allow trusted clients
4. **HTTPS in production** - Deploy behind nginx/Apache with SSL
5. **Don't log sensitive data** - Be careful with logging
6. **Rotate API keys regularly** - Update credentials periodically
7. **Run as non-root** - Use unprivileged user in production
8. **Use systemd hardening** - See deploy.sh for systemd unit options

---

## ⚡ Performance Characteristics

- **Provider request timeout:** 60 seconds
- **Failure cooldown period:** 600 seconds (10 minutes)
- **Provider selection:** O(n log n) where n = providers per model
- **Provider lookup:** O(1) hash table
- **Failure detection:** Immediate (no waiting)
- **Automatic recovery:** Starts after cooldown expires

---

## 📈 Recommended Setup

### Development
```bash
./deploy.sh dev
# or
cd src && python -m uvicorn app:app --reload
```

### Production (Single Instance)
```bash
./deploy.sh production
```

### Production (Systemd)
```bash
sudo ./deploy.sh production --create-service
sudo systemctl start llm-proxy
```

### Production (Docker)
```bash
docker-compose up -d
```

### Production (Kubernetes)
Use Dockerfile with Kubernetes manifests

---

## 🎯 Common Use Cases

1. **Cost Optimization**
   - Route cheap requests to economical providers
   - Fallback to premium providers when needed
   - Save money by optimizing provider usage

2. **Reliability**
   - Use multiple providers for redundancy
   - Automatic failover ensures uptime
   - No manual intervention required

3. **Provider Testing**
   - A/B test different LLM providers
   - Compare quality and cost
   - Gradual migration between providers

4. **API Standardization**
   - Unified interface across providers
   - Map different provider model names to single ID
   - Consistent request/response format

5. **Load Distribution**
   - Distribute requests across multiple provider accounts
   - Avoid rate limiting issues
   - Optimize for throughput

---

## 🔮 Future Enhancements

- [ ] Async/await for concurrent requests
- [ ] Request caching layer
- [ ] Rate limiting per client
- [ ] Usage analytics and cost tracking
- [ ] Advanced circuit breaker patterns
- [ ] Streaming response support
- [ ] Request logging and audit trail
- [ ] Admin API for runtime configuration
- [ ] Prometheus metrics endpoint
- [ ] Provider health monitoring

---

## 📦 Dependencies

### Production
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation
- `requests` - HTTP client
- `pyyaml` - YAML parsing

### Optional (for production deployment)
- `gunicorn` - WSGI server
- `python-dotenv` - Environment variables

### Development
- All of the above
- `pytest` (for test framework)

---

## 🗂️ Quick File Reference

**Want to...**
- ...understand the system? → Read `ARCHITECTURE.md`
- ...get started quickly? → Read `QUICKSTART.md`
- ...use the API? → Read `README.md`
- ...add a provider? → See "Adding New Providers" section below
- ...deploy to production? → Run `./deploy.sh production`
- ...understand the code? → Start with `src/app.py`
- ...configure providers? → Edit `config/config.yaml`
- ...test locally? → Run `python test_basic.py`

---

## 📞 Troubleshooting

### "Registry not initialized"
→ Ensure `config/config.yaml` exists and is valid YAML

### "Model not found"
→ Check model ID matches config and run `GET /v1/models` to list available

### "All providers failed"
→ Verify API keys, base URLs, and network connectivity

### Provider keeps failing after 3 times
→ Check for rate limits, expired keys, or invalid model IDs

---

## 📋 Deployment Checklist

- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Copy `.env.example` to `.env` and fill in API keys
- [ ] Edit `config/config.yaml` with your providers
- [ ] Test locally: `cd src && python -m uvicorn app:app --reload`
- [ ] Test endpoints: `curl http://localhost:8000/v1/models`
- [ ] For Docker: `docker-compose up -d`
- [ ] For production: `./deploy.sh production`
- [ ] Verify health: `curl http://localhost:8000/health`
- [ ] Set up monitoring/logging
- [ ] Configure reverse proxy (nginx) with SSL
- [ ] Set up backups and disaster recovery

---

## 📄 License

MIT License

---

## 🎓 Learning Path

1. **Start** → INDEX.md (this file)
2. **Quick Setup** → QUICKSTART.md (5 min)
3. **Use the API** → README.md (features and examples)
4. **Understand Design** → ARCHITECTURE.md (deep dive)
5. **Extend System** → Add custom provider following the template
6. **Deploy** → Use docker-compose or deploy.sh script

---

**Built with FastAPI + Python 3.8+**
**Production Ready: ✅ Docker ✅ Systemd ✅ Tests ✅ Documentation**
**Total Lines: ~3,000 (code + docs)**