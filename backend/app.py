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
from fastapi.responses import JSONResponse

from qna import analyze_transcript_chunk
from zoom_oauth import exchange_code_for_token
from zoom_chat import send_chat_message

# Optional local ASR (disabled on cloud)
ENABLE_LOCAL_ASR = os.getenv("ENABLE_LOCAL_ASR", "false").lower() == "true"
if ENABLE_LOCAL_ASR:
    from asr_local import LocalASRSource

app = FastAPI(title="Zoom Transcript QA Backend (Render)")

# CORS (adjust to your frontend domain in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # tighten later
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
    await websocket.accept()
    async with meeting_lock:
        meeting_clients.setdefault(meeting_id, set()).add(websocket)
    try:
        while True:
            try:
                _ = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
    except WebSocketDisconnect:
        pass
    finally:
        async with meeting_lock:
            clients = meeting_clients.get(meeting_id, set())
            clients.discard(websocket)
            if not clients:
                meeting_clients.pop(meeting_id, None)

async def broadcast_to_meeting(meeting_id: str, message: Dict[str, Any]):
    text = json.dumps(message, ensure_ascii=False)
    async with meeting_lock:
        for ws in list(meeting_clients.get(meeting_id, set())):
            try:
                await ws.send_text(text)
            except Exception:
                meeting_clients[meeting_id].discard(ws)

# ---------------- OAuth callback ----------------
@app.post("/oauth/callback")
async def oauth_callback(code: str = Form(...)):
    token_payload = exchange_code_for_token(code)
    return JSONResponse(token_payload)

# ---------------- Optional: Zoom chat ----------------
@app.post("/chat")
async def chat_endpoint(access_token: str = Form(...), to_jid: str = Form(...), message: str = Form(...)):
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

    await broadcast_to_meeting(meeting_id, {"type": "transcript", "text": text})
    qna = analyze_transcript_chunk(text)
    await broadcast_to_meeting(meeting_id, {"type": "qna", "data": qna})
    return JSONResponse({"ok": True})

# ---------------- Optional local ASR loop ----------------
async def producer_loop():
    if not ENABLE_LOCAL_ASR or asr_source is None:
        return
    asr_source.start()
    try:
        # Demo: if using local mic, we broadcast to a fixed dev meeting_id
        dev_mid = os.getenv("DEV_MEETING_ID", "local-dev")
        while True:
            await asyncio.sleep(0.2)
            text = asr_source.get_chunk_text_if_ready()
            if not text:
                continue
            await broadcast_to_meeting(dev_mid, {"type": "transcript", "text": text})
            qna = analyze_transcript_chunk(text)
            await broadcast_to_meeting(dev_mid, {"type": "qna", "data": qna})
    finally:
        asr_source.stop()

@app.on_event("startup")
async def on_startup():
    if ENABLE_LOCAL_ASR:
        asyncio.create_task(producer_loop())

@app.get("/")
async def health():
    return {"status": "ok"}
