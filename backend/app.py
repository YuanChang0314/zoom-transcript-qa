import base64
import os
from typing import Any, Dict

import requests
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID", "")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET", "")
ZOOM_REDIRECT_URI_FALLBACK = os.getenv("ZOOM_REDIRECT_URI", "")

def _zoom_basic_auth_header() -> str:
    creds = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("utf-8")

def _error(stage: str, status: int, zoom_error: Dict[str, Any]) -> JSONResponse:
    return JSONResponse({"stage": stage, "status": status, "zoom_error": zoom_error}, status_code=status)

@app.post("/oauth/exchange")
def oauth_exchange(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    """
    Exchange authorization code for access/refresh token using PKCE.
    Frontend must send: code, code_verifier, redirect_uri (from onAuthorized payload)
    """
    if not ZOOM_CLIENT_ID or not ZOOM_CLIENT_SECRET:
        return _error("token", 500, {"reason": "missing client credentials", "error": "server_misconfig"})

    code = payload.get("code")
    code_verifier = payload.get("code_verifier")
    redirect_uri = payload.get("redirect_uri") or ZOOM_REDIRECT_URI_FALLBACK

    if not code or not code_verifier or not redirect_uri:
        return _error("token", 400, {"reason": "missing required fields (code/code_verifier/redirect_uri)", "error": "invalid_request"})

    token_url = "https://zoom.us/oauth/token"
    headers = {
        "Authorization": _zoom_basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }

    try:
        resp = requests.post(token_url, headers=headers, data=data, timeout=20)
        if resp.status_code != 200:
            try:
                z = resp.json()
            except Exception:
                z = {"reason": resp.text, "error": "unknown"}
            return _error("token", resp.status_code, z)
        return JSONResponse(resp.json(), status_code=200)
    except requests.RequestException as e:
        return _error("token", 502, {"reason": str(e), "error": "network"})
