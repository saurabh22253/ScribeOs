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

# ── Step 1 prompt: Blind Acoustic Agent ──────────────────────────────────────
# Sent with audio. Strictly forbids name-to-voice guessing.
# Names list is injected at call time as a spelling glossary only.
_ACOUSTIC_PROMPT_TEMPLATE = """\
You are an expert transcriptionist. Your ONLY job is to transcribe the audio accurately.

LANGUAGE RULES
- Detect the language(s) spoken automatically. Transcribe every utterance in
  the ORIGINAL language it was spoken in.
- Immediately after each foreign-language segment add an English translation
  in parentheses, e.g.: "Haan, theek hai (Yes, that's fine)".
- If the entire conversation is in English, skip translations.

SPEAKER LABELLING — CRITICAL
- Label every distinct voice with a generic sequential label: Speaker A,
  Speaker B, Speaker C, … in the order each voice first appears.
- NEVER guess, infer, or assign a real person's name to any voice label.
  You are acoustically blind to identity.
- If only one voice is audible, omit the speaker label entirely.

SPELLING GLOSSARY (for spelling correction ONLY — do NOT use as participant names)
{names_glossary}

FORMATTING RULES
- One line per speaker turn: "**Speaker X:** utterance"
- Omit filler words (um, uh, like, you know) unless they carry meaning.
- Do NOT add titles, headers, commentary, or a summary — only the raw transcript.
- Preserve technical terms, product names, and proper nouns exactly.
"""

# ── Step 2 prompt: Detective Logic Agent ─────────────────────────────────────
# Sent with TEXT only (no audio). Infers real names from conversational context.
_DETECTIVE_PROMPT_TEMPLATE = """\
You are a transcript editor. Analyze the raw transcript below and apply the
following logic to resolve speaker identities.

TASKS
1. Identify the ACTUAL PARTICIPANTS by reading conversational context:
   - Direct address: if Speaker B says "Good work, Saurabh" to Speaker A,
     then Speaker A IS Saurabh.
   - Self-introduction: "Hi, I'm Priya" → that voice IS Priya.
   - Address-reply chains: if Speaker A calls out "Abhay, your thoughts?",
     the very next turn (Speaker B) is almost certainly Abhay.
   - Extend chains transitively until no more names can be resolved.

2. Distinguish PARTICIPANTS from THIRD PARTIES:
   - Only map a name to a speaker label if that name is provably a voice
     in the recording.
   - If someone is merely TALKED ABOUT (e.g. "Naveen did a great job today"),
     do NOT assign that name to any speaker label.

3. Apply the resolved names:
   - Replace every occurrence of the generic label (Speaker A, Speaker B, …)
     with the inferred real name.
   - If a speaker's identity cannot be logically deduced, leave them as
     "Speaker [Letter]" exactly — do not guess.

4. Return ONLY the updated transcript — no commentary, no explanation,
   no header, no summary. Same formatting as the input.

RAW TRANSCRIPT:
{raw_transcript}
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
        # Step 1 uses a full multimodal model (audio + text)
        self._acoustic_model = "gemini-2.5-flash"
        # Step 2 is text-only — 1.5 Flash is fast and cheap for plain-text reasoning
        self._detective_model = "gemini-2.5-flash"

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
        on_step: Optional[Callable[[int], None]] = None,
    ) -> None:
        """
        Two-step transcription pipeline for superior speaker identification.

        Step 1 — Blind Acoustic Agent
            Upload the audio and ask Gemini to produce a clean transcript using
            only generic labels (Speaker A, Speaker B, …).  Real names are
            provided solely as a spelling glossary so it cannot hallucinate
            identity from acoustics.

        Step 2 — Detective Logic Agent
            Feed the anonymised text (no audio) to a second Gemini call.  The
            model reads conversational context (greetings, direct address,
            address-reply chains) to map each generic label to the correct real
            name — without confusing third-party mentions for participants.

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

            # ── Step 1: Blind Acoustic Agent (audio → generic labels) ────────
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
            raw_transcript = (acoustic_response.text or "").strip()
            log.debug("Step 1 raw transcript:\n%s", raw_transcript)

            if not raw_transcript:
                on_result("[No speech detected]")
                return

            # ── Step 2: Detective Logic Agent (text-only → resolve names) ────
            if on_step:
                on_step(2)
            detective_prompt = _DETECTIVE_PROMPT_TEMPLATE.format(
                raw_transcript=raw_transcript
            )
            detective_response = self._client.models.generate_content(
                model=self._detective_model,
                contents=[detective_prompt],
            )
            final_transcript = (detective_response.text or "").strip()
            log.debug("Step 2 resolved transcript:\n%s", final_transcript)

            # Fall back to raw if detective returns empty
            text = final_transcript or raw_transcript

            with self._lock:
                self._full_transcript += ("\n" if self._full_transcript else "") + text

            on_result(text)

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
