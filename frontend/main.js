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
    // Add capabilities as needed
    capabilities: [
      "authorize",
      "getMeetingContext",
      "getUserContext",
      "postMessage",
      "expandApp"
    ]
  }).then(() => {
    state.installed = true;
  }).catch((e) => {
    // If this page is opened outside Zoom client, SDK config will fail.
    // You can still test WebSocket locally; just ignore SDK in that case.
    console.warn("Zoom SDK config failed:", e && e.message ? e.message : e);
  });

  // Buttons
  document.getElementById("btn-auth").addEventListener("click", async () => {
    try {
      const res = await zoomSdk.authorize({ scopes: [] });
      logJSON(elAuth, { code: res.code });
      // Exchange code for access token
      const fd = new FormData();
      fd.append("code", res.code);
      const r = await fetch(OAUTH_CALLBACK, { method: "POST", body: fd });
      const token = await r.json();
      state.accessToken = token.access_token || null;
      logJSON(elAuth, token);
    } catch (e) {
      logJSON(elAuth, { error: e && e.message ? e.message : String(e) });
    }
  });

  document.getElementById("btn-context").addEventListener("click", async () => {
    try {
      const ctx = await zoomSdk.getMeetingContext();
      state.meetingId = ctx && (ctx.meetingUUID || ctx.meetingNumber || ctx.sessionUUID) || "local-dev";
      logJSON(elCtx, ctx);
    } catch (e) {
      // If outside Zoom, you can still set a fake meetingId for local dev
      state.meetingId = "local-dev";
      logJSON(elCtx, { outsideZoom: true, meetingId: state.meetingId, error: e && e.message ? e.message : String(e) });
    }
  });

  document.getElementById("btn-connect").addEventListener("click", async () => {
    const mid = state.meetingId || "local-dev";
    const ws = new WebSocket(`${WS_URL}?meeting_id=${encodeURIComponent(mid)}`);
    state.ws = ws;

    ws.onopen = () => {
      pushCard(elTrans, "[ws] connected");
    };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "heartbeat") return;
        if (data.type === "transcript") {
          pushCard(elTrans, data.text);
        } else if (data.type === "qna") {
          pushCard(elQnA, JSON.stringify(data.data, null, 2));
        } else {
          pushCard(elTrans, ev.data);
        }
      } catch (err) {
        pushCard(elTrans, ev.data);
      }
    };
    ws.onclose = () => {
      pushCard(elTrans, "[ws] closed");
    };
    ws.onerror = (e) => {
      pushCard(elTrans, "[ws] error");
    };
  });
})();
