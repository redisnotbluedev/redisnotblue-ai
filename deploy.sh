#!/bin/bash

# LLM Provider Proxy - Production Deployment Script
# This script sets up and runs the proxy server in production

set -e

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/venv"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-4}"
CONFIG_PATH="${CONFIG_PATH:-config/config.yaml}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check Python version
check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    log_info "Python version: $PYTHON_VERSION"
}

# Create virtual environment
setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        log_info "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi
    
    source "$VENV_DIR/bin/activate"
    log_info "Virtual environment activated"
}

# Install dependencies
install_deps() {
    log_info "Installing dependencies..."
    pip install --upgrade pip setuptools wheel > /dev/null
    pip install -r "$PROJECT_DIR/requirements.txt" > /dev/null
    log_info "Dependencies installed"
}

# Validate configuration
validate_config() {
    if [ ! -f "$CONFIG_PATH" ]; then
        log_error "Configuration file not found: $CONFIG_PATH"
        exit 1
    fi
    
    log_info "Configuration file validated: $CONFIG_PATH"
}

# Check environment variables
check_env() {
    if [ -z "$OPENAI_API_KEY" ]; then
        log_warn "OPENAI_API_KEY is not set"
    else
        log_info "OPENAI_API_KEY is set"
    fi
}

# Run with gunicorn (production)
run_gunicorn() {
    log_info "Starting server with gunicorn ($WORKERS workers)"
    log_info "Listening on 0.0.0.0:$PORT"
    
    cd "$PROJECT_DIR/src"
    gunicorn \
        --workers "$WORKERS" \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:"$PORT" \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        app:app
}

# Run with uvicorn (development)
run_uvicorn() {
    log_info "Starting server with uvicorn (development mode)"
    log_info "Listening on 0.0.0.0:$PORT"
    
    cd "$PROJECT_DIR/src"
    python -m uvicorn \
        --host 0.0.0.0 \
        --port "$PORT" \
        --reload \
        app:app
}

# Create systemd service file
create_systemd_service() {
    SERVICE_FILE="/etc/systemd/system/llm-proxy.service"
    
    log_info "Creating systemd service file..."
    
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=LLM Provider Proxy Server
After=network.target

[Service]
Type=notify
User=$(whoami)
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="CONFIG_PATH=$CONFIG_PATH"
EnvironmentFile=/etc/llm-proxy/.env

ExecStart=$VENV_DIR/bin/gunicorn \\
    --workers $WORKERS \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --bind 0.0.0.0:$PORT \\
    --access-logfile /var/log/llm-proxy/access.log \\
    --error-logfile /var/log/llm-proxy/error.log \\
    src.app:app

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    
    log_info "Service file created at $SERVICE_FILE"
    log_info "To enable: sudo systemctl enable llm-proxy"
    log_info "To start: sudo systemctl start llm-proxy"
}

# Parse arguments
DEPLOYMENT_MODE="${1:-development}"

# Main execution
main() {
    log_info "LLM Provider Proxy - Deployment Script"
    log_info "Mode: $DEPLOYMENT_MODE"
    
    check_python
    setup_venv
    install_deps
    validate_config
    check_env
    
    case "$DEPLOYMENT_MODE" in
        production)
            log_info "Installing gunicorn for production..."
            pip install gunicorn > /dev/null
            
            # Check if we should create systemd service
            if [ "$2" == "--create-service" ]; then
                create_systemd_service
                log_info "Service file created. Please configure /etc/llm-proxy/.env"
                exit 0
            fi
            
            run_gunicorn
            ;;
        development)
            run_uvicorn
            ;;
        *)
            log_error "Unknown deployment mode: $DEPLOYMENT_MODE"
            echo "Usage: $0 [development|production] [--create-service]"
            exit 1
            ;;
    esac
}

# Trap signals for graceful shutdown
trap 'log_info "Shutting down..."; exit 0' SIGTERM SIGINT

main "$@"