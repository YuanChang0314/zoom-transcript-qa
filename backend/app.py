# backend/app.py
import os, base64, requests
from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse

app = FastAPI()

ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")

def basic_auth_header():
    raw = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()
    return "Basic " + base64.b64encode(raw).decode()

@app.post("/oauth/exchange")
def oauth_exchange(payload: dict = Body(...)):
    """
    payload: { code, code_verifier, redirect_uri }
    """
    code = payload.get("code")
    code_verifier = payload.get("code_verifier")
    redirect_uri = payload.get("redirect_uri")

    if not (code and code_verifier and redirect_uri):
        return JSONResponse({"error": "missing params"}, status_code=400)

    token_url = "https://zoom.us/oauth/token"
    headers = {
        "Authorization": basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded"
    }
    # IMPORTANT: send as form/query params; Zoom expects x-www-form-urlencoded
    # and include code_verifier for PKCE
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier
    }
    resp = requests.post(token_url, headers=headers, data=data, timeout=20)
    try:
        resp.raise_for_status()
        return JSONResponse(resp.json(), status_code=200)
    except Exception:
        # bubble up zoom error body for debugging
        return JSONResponse({"stage":"token", "status": resp.status_code, **resp.json()}, status_code=resp.status_code)
