"""
core/ai_processor.py — ScribeOS AI Processor
=============================================
Handles all communication with the Google Gemini 1.5 Flash API.

Uses the current `google-genai` SDK (google.genai), NOT the deprecated
`google-generativeai` package.

Responsibilities
----------------
* Receive WAV audio chunks from the audio engine and request transcription.
* Maintain a sliding conversation context so each new chunk is informed by
  the preceding transcript — essential for speaker continuity and accuracy.
* Accumulate the full session transcript so a "Minutes of Meeting" document
  can be generated on demand when recording stops.
* Thread-safe: all shared state is protected by a lock so multiple chunk
  transcriptions can be in-flight concurrently without data corruption.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from datetime import date
from typing import Callable, List, Optional

from google import genai
from google.genai import types as genai_types

from core.logger import get_logger

log = get_logger(__name__)

# _CONTEXT_WINDOW / _CONTEXT_PREFIX removed: the entire recording is now sent
# as a single WAV so Gemini has full context without any rolling window.

# ── Transcription & Labelling prompt ──────────────────────────────────────
# Sent with audio. Transcribes and identifies speakers based on context.
_ACOUSTIC_PROMPT_TEMPLATE = """\
You are an expert transcriptionist and transcript editor. Your job is to transcribe the audio accurately AND identify the real participants based on context.

LANGUAGE RULES
- Detect the language(s) spoken automatically. Transcribe every utterance in the ORIGINAL language it was spoken in.
- Immediately after each foreign-language segment add an English translation in parentheses, e.g.: "Haan, theek hai (Yes, that's fine)".
- If the entire conversation is in English, skip translations.

SPEAKER LABELLING — CRITICAL
1. Identify the ACTUAL PARTICIPANTS by reading conversational context:
   - Direct address: if a speaker says "Good work, Saurabh" to another speaker, then that other speaker IS Saurabh.
   - Self-introduction: "Hi, I'm Priya" → that voice IS Priya.
   - Address-reply chains: if someone calls out "Abhay, your thoughts?", the very next turn is almost certainly Abhay.
2. If a speaker's identity cannot be logically deduced from the conversation, label them with a generic sequential label: Speaker A, Speaker B, Speaker C, … in the order each voice first appears. Do not guess names without context.
3. Distinguish PARTICIPANTS from THIRD PARTIES. If someone is merely TALKED ABOUT (e.g. "Naveen did a great job today"), do NOT assign that name to any speaker label.
4. If only one voice is audible, omit the speaker label entirely.

SPELLING GLOSSARY (for spelling correction ONLY)
{names_glossary}

FORMATTING RULES
- One line per speaker turn: "**Speaker Name/Label:** utterance"
- Omit filler words (um, uh, like, you know) unless they carry meaning.
- Do NOT add titles, headers, commentary, or a summary — only the raw transcript.
- Preserve technical terms, product names, and proper nouns exactly.
"""

_MOM_PROMPT = """\
You are a professional multilingual meeting secretary with expertise in
action-item extraction and speaker attribution.

Based on the COMPLETE TRANSCRIPT below, produce well-structured
**Minutes of Meeting** in Markdown. Follow every rule exactly.

════════════════════════════════════════════════════════
# Minutes of Meeting
**Date:** {date}

## Attendees
List every person identified by name in the transcript.  
If no names were mentioned write: _Not specified_.

## Language(s) Spoken
List every language detected (e.g. English, Hindi, Spanish).
If translations were provided, note it.

## Summary
2–3 sentence executive summary of the meeting, language-agnostic.

## Key Discussion Points
Bullet list of the main topics. Where relevant, note which speaker raised
or championed each point.

## Decisions Made
Bullet list of explicit decisions reached, with the decision-maker if known.  
_Omit this section entirely if no decisions were made._

## Action Items  ← CRITICAL SECTION — be exhaustive
Use this exact table format:

| Owner | Task | Due Date |
|-------|------|----------|
| Name / [Speaker X] | Clear description of what they must do | Date if mentioned, else — |

- Create one row per distinct task.
- If a person has multiple tasks, create multiple rows.
- If the owner is unknown write "Unassigned".
- If NO action items exist write: _No action items identified._

## Per-Person Summary
For every identified speaker (named or labelled), write a short sub-section:
### [Name / Speaker label]
- **Contributions:** what they said / proposed
- **Responsibilities:** tasks or commitments they accepted
- **Follow-ups:** anything they promised to check, send, or investigate

_Omit speakers who said nothing substantive._

## Next Steps
Ordered list of what needs to happen after this meeting (chronological if
dates were mentioned).  
_Omit if nothing was mentioned._
════════════════════════════════════════════════════════

