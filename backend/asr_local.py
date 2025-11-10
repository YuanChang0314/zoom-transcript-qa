# -*- coding: utf-8 -*-
"""
Local non-blocking audio capture + Whisper transcription.
This is a PoC audio source so you can wire Zoom App <-> backend end-to-end.
For production, replace this module with a meeting audio source (Meeting SDK bot,
Recall.ai, or Zoom 3rd-party Closed Caption push) but keep the same interface.

Public API:
- class LocalASRSource: start(), stop(), get_chunk_text_if_ready()
"""

import queue
import threading
import warnings
import tempfile
from typing import Optional, List

import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SECONDS = 8.0
WHISPER_MODEL = "tiny.en"

INITIAL_PROMPT = (
    "This is a surgical morbidity and mortality (M&M) conference. "
    "Speakers are residents, attendings, and moderators discussing surgical cases. "
    "Common terms: EKG, troponin, lab, diabetes, GI, ICU, vasopressors, norepinephrine, "
    "intubation, extubation, wound infection, dehiscence, drain output."
)

class LocalASRSource:
    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS, chunk_seconds: float = CHUNK_SECONDS):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_seconds = chunk_seconds
        self.samples_per_chunk = int(self.sample_rate * self.chunk_seconds)
        self.audio_q: "queue.Queue[np.ndarray]" = queue.Queue()
        self.buffer: List[np.ndarray] = []
        self.samples_accum = 0
        self.stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        self._running = False
        warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")
        self.asr_model = whisper.load_model(WHISPER_MODEL)

    @staticmethod
    def _audio_callback(indata, frames, time_info, status):
        # This static method will be rebound with closure to put into the right queue.
        pass

    def _make_callback(self):
        q = self.audio_q
        def _cb(indata, frames, time_info, status):
            if status:
                # you could log status warnings if needed
                pass
            q.put(indata.copy())
        return _cb

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._make_callback()
            )
            self.stream.start()

    def stop(self):
        with self._lock:
            self._running = False
            if self.stream is not None:
                try:
                    self.stream.stop()
                except Exception:
                    pass
                try:
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None

    def _drain_queue_to_buffer(self):
        drained = False
        while True:
            try:
                block = self.audio_q.get_nowait()
                self.buffer.append(block)
                self.samples_accum += block.shape[0]
                drained = True
            except queue.Empty:
                break
        return drained

    def _transcribe(self, wav_path: str) -> str:
        result = self.asr_model.transcribe(
            wav_path,
            language="en",
            task="transcribe",
            initial_prompt=INITIAL_PROMPT,
            fp16=False
        )
        text = (result.get("text") or "").strip()
        return text

    def get_chunk_text_if_ready(self) -> Optional[str]:
        """
        Returns a transcript string if a full chunk is available; otherwise None.
        """
        self._drain_queue_to_buffer()
        if self.samples_accum < self.samples_per_chunk:
            return None

        # Concatenate buffer into single array
        if not self.buffer:
            return None
        audio_block = np.concatenate(self.buffer, axis=0)
        self.buffer.clear()
        self.samples_accum = 0

        # Write to temp wav
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio_block, self.sample_rate)
            wav_path = tmp.name

        # Transcribe
        text = self._transcribe(wav_path)
        return text
