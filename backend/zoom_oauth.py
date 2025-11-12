# -*- coding: utf-8 -*-
"""
Minimal Zoom in-client OAuth scaffolding.
- /oauth/callback receives the code from zoomSdk.authorize()
- exchange_code_for_token(code) is a placeholder; implement with real Zoom OAuth endpoints.
"""

import os
import base64
import requests
from typing import Dict, Any, Optional

ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET", "")
ZOOM_REDIRECT_URI = os.getenv("ZOOM_REDIRECT_URI")

def exchange_code_for_token(code: str, code_verifier: Optional[str] = None) -> Dict[str, Any]:
    """
    Exchange authorization code for tokens.
    Supports:
      - Standard OAuth (Authorization Code + Basic auth)
      - PKCE (Zoom Apps in-client OAuth) with code_verifier
    """
    if not ZOOM_CLIENT_ID or not ZOOM_REDIRECT_URI:
        raise RuntimeError("Missing ZOOM_CLIENT_ID or ZOOM_REDIRECT_URI")

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": ZOOM_REDIRECT_URI,
    }

    if code_verifier:
        data["code_verifier"] = code_verifier

    if ZOOM_CLIENT_SECRET:
        basic = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
        headers["Authorization"] = f"Basic {basic}"
    else:
        data["client_id"] = ZOOM_CLIENT_ID

    resp = requests.post(TOKEN_URL, data=data, timeout=20)
    resp.raise_for_status()
    return resp.json()