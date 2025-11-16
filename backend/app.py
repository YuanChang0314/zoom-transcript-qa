# -*- coding: utf-8 -*-
"""
FastAPI backend for Zoom App integration (Render-ready):
- WebSocket per meeting: /ws?meeting_id=...
- Optional: POST /ingest to push transcript text (useful before wiring a meeting bot)
- OAuth callback: POST /oauth/callback
- Optional: POST /chat to send Zoom Chat message (needs access_token)
- Cloud friendly:
  - ENABLE_LOCAL_ASR=false on Render (do not start local microphone)
  - Broadcast strictly by meeting_id
"""

import os
import asyncio
import json
from typing import Dict, Set, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from qna import analyze_transcript_chunk
from zoom_oauth import exchange_code_for_token
from zoom_chat import send_chat_message

# Optional local ASR (disabled on cloud)
ENABLE_LOCAL_ASR = os.getenv("ENABLE_LOCAL_ASR", "false").lower() == "true"
if ENABLE_LOCAL_ASR:
    from asr_local import LocalASRSource

app = FastAPI(title="Zoom Transcript QA Backend (Render)")

# CORS - Allow Zoom domains and your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",  # For development - tighten in production
        "https://*.zoom.us",
        "https://*.zoom.com",
        "https://*.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# meeting_id -> set(websockets)
meeting_clients: Dict[str, Set[WebSocket]] = {}
meeting_lock = asyncio.Lock()

# Optional local ASR source (only if enabled)
asr_source = None
if ENABLE_LOCAL_ASR:
    asr_source = LocalASRSource()

# ---------------- WebSocket ----------------
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, meeting_id: str = Query(..., description="meeting UUID or number")):
    """WebSocket endpoint for real-time transcript and Q&A delivery"""
    await websocket.accept()
    print(f"[WS] Client connected for meeting: {meeting_id}")
    
    async with meeting_lock:
        meeting_clients.setdefault(meeting_id, set()).add(websocket)
    
    try:
        while True:
            try:
                # Keep connection alive with timeout
                _ = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
    except WebSocketDisconnect:
        print(f"[WS] Client disconnected from meeting: {meeting_id}")
    except Exception as e:
        print(f"[WS] Error in meeting {meeting_id}: {e}")
    finally:
        async with meeting_lock:
            clients = meeting_clients.get(meeting_id, set())
            clients.discard(websocket)
            if not clients:
                meeting_clients.pop(meeting_id, None)
        print(f"[WS] Cleaned up connection for meeting: {meeting_id}")

async def broadcast_to_meeting(meeting_id: str, message: Dict[str, Any]):
    """Broadcast message to all clients connected to a specific meeting"""
    text = json.dumps(message, ensure_ascii=False)
    async with meeting_lock:
        dead_connections = set()
        for ws in list(meeting_clients.get(meeting_id, set())):
            try:
                await ws.send_text(text)
            except Exception as e:
                print(f"[WS] Failed to send to client in meeting {meeting_id}: {e}")
                dead_connections.add(ws)
        
        # Clean up dead connections
        if dead_connections:
            for ws in dead_connections:
                meeting_clients[meeting_id].discard(ws)

