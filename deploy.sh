#!/bin/bash

set -e

# Build and run OpenAI proxy server

echo "Building Docker image..."
docker build -t openai-proxy .

echo "Starting container..."
docker run -d \
  -p 8000:8000 \
  -v "$(pwd)/config:/app/config" \
  -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
  --name openai-proxy \
  openai-proxy

echo "Server running on http://localhost:8000"
echo "View logs: docker logs -f openai-proxy"