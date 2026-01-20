# LLM Provider Proxy - Project Summary

## 🎯 Overview

A production-ready FastAPI server that acts as a unified proxy to multiple LLM providers (OpenAI, Anthropic, etc.) with automatic failover, intelligent provider routing, and comprehensive failure tracking.

## ✨ Key Features

- **Multi-Provider Support**: Route requests to multiple LLM providers simultaneously
- **Automatic Failover**: Seamlessly switch to backup providers on failure
- **Failure Tracking**: Track consecutive failures and disable providers after 3 failures
- **Automatic Recovery**: Re-enable providers after a 10-minute cooldown
- **Priority Routing**: Configure provider priority (0 = highest priority)
- **OpenAI-Compatible**: Drop-in replacement for OpenAI API (`/v1/chat/completions`, `/v1/models`)
- **Easy Configuration**: YAML-based provider and model management
- **Production Ready**: Includes Docker, deployment scripts, and health checks

## 📦 What's Included

### Core Application
- **src/app.py** - FastAPI application with 3 endpoints
- **src/models.py** - Data models (Message, Model, ProviderInstance)
- **src/registry.py** - Provider and model registry with config loading
- **src/providers/base.py** - Abstract provider base class
- **src/providers/openai.py** - OpenAI provider implementation

### Documentation
- **README.md** - Comprehensive documentation (416 lines)
- **QUICKSTART.md** - 5-minute quick start guide
- **ARCHITECTURE.md** - Detailed architecture documentation (590 lines)
- **PROJECT_SUMMARY.md** - This file

### Configuration & Deployment
- **config/config.yaml** - Example configuration with multiple providers
- **requirements.txt** - Python dependencies
- **Dockerfile** - Multi-stage Docker image (optimized for size)
- **docker-compose.yml** - Docker Compose configuration with optional nginx
- **deploy.sh** - Production deployment script with systemd integration
- **.env.example** - Environment variables template
- **.gitignore** - Comprehensive gitignore

### Testing
- **test_basic.py** - Basic functionality tests with mock providers

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Providers
Edit `config/config.yaml`:
```yaml
providers:
  openai:
    type: openai
    api_key: sk-your-key
    
models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
```

### 3. Start Server
```bash
cd src
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### 4. Test It
```bash
curl http://localhost:8000/v1/models
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## 📚 API Endpoints

### POST /v1/chat/completions
Send a chat completion request (OpenAI-compatible).

**Parameters:**
- `model` (required): Model name
- `messages` (required): Array of message objects
- `temperature` (optional): 0-2
- `max_tokens` or `max_completion_tokens` (optional): Max response tokens
- `top_p` (optional): 0-1
- `stop` (optional): Stop sequence(s)

**Response:** OpenAI-format chat completion response

### GET /v1/models
List all available models.

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4",
      "object": "model",
      "created": 1234567890,
      "owned_by": "openai"
    }
  ]
}
```

### GET /health
Health check endpoint.

**Response:** `{"status": "ok"}`

## 🔄 Failover Mechanism

```
Request arrives
    ↓
Get model's available providers (sorted by priority)
    ↓
For each provider in order:
  ├─ Try to get completion
  ├─ On success: mark_success() → return response
  └─ On failure: mark_failure() → continue to next
    ↓
If all fail:
  └─ Return 503 error with last failure details

Failure Tracking:
  ├─ 1st failure: consecutive_failures = 1
  ├─ 2nd failure: consecutive_failures = 2
  ├─ 3rd failure: consecutive_failures = 3 → DISABLED
  ├─ Cooldown: 10 minutes
  └─ After cooldown: re-enable and reset to 0
```

## 🛠️ Architecture

### Component Diagram
```
Client Request
    ↓
FastAPI App (app.py)
    ├─ Parse request with Pydantic
    ├─ Get model from registry
    └─ Try providers in priority order
         ↓
    ModelRegistry (registry.py)
    ├─ Load config from YAML
    ├─ Store providers & models
    └─ Route requests
         ↓
    Model + ProviderInstances
    ├─ Track availability
    ├─ Sort by priority
    └─ Handle failures
         ↓
    Provider Abstraction (base.py)
    ├─ translate_request()
    ├─ make_request()
    └─ translate_response()
         ↓
    Concrete Providers
    ├─ OpenAI (openai.py)
    ├─ Anthropic (template)
    └─ Custom providers...
         ↓
    LLM Provider APIs
```

### Data Models

**Message**
- `role`: "user", "assistant", "system"
- `content`: Message text

**ProviderInstance**
- `provider`: Reference to Provider
- `priority`: Sort order
- `model_id`: Provider-specific model name
- `enabled`: Currently available
- `consecutive_failures`: Failure count
- `last_failure`: Unix timestamp

**Model**
- `id`: Unified model name
- `provider_instances`: List of ProviderInstance
- `created`: Unix timestamp
- `owned_by`: Provider name

## 📝 Configuration

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
    api_key: sk-primary
  backup:
    type: openai
    api_key: sk-backup

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

## 🐳 Docker Deployment

### Using Docker
```bash
docker build -t llm-proxy .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -v $(pwd)/config:/app/config:ro \
  llm-proxy
