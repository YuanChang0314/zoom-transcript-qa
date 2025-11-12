# app/oauth.py  —— 完整可用的最小换 token 实现（保留英文注释）
import os, base64, requests
from typing import Dict, Any, Optional
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter()

ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET", "")
ZOOM_REDIRECT_URI = os.getenv("ZOOM_REDIRECT_URI")
TOKEN_URL = "https://zoom.us/oauth/token"

def exchange_code_for_token(code: str, code_verifier: Optional[str] = None) -> Dict[str, Any]:
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
        data["client_id"] = ZOOM_CLIENT_ID  # pure PKCE

    resp = requests.post(TOKEN_URL, headers=headers, data=data, timeout=20)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        raise RuntimeError(f"Zoom token exchange failed: {resp.status_code} {resp.text}")
    return resp.json()

@router.get("/oauth/callback")
def oauth_callback(code: str = Query(...), state: Optional[str] = None, code_verifier: Optional[str] = None):
    try:
        tokens = exchange_code_for_token(code, code_verifier=code_verifier)
        return JSONResponse(tokens)
    except Exception as e:
        return JSONResponse({"error": "token_exchange_failed", "detail": str(e)}, status_code=500)
