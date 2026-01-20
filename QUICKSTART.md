# Quick Start Guide

Get the OpenAI Proxy Server running in 5 minutes.

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

## Installation

### 1. Clone and Set Up

```bash
cd redisnotblue-ai
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Your API Keys

Edit `config/config.yaml` and add your OpenAI API key:

```yaml
providers:
  openai_primary:
    type: openai
    api_key: sk-your-api-key-here
    base_url: https://api.openai.com/v1
```

Or use environment variables:

```bash
export OPENAI_API_KEY="sk-your-api-key-here"
```

Then in `config/config.yaml`:

```yaml
providers:
  openai_primary:
    type: openai
    api_key: ${OPENAI_API_KEY}
```

### 3. Start the Server

```bash
cd src
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
Uvicorn running on http://0.0.0.0:8000
Press CTRL+C to quit
```

## Testing

### Check Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok"}
```

### List Models

```bash
curl http://localhost:8000/v1/models
```

Expected response:
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

### Send a Chat Completion Request

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Say hello!"}
    ]
  }'
```

Expected response:
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 12,
    "total_tokens": 22
  }
}
```

## Using with Python

```python
import openai

# Point to your local proxy
openai.api_base = "http://localhost:8000/v1"
openai.api_key = "anything"  # Not validated by proxy

# Use like normal OpenAI API
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

## Adding Multiple Providers

Edit `config/config.yaml` to add failover:

```yaml
providers:
  openai_primary:
    type: openai
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1

  openai_backup:
    type: openai
    api_key: ${OPENAI_BACKUP_API_KEY}
    base_url: https://api.openai.com/v1

models:
  gpt-4:
    owned_by: openai
    providers:
      openai_primary:
        priority: 0      # Try primary first
        model_id: gpt-4
      openai_backup:
        priority: 1      # Use backup if primary fails
        model_id: gpt-4
```

Now if the primary provider fails 3 times, requests will automatically use the backup.

## Troubleshooting

### "Connection refused"
- Is the server running? Check `http://localhost:8000/health`
- Check the port (default 8000)

### "Model not found"
- Check your request uses a model from `GET /v1/models`
- Verify config.yaml has the model defined

### "All providers failed"
- Check API keys are correct
- Verify provider base URLs are accessible
- Check network connectivity

### "Registry not initialized"
- Ensure `config/config.yaml` exists
- Check the config file is valid YAML

## Configuration Syntax

### Minimal Config

```yaml
providers:
  openai:
    type: openai
    api_key: your-key-here

models:
  gpt-4:
    providers:
      openai:
        priority: 0
        model_id: gpt-4
```

### Full Config with Failover

```yaml
providers:
  primary:
    type: openai
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1

  backup:
    type: openai
    api_key: ${OPENAI_BACKUP_API_KEY}
    base_url: https://api.openai.com/v1

models:
  gpt-4:
    owned_by: openai
    providers:
      primary:
        priority: 0
        model_id: gpt-4
      backup:
        priority: 1
        model_id: gpt-4

  gpt-3.5-turbo:
    owned_by: openai
    providers:
      primary:
        priority: 0
        model_id: gpt-3.5-turbo
      backup:
        priority: 1
        model_id: gpt-3.5-turbo
```

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Check out the [Project Structure](#) for code organization
- Add more providers by implementing the Provider base class
- Deploy to production with proper security settings

## Production Deployment

For production use:

1. **Use HTTPS**: Deploy behind nginx or similar with SSL
2. **Secure API Keys**: Use environment variables, never commit keys
3. **Add Authentication**: Add API key validation to protect your proxy
4. **Use Production ASGI**: Use gunicorn or similar instead of `--reload`
5. **Monitor Logs**: Set up logging and monitoring
6. **Rate Limiting**: Add rate limiting to prevent abuse

Example production start:

```bash
gunicorn -w 4 -b 0.0.0.0:8000 src.app:app
```

See [README.md](README.md) for more details.