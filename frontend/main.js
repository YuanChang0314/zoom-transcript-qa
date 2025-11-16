const BACKEND_BASE = "https://zoom-transcript-qa.onrender.com"; 
const WS_URL = `${BACKEND_BASE.replace("https://", "wss://")}/ws`;
const OAUTH_CALLBACK = `${BACKEND_BASE}/oauth/callback`;

(function () {
  const state = {
    meetingId: null,
    ws: null,
    accessToken: null,
    installed: false
  };

  const elCtx = document.getElementById("ctx");
  const elAuth = document.getElementById("auth");
  const elTrans = document.getElementById("transcripts");
  const elQnA = document.getElementById("qna");

  function logJSON(el, obj) {
    el.textContent = JSON.stringify(obj, null, 2);
  }

  function pushCard(container, text) {
    const div = document.createElement("div");
    div.className = "card";
    div.textContent = text;
    container.prepend(div);
  }

  // Configure Zoom Apps SDK
  zoomSdk.config({
    capabilities: [
      "authorize",
      "getMeetingContext",
      "getUserContext",
      "postMessage",
      "expandApp"
    ]
  }).then(() => {
    state.installed = true;
    pushCard(elTrans, "[SDK] Initialized successfully");
  }).catch((e) => {
    console.warn("Zoom SDK config failed:", e);
    pushCard(elTrans, `[SDK] Config failed: ${e.message || e}`);
  });

  // Buttons
  document.getElementById("btn-auth").addEventListener("click", async () => {
    try {
      if (!state.installed) {
        throw new Error("Zoom SDK not initialized. This app must run inside Zoom client.");
      }
      
      pushCard(elAuth, "Starting authorization...");
      const res = await zoomSdk.authorize({ scopes: [] });
      logJSON(elAuth, { step: "got_code", code: res.code });
      
      // Exchange code for access token using GET request with query parameter
      pushCard(elAuth, "Exchanging code for token...");
      const callbackUrl = `${OAUTH_CALLBACK}?code=${encodeURIComponent(res.code)}`;
      
      const r = await fetch(callbackUrl, { 
        method: "GET",
        headers: {
          "Accept": "application/json"
        }
      });
      
      if (!r.ok) {
        const errorText = await r.text();
        throw new Error(`HTTP ${r.status}: ${errorText}`);
      }
      
      const token = await r.json();
      
      // Check if token exchange returned an error
      if (token.error || token.stage) {
        logJSON(elAuth, { 
          error: "Token exchange failed", 
          details: token 
        });
        return;
      }
      
      state.accessToken = token.access_token || null;
      logJSON(elAuth, { 
        success: true, 
        access_token: token.access_token ? "***" : null,
        token_type: token.token_type,
        expires_in: token.expires_in
      });
      pushCard(elAuth, "✓ Authorization successful");
      
    } catch (e) {
      console.error("Auth error:", e);
      logJSON(elAuth, { 
        error: e.message || String(e),
        type: e.name,
        details: e.stack 
      });
      pushCard(elAuth, `✗ Auth failed: ${e.message}`);
    }
  });

  document.getElementById("btn-context").addEventListener("click", async () => {
    try {
      if (!state.installed) {
        // Fallback for testing outside Zoom
        state.meetingId = "local-dev";
        logJSON(elCtx, { 
          outsideZoom: true, 
          meetingId: state.meetingId,
          note: "Using fallback meeting ID for local testing"
        });
        pushCard(elCtx, "Using local-dev meeting ID (outside Zoom)");
        return;
      }
      
      pushCard(elCtx, "Getting meeting context...");
      const ctx = await zoomSdk.getMeetingContext();
      state.meetingId = ctx.meetingUUID || ctx.meetingNumber || ctx.sessionUUID || "local-dev";
      logJSON(elCtx, ctx);
      pushCard(elCtx, `✓ Meeting ID: ${state.meetingId}`);
      
    } catch (e) {
      console.error("Context error:", e);
      // Fallback to local-dev
      state.meetingId = "local-dev";
      logJSON(elCtx, { 
        error: e.message || String(e),
        fallback: true, 
        meetingId: state.meetingId 
      });
      pushCard(elCtx, `Using fallback meeting ID: ${state.meetingId}`);
    }
  });

  document.getElementById("btn-connect").addEventListener("click", async () => {
    try {
      // Close existing connection if any
      if (state.ws && state.ws.readyState !== WebSocket.CLOSED) {
        state.ws.close();
        await new Promise(resolve => setTimeout(resolve, 100));
      }

      const mid = state.meetingId || "local-dev";
      const wsFullUrl = `${WS_URL}?meeting_id=${encodeURIComponent(mid)}`;
      
      pushCard(elTrans, `[WS] Connecting to ${wsFullUrl}`);
      const ws = new WebSocket(wsFullUrl);
      state.ws = ws;

      ws.onopen = () => {
        pushCard(elTrans, "[WS] ✓ Connected successfully");
        console.log("WebSocket connected");
      };
      
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.type === "heartbeat") {
            console.log("Heartbeat received");
            return;
          }
          if (data.type === "transcript") {
            pushCard(elTrans, `[Transcript] ${data.text}`);
          } else if (data.type === "qna") {
            pushCard(elQnA, JSON.stringify(data.data, null, 2));
          } else {
            pushCard(elTrans, `[Unknown] ${ev.data}`);
          }
        } catch (err) {
          console.error("Message parse error:", err);
          pushCard(elTrans, `[Raw] ${ev.data}`);
        }
      };
      
      ws.onclose = (ev) => {
        const reason = ev.reason || "No reason provided";
        const code = ev.code;
        pushCard(elTrans, `[WS] ✗ Closed (code: ${code}, reason: ${reason})`);
        console.log("WebSocket closed:", code, reason);
      };
      
      ws.onerror = (e) => {
        pushCard(elTrans, "[WS] ✗ Connection error - check backend URL and CORS");
        console.error("WebSocket error:", e);
      };
      
    } catch (e) {
      console.error("Connect error:", e);
      pushCard(elTrans, `[WS] ✗ Failed to connect: ${e.message}`);
    }
  });
})();