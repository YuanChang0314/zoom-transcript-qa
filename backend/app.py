# -*- coding: utf-8 -*-
"""
FastAPI backend for Zoom App integration:
- WebSocket endpoint: /ws connects a meeting panel to receive ASR+QnA JSON payloads.
- Background loop:
    - Reads audio chunks from LocalASRSource
    - Runs Whisper transcription and LLM analysis
    - Broadcasts results to all clients of the same meeting
- OAuth callback: /oauth/callback to receive Zoom in-client OAuth code
- Optional: /chat to send message into Zoom Chat (requires token + to_jid)

Run:
  export OPENAI_API_KEY=sk-...
  uvicorn app:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import asyncio
import json
import uuid
from typing import Dict, List, Set, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from asr_local import LocalASRSource
from qna import analyze_transcript_chunk
from zoom_oauth import exchange_code_for_token
from zoom_chat import send_chat_message

app = FastAPI(title="Zoom Transcript QA Backend")

# CORS for local dev / Zoom allowlisted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # refine this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------ Connection registry per meeting ------------
# meeting_id -> set of websockets
meeting_clients: Dict[str, Set[WebSocket]] = {}
meeting_lock = asyncio.Lock()

# Shared ASR source (PoC: single machine microphone)
asr_source = LocalASRSource()

# ------------ WebSocket endpoint ------------
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, meeting_id: str = Query(..., description="meeting UUID or id")):
    await websocket.accept()
    async with meeting_lock:
        if meeting_id not in meeting_clients:
            meeting_clients[meeting_id] = set()
        meeting_clients[meeting_id].add(websocket)

    try:
        # Keep the connection alive; we do not expect messages from client right now.
        while True:
            # Wait for ping/pong or small delay
            try:
                _ = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
    except WebSocketDisconnect:
        pass
    finally:
        async with meeting_lock:
            if meeting_id in meeting_clients:
                meeting_clients[meeting_id].discard(websocket)
                if not meeting_clients[meeting_id]:
                    meeting_clients.pop(meeting_id, None)

# ------------ OAuth callback ------------
@app.post("/oauth/callback")
async def oauth_callback(code: str = Form(...)):
    """
    Frontend calls zoomSdk.authorize(); sends code here via fetch() FormData.
    Exchange the code for token and store as needed (DB/redis/etc.); here we return it in response for PoC.
    """
    token_payload = exchange_code_for_token(code)
    return JSONResponse(token_payload)

# ------------ Optional: Zoom chat relay ------------
@app.post("/chat")
async def chat_endpoint(access_token: str = Form(...), to_jid: str = Form(...), message: str = Form(...)):
    ok = send_chat_message(access_token, to_jid, message)
    return JSONResponse({"ok": ok})

# ------------ Background producer task ------------
async def producer_loop():
    """
    Background task:
    - Start ASR source (local mic)
    - Every time a chunk is ready: transcribe -> analyze -> broadcast to all connected meetings
    """
    asr_source.start()
    try:
        while True:
            await asyncio.sleep(0.2)
            text = asr_source.get_chunk_text_if_ready()
            if not text:
                continue

            payload = {
                "type": "transcript",
                "text": text
            }
            await broadcast(payload)

            qna = analyze_transcript_chunk(text)
            payload2 = {
                "type": "qna",
                "data": qna
            }
            await broadcast(payload2)
    finally:
        asr_source.stop()

async def broadcast(message: Dict[str, Any]):
    """
    Broadcast to all meetings (PoC). If you want to scope to a single meeting_id,
    add routing logic (e.g., keep per-meeting buffers and tags).
    For this PoC, we broadcast to everyone connected because the local mic is a single source.
    """
    text = json.dumps(message, ensure_ascii=False)
    async with meeting_lock:
        # In production, route by meeting_id. Here we push to all clients.
        for meeting_id, conns in list(meeting_clients.items()):
            stale = []
            for ws in list(conns):
                try:
                    await ws.send_text(text)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                conns.discard(ws)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(producer_loop())

# ------------ Health check ------------
@app.get("/")
async def root():
    return {"status": "ok"}
