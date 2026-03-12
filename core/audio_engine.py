"""
core/audio_engine.py — ScribeOS Python Audio Engine
=====================================================
Manages the lifecycle of the compiled Swift audio bridge (audio_bridge).

Responsibilities
----------------
* Launch the Swift binary as a subprocess and communicate via pipes.
* Read raw 16 kHz / mono / Int16 PCM bytes from the binary's stdout and
  accumulate the ENTIRE session into a single in-memory buffer.
* On stop(), wrap the full buffer in a WAV header and return it so the AI
  processor can transcribe the whole recording in one API call — preserving
  complete speaker and language context from start to finish.
* Forward real-time control commands (MIC_OFF / MIC_ON / QUIT) to the binary's
  stdin so the Python UI can toggle the mic without restarting the process.
"""

from __future__ import annotations

import io
import subprocess
import threading
import wave
from pathlib import Path
from typing import Optional

from core.logger import get_logger

log = get_logger(__name__)

# ── Audio format constants (must match the Swift binary's output) ──────────────
SAMPLE_RATE   : int = 16_000   # Hz
CHANNELS      : int = 1        # mono
SAMPLE_WIDTH  : int = 2        # bytes (16-bit PCM)


class AudioEngine:
    """Bridges the Swift audio capture binary with the Python AI pipeline."""

    def __init__(self, binary_path: str) -> None:
        """
        Parameters
        ----------
        binary_path:  Absolute path to the compiled `audio_bridge` binary.
        """
        self.binary_path = binary_path

        self._process    : Optional[subprocess.Popen] = None
        self._running    : bool                       = False
        self._mic_muted  : bool                       = False

        # Full-session raw PCM accumulation buffer
        self._raw_buffer  : bytes          = b""
        self._buffer_lock : threading.Lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, mic_muted: bool = False) -> None:
        """Launch the Swift binary and begin buffering audio."""
        if not Path(self.binary_path).exists():
            raise FileNotFoundError(
                f"Audio bridge binary not found at '{self.binary_path}'.\n"
                "Compile it first:\n"
                "  swiftc audio_bridge.swift -o audio_bridge -framework ScreenCaptureKit"
            )

        self._mic_muted  = mic_muted
        self._raw_buffer = b""  # reset for new session
        args = [self.binary_path]
        if mic_muted:
            args.append("--mic-off")

        self._process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # unbuffered — critical for low-latency PCM streaming
        )
        self._running = True

        threading.Thread(target=self._read_stdout, daemon=True, name="ae-reader").start()
        threading.Thread(target=self._log_stderr,  daemon=True, name="ae-stderr").start()

        log.info("AudioEngine started (binary: %s, mic_muted=%s)", self.binary_path, mic_muted)

    def stop(self) -> Optional[bytes]:
        """
        Gracefully stop recording.

        Returns
        -------
        WAV bytes for the ENTIRE session, or None if nothing was recorded.
        """
        self._running = False
        self._send_command("QUIT")

        if self._process:
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.terminate()
            self._process = None

        with self._buffer_lock:
            full_pcm         = self._raw_buffer
            self._raw_buffer = b""

        duration_sec = len(full_pcm) / (SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)
        log.info(
            "AudioEngine stopped. Captured %.1f seconds (%d bytes raw PCM)",
            duration_sec, len(full_pcm),
        )
        return _wrap_wav(full_pcm) if full_pcm else None

    def set_mic_muted(self, muted: bool) -> None:
        """Dynamically mute or unmute the microphone without restarting."""
        self._mic_muted = muted
        self._send_command("MIC_OFF" if muted else "MIC_ON")
        log.info("Mic %s", "muted" if muted else "unmuted")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def buffered_seconds(self) -> float:
        """Approximate recording duration accumulated so far."""
        with self._buffer_lock:
            return len(self._raw_buffer) / (SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _send_command(self, cmd: str) -> None:
        """Write a newline-terminated command to the Swift binary's stdin."""
        if self._process and self._process.stdin:
            try:
                self._process.stdin.write(f"{cmd}\n".encode())
                self._process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def _read_stdout(self) -> None:
        """Background thread: reads raw PCM bytes from the Swift binary's stdout."""
        chunk = 4096
        while self._running and self._process:
            try:
                data = self._process.stdout.read(chunk)
                if not data:
                    break
                with self._buffer_lock:
                    self._raw_buffer += data
            except OSError:
                break
        log.debug("stdout reader thread exiting")

    def _log_stderr(self) -> None:
        """Background thread: forwards the Swift binary's stderr to the Python logger."""
        for raw_line in self._process.stderr:
            line = raw_line.decode(errors="replace").rstrip()
            if line:
                log.info("bridge: %s", line)
        log.debug("stderr logger thread exiting")


# ── Module-level utility ──────────────────────────────────────────────────────

def _wrap_wav(raw_pcm: bytes) -> bytes:
    """Wrap raw PCM bytes in a standard WAV container understood by Gemini."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(raw_pcm)
    return buf.getvalue()