# ---------------- OAuth callback ----------------
@app.api_route("/oauth/callback", methods=["GET", "POST"])
async def oauth_callback(request: Request) -> JSONResponse:
    """
    Unified OAuth callback that works for both GET (?code=...) and POST (form-encoded).
    It surfaces Zoom's token-exchange errors instead of returning a blank 500.
    """
    code = request.query_params.get("code")

    # If POST, Zoom (or future flows) may send code in form body
    if not code and request.method == "POST":
        try:
            form = await request.form()
            code = form.get("code")
        except Exception as e:
            print(f"[OAuth] Failed to parse form: {e}")

    if not code:
        # also handle error returned from authorize step if present
        auth_error = request.query_params.get("error")
        auth_error_desc = request.query_params.get("error_description", "")
        if auth_error:
            print(f"[OAuth] Authorization error: {auth_error} - {auth_error_desc}")
            return JSONResponse({
                "stage": "authorize", 
                "error": auth_error,
                "error_description": auth_error_desc
            }, status_code=400)
        
        print("[OAuth] Missing code parameter")
        return JSONResponse({
            "error": "missing_code",
            "detail": "No authorization code provided"
        }, status_code=400)

    try:
        print(f"[OAuth] Exchanging code for token...")
        token_payload = exchange_code_for_token(code)
        
        # If exchange returns a dict with error status, surface it
        if isinstance(token_payload, dict):
            if token_payload.get("status") and token_payload.get("status") != 200:
                print(f"[OAuth] Token exchange failed: {token_payload}")
                return JSONResponse({
                    "stage": "token", 
                    **token_payload
                }, status_code=token_payload.get("status", 502))
            
            # Check for Zoom API errors
            if "error" in token_payload:
                print(f"[OAuth] Zoom error: {token_payload}")
                return JSONResponse({
                    "stage": "zoom_api",
                    **token_payload
                }, status_code=400)
        
        print("[OAuth] Token exchange successful")
        return JSONResponse(token_payload)
        
    except Exception as e:
        print(f"[OAuth] Exception during token exchange: {e}")
        return JSONResponse({
            "error": "token_exchange_failed", 
            "detail": str(e)
        }, status_code=500)

# ---------------- Optional: Zoom chat ----------------
@app.post("/chat")
async def chat_endpoint(access_token: str = Form(...), to_jid: str = Form(...), message: str = Form(...)):
    """Send a Zoom chat message"""
    ok = send_chat_message(access_token, to_jid, message)
    return JSONResponse({"ok": ok})

# ---------------- Ingest endpoint (text push) ----------------
@app.post("/ingest")
async def ingest_endpoint(meeting_id: str = Form(...), text: str = Form(...)):
    """
    Push a transcript text for a given meeting (useful before wiring real meeting bot).
    """
    if not text.strip():
        return JSONResponse({"ok": True, "skipped": True})

    print(f"[Ingest] Received text for meeting {meeting_id}: {text[:100]}...")
    
    await broadcast_to_meeting(meeting_id, {"type": "transcript", "text": text})
    qna = analyze_transcript_chunk(text)
    await broadcast_to_meeting(meeting_id, {"type": "qna", "data": qna})
    
    return JSONResponse({"ok": True})

# ---------------- Optional local ASR loop ----------------
async def producer_loop():
    if not ENABLE_LOCAL_ASR or asr_source is None:
        return
    
    print("[ASR] Starting local audio capture...")
    asr_source.start()
    
    try:
        # Demo: if using local mic, we broadcast to a fixed dev meeting_id
        dev_mid = os.getenv("DEV_MEETING_ID", "local-dev")
        while True:
            await asyncio.sleep(0.2)
            text = asr_source.get_chunk_text_if_ready()
            if not text:
                continue
            print(f"[ASR] Transcribed: {text[:100]}...")
            await broadcast_to_meeting(dev_mid, {"type": "transcript", "text": text})
            qna = analyze_transcript_chunk(text)
            await broadcast_to_meeting(dev_mid, {"type": "qna", "data": qna})
    finally:
        asr_source.stop()
        print("[ASR] Stopped local audio capture")

@app.on_event("startup")
async def on_startup():
    print("[App] Starting up...")
    print(f"[App] ENABLE_LOCAL_ASR: {ENABLE_LOCAL_ASR}")
    print(f"[App] ZOOM_CLIENT_ID: {'set' if os.getenv('ZOOM_CLIENT_ID') else 'NOT SET'}")
    print(f"[App] ZOOM_CLIENT_SECRET: {'set' if os.getenv('ZOOM_CLIENT_SECRET') else 'NOT SET'}")
    print(f"[App] ZOOM_REDIRECT_URI: {os.getenv('ZOOM_REDIRECT_URI', 'NOT SET')}")
    
    if ENABLE_LOCAL_ASR:
        asyncio.create_task(producer_loop())

@app.get("/")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "Zoom Transcript QA Backend",
        "local_asr_enabled": ENABLE_LOCAL_ASR
    }

@app.get("/debug/meetings")
async def debug_meetings():
    """Debug endpoint to see active meeting connections"""
    async with meeting_lock:
        return {
            "active_meetings": list(meeting_clients.keys()),
            "connection_counts": {mid: len(clients) for mid, clients in meeting_clients.items()}
        }