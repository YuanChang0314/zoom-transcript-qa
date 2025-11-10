# -*- coding: utf-8 -*-
"""
Minimal Zoom in-client OAuth scaffolding.
- /oauth/callback receives the code from zoomSdk.authorize()
- exchange_code_for_token(code) is a placeholder; implement with real Zoom OAuth endpoints.
"""

import os
import base64
import requests
from typing import Dict, Any

ZOOM_CLIENT_ID = os.getenv("fzZWIO_CQamd_R8XiG7Q1A", "")
ZOOM_CLIENT_SECRET = os.getenv("a8ilzXuHY3b9bdXYV50oX2KmE3DSl24n", "")
ZOOM_REDIRECT_URI = os.getenv("ZOOM_REDIRECT_URI", "https://your.domain.com/oauth/callback")

def exchange_code_for_token(code: str) -> Dict[str, Any]:
    """
    Implement the OAuth token exchange with Zoom's OAuth endpoint.
    This function returns a dict like:
    {"access_token": "...", "refresh_token": "...", "expires_in": 3600, ...}
    """
    if not ZOOM_CLIENT_ID or not ZOOM_CLIENT_SECRET:
        # PoC mode: return fake payload so frontend flow does not break.
        return {"access_token": "DUMMY", "refresh_token": "DUMMY", "expires_in": 3600}

    token_url = "https://zoom.us/oauth/token"
    auth = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    params = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": ZOOM_REDIRECT_URI
    }
    resp = requests.post(token_url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()
