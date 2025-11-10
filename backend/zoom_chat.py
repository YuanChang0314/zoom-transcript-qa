# -*- coding: utf-8 -*-
"""
Optional: Zoom Chat send message.
You need a valid user-scoped access token with the chat_message:write scope.
"""

import requests
from typing import Optional

def send_chat_message(access_token: str, to_jid: str, message: str) -> bool:
    """
    Send a Zoom Chat message to a JID (user or channel).
    Returns True if success, else False.
    """
    try:
        url = "https://api.zoom.us/v2/im/chat/messages"
        payload = {
            "message": message,
            "to_jid": to_jid
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        return 200 <= resp.status_code < 300
    except Exception:
        return False
