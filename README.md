# OpenAI Proxy

A FastAPI server that acts as a proxy to OpenAI's API with automatic failover and round-robin API key rotation.

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure `config/config.yaml`. Example:
```yaml
providers:
  openai_primary:
    type: openai
    api_key: ${OPENAI_API_KEY}

models:
  gpt-4:
    owned_by: openai
    providers:
      openai_primary:
        priority: 0
        model_id: gpt-4
```

3. Run the server:
```bash
cd src
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

## API

### POST /v1/chat/completions
Standard OpenAI chat completion endpoint.

### GET /v1/models
List available models.

### GET /health
Health check.

## Features

- **Multi-provider failover**: Automatic switching between providers
- **API key rotation**: Round-robin rotation across multiple keys
- **Failure handling**: Automatic cooldown and retry logic
- **OpenAI-compatible**: Drop-in replacement for OpenAI API

## Configuration

Set API keys via environment variables in `config.yaml`:
```yaml
api_key: ${OPENAI_API_KEY}
```

Or directly in the config file (not recommended for production).
```
