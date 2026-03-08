# EarWitness

Local web app for transcribing and diarizing audio and video recordings with speaker labels. Upload a voice memo, meeting recording, or Zoom video — review and edit the transcript, rename speakers, then export a clean Markdown file or audio clip.

Two transcription engines are available:
- **AssemblyAI** (cloud) — best diarization quality, requires API key, ~$0.15/hour
- **Local** (offline) — free, uses mlx-whisper + pyannote.audio, runs entirely on your Mac

## Features

- **Multi-format support** — audio (.m4a, .mp3, .wav, .flac, .ogg, .aac, .wma) and video (.mp4, .mov, .webm, .mkv)
- **Speaker diarization** — automatically identifies and labels speakers
- **Inline editing** — click any text to fix words; rename speakers; reassign speaker labels per segment
- **Split and merge** — click between words to split a segment; merge adjacent same-speaker segments
- **Find and replace** — search across the full transcript with match highlighting and replace support
- **Audio playback** — synced audio player with click-to-seek on any utterance
- **Markdown export** — structured .md file with date, attendees, duration, and timestamped transcript
- **Audio clip export** — select utterances and export them as a single .m4a audio clip
- **Project management** — auto-saves projects with full transcript, audio, and speaker names; reopen anytime from the home screen
- **Rename projects** — click the project name in the header or use the rename button on project cards
- **Settings panel** — configure default export folder, transcription engine, API keys, and model selection
- **Cancel local transcription** — stop an in-progress local transcription and return to the home screen

## Prerequisites

- macOS on Apple Silicon (M1/M2/M3/M4/M5)
- Python 3.11+
- ffmpeg (`brew install ffmpeg`)
- An AssemblyAI account ([sign up here](https://www.assemblyai.com/dashboard/signup)) — for cloud engine
- A HuggingFace account ([sign up here](https://huggingface.co/join)) — for local engine

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure API keys (choose one or both):

   **Option A — Settings panel (recommended):** Launch the app and click the gear icon to enter your AssemblyAI API key directly. No file editing needed.

   **Option B — .env file:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your keys:
   - `ASSEMBLYAI_API_KEY` — from your [AssemblyAI dashboard](https://www.assemblyai.com/dashboard)
   - `HF_TOKEN` — from [HuggingFace settings](https://huggingface.co/settings/tokens) (needed for local engine only)

4. **For local engine only:** Accept the pyannote model license at [huggingface.co/pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) (click "Agree and access repository" while logged in).

## Usage

Start the app:

```bash
python run.py
```

Open http://localhost:8000 in your browser.

### Workflow

1. **Select engine** — Choose "Local" or "AssemblyAI" before uploading
2. **Upload** — Drag and drop (or browse for) an audio or video file
3. **Wait** — Cloud: ~1–3 min. Local: slower, first run also downloads ~3GB of models
4. **Review** — Edit the transcript:
   - Click any text to fix mis-transcribed words
   - Rename speakers in the speaker panel at the top
   - Change a segment's speaker using the dropdown on each block
   - Click between words to split a segment; merge adjacent same-speaker segments
   - Use Find (magnifying glass icon) to search and replace across the transcript
5. **Export** — Click "Export Transcript" to save a .md file, or select utterances and export an audio clip

Exported files are saved to `~/Documents/Transcripts/` by default (configurable in Settings).

### Settings

Click the gear icon (always visible in the header) to configure:

| Setting | Description |
|---------|-------------|
| Default export folder | Where transcript and clip files are saved |
| Default engine | Which transcription engine is pre-selected on launch |
| AssemblyAI API key | Your API key (alternative to .env file) |
| AssemblyAI model | Universal-3 Pro (default, best quality) or Universal-2 (cheaper) |
| Local Whisper model | Large V3 Turbo (default, fastest), Large V3 (best), or Small (lightweight) |

### Export format

Transcripts are exported as Markdown files with the following structure:

```
**Date:** 2026-02-17
**Attendees:** Trey, Joe
**Duration:** 15 min

---

## Transcript

[0:00] Trey: So let's talk about the marketing plan...

[2:14] Joe: Sure, I was thinking...
```

The date is extracted from the project name if it contains a `YYYY-MM-DD` pattern; otherwise it defaults to the export date.

## Project structure

```
TranscriptionTool/
├── run.py                  # Entry point — starts uvicorn server
├── settings.json           # User settings (auto-generated)
├── requirements.txt        # Python dependencies
├── .env.example            # Template for API keys
├── backend/
│   ├── main.py             # FastAPI routes and endpoints
│   ├── transcribe.py       # AssemblyAI cloud transcription
│   ├── transcribe_local.py # Local mlx-whisper + pyannote transcription
│   ├── export.py           # Transcript formatting and file export
│   ├── projects.py         # Project CRUD and storage
│   └── settings.py         # Settings persistence and validation
└── frontend/
    └── index.html          # Single-page app (HTML + CSS + JS)
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Unsupported file format | Supported: .m4a, .mp3, .wav, .flac, .ogg, .aac, .wma, .mp4, .mov, .webm, .mkv |
| AssemblyAI API error | Check your API key in Settings or `.env` |
| pyannote access denied | Accept the license at the HuggingFace link above, check `HF_TOKEN` |
| Port 8000 already in use | Stop the other process, or change the port in `run.py` |
| Local engine is slow | First run downloads models (~3GB). Subsequent runs are faster |
| ffmpeg not found | Install with `brew install ffmpeg` |
