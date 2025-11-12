# zoom_oauth.py
import base64
import os
from typing import Any, Dict
import requests

ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")
ZOOM_REDIRECT_URI = os.getenv("ZOOM_REDIRECT_URI")

def exchange_code_for_token(code: str) -> Dict[str, Any]:
    """
    Exchange authorization code for Zoom OAuth tokens.
    Returns a dict payload; if Zoom returns an error, the dict will include
    'status' and 'zoom_error' for debugging instead of raising a 500.
    """
    if not ZOOM_CLIENT_ID or not ZOOM_CLIENT_SECRET or not ZOOM_REDIRECT_URI:
        return {
            "status": 500,
            "error": "missing_env",
            "detail": {
                "has_client_id": bool(ZOOM_CLIENT_ID),
                "has_client_secret": bool(ZOOM_CLIENT_SECRET),
                "has_redirect_uri": bool(ZOOM_REDIRECT_URI),
            },
        }

    token_url = "https://zoom.us/oauth/token"
    basic = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()

    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # Use form body (data), not JSON
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": ZOOM_REDIRECT_URI,  # MUST match exactly with app config
    }

    try:
        resp = requests.post(token_url, headers=headers, data=data, timeout=15)
        # Try to parse JSON regardless of status
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw": resp.text}

        if resp.status_code != 200:
            return {"status": resp.status_code, "zoom_error": payload}

        return payload
    except requests.RequestException as e:
        return {"status": 502, "error": "request_exception", "detail": str(e)}
