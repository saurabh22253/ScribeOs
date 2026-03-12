# ScribeOS — Setup Guide

> **ScribeOS** is a local macOS AI transcription app built with Swift + Python.  
> It captures your microphone and system audio in real-time, transcribes everything with **Gemini 2.5 Flash**, detects multiple languages and speakers automatically, and generates structured **Minutes of Meeting** — all without any virtual audio drivers.

---

## Requirements

| Dependency | Minimum version | Notes |
|---|---|---|
| macOS | 13.0 Ventura | ScreenCaptureKit requires macOS 13+ |
| Xcode Command Line Tools | any recent | for `swiftc` |
| Python | 3.11 or 3.12 | 3.13 not yet tested |
| pip | 23+ | bundled with Python |
| Google Gemini API key | — | free tier works; get one at [aistudio.google.com](https://aistudio.google.com) |

---

## 1 — Clone the repo

```bash
git clone https://github.com/saurabh22253/ScribeOs.git
cd ScribeOs
```

---

## 2 — Install Xcode Command Line Tools

If you haven't already:

```bash
xcode-select --install
```

Verify `swiftc` is available:

```bash
swiftc --version
```

---

## 3 — Compile the Swift audio bridge

ScribeOS uses a small Swift binary (`audio_bridge`) to capture audio via  
ScreenCaptureKit and AVFoundation. Compile it once:

```bash
swiftc audio_bridge.swift -o audio_bridge -framework ScreenCaptureKit
```

This produces a single `audio_bridge` binary in the project root.  
You need to recompile only if you edit `audio_bridge.swift`.

---

## 4 — Create a Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 5 — Install Python dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` installs:

| Package | Purpose |
|---|---|
| `flet>=0.21.0` | Cross-platform desktop UI framework |
| `google-genai>=1.0.0` | Official Google Gemini SDK (new `google.genai` namespace) |
| `keyring>=24.3.0` | Secure API key storage in macOS Keychain |
| `python-dotenv>=1.0.1` | Optional `.env` support |

---

## 6 — Get a Gemini API key

1. Visit [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **Create API key**
3. Copy the key — it starts with `AIza…`

You do **not** need a paid plan. The free tier is sufficient for normal meeting lengths.

---

## 7 — Grant macOS permissions (one-time)

The app needs two macOS privacy permissions:

### Screen Recording (for system audio)
`System Settings → Privacy & Security → Screen Recording`  
→ Enable your **Terminal** app (or whichever terminal emulator you use).

### Microphone
`System Settings → Privacy & Security → Microphone`  
→ Enable your **Terminal** app.

> Both permission dialogs appear automatically on first run — just click **Allow**.

---

## 8 — Run ScribeOS

```bash
source venv/bin/activate   # if not already active
python main.py
```

The app window opens. On first launch:

1. Paste your Gemini API key into the field in the top bar.
2. Click the **Save** (🔑) icon to store it in the macOS Keychain — you won't need to paste it again.
3. Click **Start Scribing** to begin recording.
4. Click **Stop Scribing** when done — the full recording is sent to Gemini and the transcript appears.
5. Click **Generate MOM** for structured Minutes of Meeting.
6. Use **Export .txt** / **Export MOM** to save files to your Desktop.

---

## Project structure

```
ScribeOs/
├── audio_bridge.swift      # Swift audio capture binary (source)
├── audio_bridge            # compiled binary — gitignored, build locally
├── main.py                 # Flet app entry point & UI controller
├── requirements.txt
├── core/
│   ├── audio_engine.py     # Manages the Swift subprocess + PCM buffering
│   ├── ai_processor.py     # Gemini transcription + MOM generation
│   └── logger.py           # Structured logging
├── ui/
│   ├── styles.py           # Design tokens (colours, sizes, typography)
│   └── components.py       # Reusable Flet control factories
└── utlis/
    ├── export_tools.py     # Save transcript / MOM to Desktop
    └── security.py         # macOS Keychain read/write via keyring
```

---

## How it works

```
Microphone ──┐
             ▼
        audio_bridge (Swift)
             │  16 kHz · mono · Int16 PCM streamed to stdout
             ▼
        AudioEngine (Python)
             │  buffers entire session in memory
             ▼ on Stop
        WAV file (in-memory)
             │
             ▼
        Gemini Files API  →  generate_content(model="gemini-2.5-flash")
             │
             ▼
        Transcript  →  Minutes of Meeting
System audio ──┘  (via ScreenCaptureKit, mixed with mic)
```

---

## Troubleshooting

### "audio_bridge binary not found"
Compile it: `swiftc audio_bridge.swift -o audio_bridge -framework ScreenCaptureKit`

### No system audio captured
Grant **Screen Recording** permission to your terminal in  
`System Settings → Privacy & Security → Screen Recording`  
then restart the app.

### No microphone audio
Grant **Microphone** permission to your terminal in  
`System Settings → Privacy & Security → Microphone`  
then restart the app.

### Gemini API errors
- Confirm your key is correct (`AIza…`).
- Ensure you have internet access — the transcription step sends audio to Google's servers.
- If you see a 404 model error, the SDK auto-selects `gemini-2.5-flash`; no action needed.

### `flet` import errors / `AttributeError`
Ensure you are running inside the virtual environment:
```bash
source venv/bin/activate
python main.py
```

---

## License

MIT — do what you want, just don't remove the attribution.