**Full Transcript:**
{transcript}
"""


class AIProcessor:
    """Orchestrates Gemini calls for live transcription and MOM generation."""

    def __init__(self, api_key: str) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("Gemini API key must not be empty.")

        self._client = genai.Client(api_key=api_key.strip())
        self._acoustic_model = "gemini-2.5-flash"

        # Shared mutable state — always access under _lock
        self._lock            : threading.Lock = threading.Lock()
        self._full_transcript : str            = ""
        # Known participant names (populated from UI settings if available)
        self.known_names      : List[str]      = []

    # ── Public API ────────────────────────────────────────────────────────────

    def transcribe_chunk(
        self,
        wav_bytes: bytes,
        on_result: Callable[[str], None],
    ) -> None:
        """
        Single-step transcription pipeline.

        Upload the audio and ask Gemini to produce a clean transcript,
        automatically resolving speaker identities from conversational context.

        Parameters
        ----------
        wav_bytes:  WAV-formatted audio data (16 kHz / mono / 16-bit).
        on_result:  Callback invoked with the final transcript string.
                    Called on the same thread that called transcribe_chunk.
        """
        tmp_path: Optional[str] = None
        audio_file = None
        try:
            # ── Upload audio ─────────────────────────────────────────────────
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, prefix="scribeos_"
            ) as tmp:
                tmp.write(wav_bytes)
                tmp_path = tmp.name

            audio_file = self._client.files.upload(
                file=tmp_path,
                config=genai_types.UploadFileConfig(mime_type="audio/wav"),
            )
            _wait_for_file_active(self._client, audio_file)

            # ── Transcription & Labelling (audio → resolved transcript) ────────
            with self._lock:
                names = list(self.known_names)
            if names:
                glossary = ", ".join(names)
                names_glossary = f"Known names for spelling only: {glossary}"
            else:
                names_glossary = "(No spelling glossary provided)"

            acoustic_prompt = _ACOUSTIC_PROMPT_TEMPLATE.format(
                names_glossary=names_glossary
            )
            acoustic_response = self._client.models.generate_content(
                model=self._acoustic_model,
                contents=[acoustic_prompt, audio_file],
            )
            final_transcript = (acoustic_response.text or "").strip()
            log.debug("Transcript:\n%s", final_transcript)

            if not final_transcript:
                on_result("[No speech detected]")
                return

            with self._lock:
                self._full_transcript += ("\n" if self._full_transcript else "") + final_transcript

            on_result(final_transcript)

        except Exception as exc:  # noqa: BLE001
            err_msg = f"[Transcription error: {exc}]"
            log.error(err_msg)
            on_result(err_msg)

        finally:
            # Best-effort cleanup of the remote file and local temp file
            if audio_file:
                try:
                    self._client.files.delete(name=audio_file.name)
                except Exception:  # noqa: BLE001
                    pass
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def generate_mom(self) -> str:
        """
        Generate a Markdown "Minutes of Meeting" from the accumulated transcript.

        Returns the MOM as a Markdown string, or an error message.
        """
        with self._lock:
            transcript = self._full_transcript.strip()

        if not transcript:
            return "_No transcript available. Start a recording first._"

        prompt = _MOM_PROMPT.format(
            date=date.today().strftime("%B %d, %Y"),
            transcript=transcript,
        )
        try:
            response = self._client.models.generate_content(
                model=self._acoustic_model,
                contents=[prompt],
            )
            return (response.text or "").strip()
        except Exception as exc:  # noqa: BLE001
            msg = f"Error generating minutes: {exc}"
            log.error(msg)
            return msg

    def reset(self) -> None:
        """Clear all accumulated transcription state for a new session."""
        with self._lock:
            self._full_transcript = ""
        log.info("AIProcessor state reset")

    @property
    def full_transcript(self) -> str:
        """Thread-safe read of the complete accumulated transcript."""
        with self._lock:
            return self._full_transcript


# ── Internal helpers ───────────────────────────────────────────────────────────

def _wait_for_file_active(client: genai.Client, f, timeout: float = 30.0) -> None:
    """
    Poll Gemini's Files API until the uploaded file transitions from
    PROCESSING → ACTIVE, or raise TimeoutError if it takes too long.
    """
    deadline = time.monotonic() + timeout
    while True:
        state_name = f.state.name if hasattr(f.state, "name") else str(f.state)
        if state_name == "ACTIVE":
            return
        if state_name not in ("PROCESSING", "STATE_UNSPECIFIED"):
            raise RuntimeError(f"Gemini file in unexpected state: {state_name}")
        if time.monotonic() > deadline:
            raise TimeoutError("Gemini file processing timed out")
        time.sleep(0.5)
        f = client.files.get(name=f.name)
