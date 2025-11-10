# -*- coding: utf-8 -*-
"""
LLM Q&A module.
- analyze_transcript_chunk(text) takes transcript text and returns structured JSON.
- Uses OpenAI Chat Completions with a conservative, safety-aware instruction.
"""

import os
import json
import datetime
from typing import Dict, Any, List
from openai import OpenAI

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.0"))

client = OpenAI()

SAFETY_NOTE = (
    "Important: The following content is for educational discussion only "
    "and is not medical advice. For clinical decisions, seek licensed supervision."
)

SYSTEM_INSTRUCTION = (
    "You assist in a Surgical Morbidity & Mortality (M&M) conference. "
    "Given a transcript chunk, extract potential audience questions and provide concise answers "
    "only if answerable with general medical knowledge. "
    "If not confidently answerable, mark it unanswerable. "
    "Return STRICT JSON with structure:\n"
    "{\n"
    '  "timestamp": "<UTC ISO8601>",\n'
    '  "questions": [\n'
    '     {"original": "<string>", "refined": "<string>", "answerable": true/false, "answer": "<string or null>"}\n'
    "  ],\n"
    '  "note": "<string safety note>"\n'
    "}\n"
    "No extra commentary, no markdown."
)

def analyze_transcript_chunk(text: str) -> Dict[str, Any]:
    """
    Return a dict of the form:
    {
      "timestamp": "...",
      "questions": [{"original": "...", "refined": "...", "answerable": bool, "answer": "... or None"}],
      "note": SAFETY_NOTE
    }
    """
    if not text or not text.strip():
        return {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "questions": [],
            "note": SAFETY_NOTE
        }

    user_prompt = (
        f"Transcript:\n{text}\n\n"
        f"{SAFETY_NOTE}\n"
        "Return strict JSON only."
    )

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_prompt}
        ]
    )
    content = resp.choices[0].message.content.strip()

    # Try parsing JSON; if failed, wrap in fallback envelope
    try:
        data = json.loads(content)
        # Ensure required fields exist
        data["timestamp"] = datetime.datetime.utcnow().isoformat() + "Z"
        data["note"] = SAFETY_NOTE
        if "questions" not in data or not isinstance(data["questions"], list):
            data["questions"] = []
        return data
    except Exception:
        return {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "questions": [],
            "note": SAFETY_NOTE,
            "raw": content,
            "parse_error": True
        }
