import base64
import hashlib
import json
import queue
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    def __init__(self, *args, code_queue=None, **kwargs):
        self.code_queue = code_queue
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET request to /oauth-callback."""
        if self.path.startswith('/oauth-callback'):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            code = params.get('code', [None])[0]
            state = params.get('state', [None])[0]

            if code and self.code_queue:
                self.code_queue.put({'code': code, 'state': state})
                print("Authorization code received. You can close the browser tab now.", flush=True)

            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><body><h1>Authentication successful! You can close this window.</h1></body></html>')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress server logs."""
        pass


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip('=')
    return code_verifier, code_challenge


def authenticate_antigravity() -> Dict[str, Any]:
    """
    Perform OAuth authentication for Antigravity.
    
    Returns:
        Dict with access_token, refresh_token, expires_in, etc.
    """
    client_id = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
    scopes = [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs"
    ]
    redirect_uri = "http://localhost:51121/oauth-callback"
    
    # Generate PKCE
    code_verifier, code_challenge = generate_pkce()
    
    # Build OAuth URL
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': ' '.join(scopes),
        'response_type': 'code',
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'state': secrets.token_urlsafe(16)
    }
    oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    
    # Start local server
    code_queue = queue.Queue()
    server = HTTPServer(('localhost', 51121), lambda *args, **kwargs: OAuthCallbackHandler(*args, code_queue=code_queue, **kwargs))
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    print("Local server started on http://localhost:51121", flush=True)

    # Open browser
    print("Opening browser for authentication...", flush=True)
    print(f"If browser doesn't open, visit: {oauth_url}", flush=True)
    webbrowser.open(oauth_url)

    # Wait for callback
    timeout = 300  # 5 minutes
    start_time = time.time()
    print("Waiting for authorization callback...", flush=True)
    code_received = None
    while code_received is None and (time.time() - start_time) < timeout:
        try:
            code_received = code_queue.get(timeout=0.1)
        except queue.Empty:
            continue

    server.shutdown()
    server_thread.join(timeout=5)  # Wait up to 5 seconds for thread to finish
    time.sleep(0.5)  # Small delay to ensure cleanup
    print("Server shut down.", flush=True)

    if not code_received or not code_received.get('code'):
        print("No authorization code received. Timeout or user cancelled.", flush=True)
        raise Exception("Authentication timeout or failed")

    print("Authorization code received, exchanging for tokens...", flush=True)

    # Exchange code for tokens
    import requests
    response = requests.post("https://oauth2.googleapis.com/token", data={
        'client_id': client_id,
        'client_secret': "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",
        'code': code_received['code'],
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
        'code_verifier': code_verifier
    })

    if response.status_code != 200:
        print(f"Token exchange failed with status {response.status_code}: {response.text}", flush=True)
        raise Exception(f"Token exchange failed: {response.text}")

    tokens = response.json()
    print("Token exchange successful.", flush=True)
    return tokens


if __name__ == "__main__":
    tokens = authenticate_antigravity()
    print("Authentication successful!", flush=True)
    print("Your refresh token is:", flush=True)
    print(tokens['refresh_token'], flush=True)
    print("\nAdd this to your config.yaml under api_keys for the antigravity provider.", flush=True)