```

### Using Docker Compose
```bash
export OPENAI_API_KEY=sk-...
docker-compose up -d
```

## 🚀 Production Deployment

### Using Deployment Script
```bash
# Development with auto-reload
./deploy.sh dev

# Production with gunicorn
./deploy.sh production

# With systemd service
./deploy.sh production --create-service
```

### Using systemd
```bash
sudo systemctl start llm-proxy
sudo systemctl status llm-proxy
sudo systemctl logs llm-proxy
```

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

## 📊 Performance

- **Request timeout**: 60 seconds per provider
- **Failure cooldown**: 600 seconds (10 minutes, configurable)
- **Provider selection**: O(n log n) where n = providers per model
- **Provider lookup**: O(1) hash table

## 🔒 Security Considerations

⚠️ **This proxy handles API keys - handle carefully:**

1. **Never commit API keys** - Use environment variables
2. **Use .env files** - Load from environment, not config files
3. **Restrict network access** - Only allow trusted clients
4. **Use HTTPS in production** - Deploy behind nginx/Apache with SSL
5. **Don't log sensitive data** - Be careful with logging
6. **Rotate API keys** - Regularly update credentials
7. **Use non-root user** - Run server as unprivileged user

## 📁 Project Structure

```
redisnotblue-ai/
├── src/                          # Application code
│   ├── app.py                   # FastAPI application
│   ├── models.py                # Data models
│   ├── registry.py              # Provider/model registry
│   ├── __init__.py
│   └── providers/               # Provider implementations
│       ├── base.py              # Abstract base class
│       ├── openai.py            # OpenAI provider
│       └── __init__.py
├── config/
│   └── config.yaml              # Configuration file
├── README.md                     # Full documentation
├── QUICKSTART.md                # Quick start guide
├── ARCHITECTURE.md              # Architecture details
├── PROJECT_SUMMARY.md           # This file
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Docker image
├── docker-compose.yml           # Docker Compose config
├── deploy.sh                    # Deployment script
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore rules
└── test_basic.py               # Basic tests
```

## 🧪 Testing

Run basic tests:
```bash
python3 test_basic.py
```

Test the API:
```bash
# Health check
curl http://localhost:8000/health

# List models
curl http://localhost:8000/v1/models

# Chat completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "test"}]
  }'
```

## 📖 Documentation Files

1. **README.md** (9.7 KB)
   - Complete feature documentation
   - Installation instructions
   - API endpoint details
   - Usage examples
   - Error handling guide
   - Extension guide for new providers

2. **QUICKSTART.md** (5.1 KB)
   - 5-minute setup guide
   - Configuration examples
   - Troubleshooting tips
   - Production deployment notes

3. **ARCHITECTURE.md** (18 KB)
   - System architecture diagrams
   - Component details
   - Request flow documentation
   - Failure recovery mechanism
   - Configuration schema
   - Performance characteristics
   - Security considerations
   - Future enhancements

4. **PROJECT_SUMMARY.md** (This file)
   - Quick overview
   - Key features
   - Architecture summary
   - Quick start guide

## 🎯 Use Cases

1. **Cost Optimization**: Route expensive requests to cheaper providers, fallback to premium when needed
2. **Reliability**: Use multiple providers for redundancy and automatic failover
3. **Model Mapping**: Unified API across different provider model names
4. **Rate Limit Handling**: Distribute load across multiple provider accounts
5. **Provider Testing**: A/B test different LLM providers
6. **Migration**: Gradually migrate from one provider to another

## 🔮 Future Enhancements

- [ ] Async/await for concurrent requests
- [ ] Request caching
- [ ] Rate limiting per client
- [ ] Usage analytics and cost tracking
- [ ] Advanced circuit breaker logic
- [ ] Streaming response support
- [ ] Request logging and audit trail
- [ ] Admin API for runtime configuration
- [ ] Prometheus metrics endpoint
- [ ] GraphQL endpoint support

## 📝 License

MIT

## 🤝 Contributing

This is a template project. Extend it by:
1. Adding new provider implementations
2. Implementing additional endpoints
3. Adding middleware for authentication
4. Setting up monitoring and alerting
5. Creating provider-specific optimizations

## 📞 Support

For issues or questions:
1. Check the troubleshooting section in README.md
2. Review ARCHITECTURE.md for design details
3. Check test_basic.py for example usage
4. Review provider implementations for API details

---

**Built with**: FastAPI, Pydantic, YAML, Python 3.8+
**Production Ready**: ✅ Docker, ✅ Systemd, ✅ Health checks, ✅ Error handling