# Project Specification: EarWitness
**Version:** 2.0
**Date:** 2026-03-07
**Status:** Current Production Build

---

## 1. Overview

EarWitness is a locally-run web application for transcribing and diarizing audio and video recordings. It identifies distinct speakers, presents an editable transcript in the browser, and exports clean Markdown files or audio clips. It runs entirely on localhost with no cloud deployment — just double-click to launch.

Two transcription engines are available:
- **Local** (offline, free) — mlx-whisper for transcription + pyannote.audio for speaker diarization, accelerated on Apple Silicon via Metal
- **AssemblyAI** (cloud, paid) — REST API integration, best diarization quality, ~$0.15/hour of audio

---

## 2. Target Environment

| Attribute | Value |
|-----------|-------|
| **Machine** | Mac with Apple Silicon (M1/M2/M3/M4/M5) |
| **OS** | macOS (Sequoia or later recommended) |
| **Runtime** | Local only — runs on `localhost:8000` |
| **Browser** | Safari or Chrome on macOS |
| **Privacy** | External API calls used for cloud engine only; local engine is fully offline |

---

## 3. Supported Input Formats

| Type | Formats |
|------|---------|
| **Audio** | `.m4a`, `.mp3`, `.wav`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Video** | `.mp4`, `.mov`, `.webm`, `.mkv` (audio track extracted automatically) |

Video support enables direct upload of Zoom recordings and other meeting captures without a separate audio extraction step. FFmpeg handles all format conversion internally.

---

## 4. Technical Architecture

### 4.1 Backend: Python + FastAPI

- **Language:** Python 3.11+
- **Framework:** FastAPI with uvicorn ASGI server
- **Key dependencies:**
  - `fastapi`, `uvicorn`, `python-multipart` — web framework and file uploads
  - `python-dotenv` — environment variable management
  - `httpx` — HTTP client for AssemblyAI REST API (used instead of the SDK for Python 3.14 compatibility)
  - `mlx-whisper` — local transcription with word-level timestamps (Apple Silicon optimized)
  - `pyannote.audio` — local speaker diarization (community model)
  - `ffmpeg` — system binary for audio conversion, clip extraction, and video audio extraction

### 4.2 Frontend: Single-Page App

- A single `index.html` file served by FastAPI — no React, no build step, no npm
- All CSS and JavaScript inline in the HTML file
- Vanilla JS with no external dependencies

### 4.3 Storage

- **Projects:** `~/Documents/Transcripts/Projects/{project-id}/` — each project folder contains `project.json` (metadata, utterances, speaker names) and the original audio/video file
- **Exports:** `~/Documents/Transcripts/` by default (configurable in settings)
- **Settings:** `TranscriptionTool/settings.json` in the app directory
- **Session:** `sessionStorage` used to restore the active project on browser refresh

### 4.4 Backend Modules

| Module | Responsibility |
|--------|---------------|
| `main.py` | FastAPI routes, SSE streaming, file upload handling |
| `transcribe.py` | AssemblyAI REST API integration (upload, poll, parse) |
| `transcribe_local.py` | mlx-whisper transcription + pyannote diarization pipeline |
| `export.py` | Markdown transcript formatting, file export, audio clip extraction via ffmpeg |
| `projects.py` | Project CRUD: create, read, update, rename, delete, list |
| `settings.py` | Settings persistence and validation (JSON file) |

---

## 5. Application Flow

```
[User] → Double-clicks EarWitness.command to launch
    ↓
[App] → Starts server, opens browser to http://localhost:8000
    ↓
[User] → Selects transcription engine (Local or AssemblyAI)
    ↓
[User] → Drags and drops (or browses for) an audio or video file
    ↓
[Backend] → Saves file to temp directory
    ↓
[Backend] → Transcribes with selected engine:
            • Local: mlx-whisper → WAV conversion → pyannote diarization → merge
            • Cloud: Upload to AssemblyAI → poll for completion → parse response
    ↓
[Frontend] → Displays transcript in editable review UI
    ↓
[User] → Edits transcript:
         • Fix words, rename speakers, reassign segments
         • Split/merge utterances, shuttle words between blocks
         • Search and replace across transcript
    ↓
[Backend] → Auto-saves as project (audio + transcript + speaker names)
    ↓
[User] → Exports transcript as .md file and/or audio clips as .m4a
    ↓
[User] → Closes Terminal window to stop the server
```

---

## 6. Feature Specification

### 6.1 File Upload

- **Drop zone** with dashed border and hover state, plus a "Browse Files" button
- **Engine selector:** Radio buttons for Local (offline, free) and AssemblyAI (cloud, best quality)
- **Validation:** Checks file extension against supported formats; clear error message if unsupported
- **Progress screen:**
  - Real-time status messages via SSE (local engine)
  - Animated indeterminate progress bar
  - File name and size display
  - Engine-specific hint text (e.g., "First run downloads ~3GB of models")
  - **Cancel button** (local engine only) — stops transcription between major steps, cleans up temp files, returns to home screen

### 6.2 Transcript Editor

The editor displays the transcript as a vertical list of **utterance blocks**. Each block contains:

```
[✓] [▶] [Speaker Dropdown ▾]                    [0:00 – 0:45] [Split]
Speaker-color-coded text content (click to edit)
                                          [↑ shuttle] [Merge] [↓ shuttle]
```

#### Text Editing
- Click any utterance text to enter edit mode (contentEditable)
- Word-level display in view mode (individual `<span>` elements for search highlighting)
- Edited words get proportionally estimated timestamps

#### Speaker Management
- **Rename bar** (collapsible) at the top of the editor with all speakers listed
- Each speaker has a color dot, raw label, and editable name field
- Renaming a speaker updates all occurrences globally and all dropdown labels
- **Speaker dropdown** on each utterance allows reassigning that block to any speaker or creating a new speaker
- **Color coding:** 10-color palette applied as left border on utterance blocks
- Orphaned speakers (no remaining utterances) are automatically removed

#### Utterance Operations

| Action | Behavior |
|--------|----------|
| **Split** | Divides an utterance at its midpoint into two blocks; both keep the original speaker; disabled if < 2 words |
| **Merge** | Combines two adjacent same-speaker utterances into one; button only appears when applicable |
| **Word shuttle (↑)** | Moves the first word of an utterance up to the end of the preceding utterance |
| **Word shuttle (↓)** | Moves the last word of an utterance down to the start of the following utterance |

#### Search & Replace
- **Activation:** Magnifying glass icon in header, or `⌘F` / `Ctrl+F`
- Case-insensitive multi-word phrase matching
- Punctuation-tolerant (matches words ignoring leading/trailing punctuation)
- Real-time results with 200ms debounce; match count display ("X of Y")
- Navigate matches with ▲/▼ buttons, Enter/Shift+Enter keys
- **Replace mode** (`⌘H` / `Ctrl+H`): Replace current match or Replace All
- **Highlights:** Yellow for matches, orange for current match
- Escape key closes search bar

### 6.3 Audio Player

Fixed bottom bar, visible whenever the editor is open:

| Control | Behavior |
|---------|----------|
| ⏮ Previous | Jump to previous utterance |
| ▶ / ⏸ Play/Pause | Toggle playback (keyboard: Space) |
| ⏭ Next | Jump to next utterance |
| Seek slider | Drag to scrub; Arrow keys ±5 seconds |
| Speed selector | 0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x |
| Time display | Current position / total duration |

- **Click-to-seek:** Click any utterance's timestamp to jump playback to that point
- **Playing highlight:** Currently-playing utterance gets a blue background with auto-scroll
- **Keyboard:** Shift+Arrow Left/Right for segment navigation

### 6.4 Project Management

Projects are auto-created after each transcription and listed on the home screen.

| Operation | Details |
|-----------|---------|
| **Auto-create** | After transcription completes, saves project with audio file, transcript, and speaker names |
| **Open** | Click a project card on the home screen to reopen it with full audio playback |
| **Save** | Explicit save button in header; saves utterances, speakers, and speaker names to project.json |
| **Rename** | Click project name in the header for inline editing, or use "Rename" button on project cards |
| **Delete** | "Delete" button on project cards with confirmation prompt; removes entire project folder |
| **Session restore** | Active project ID stored in sessionStorage; auto-reopens on browser refresh |

**Project card display:** Each card in the "Recent Projects" list shows:
- Project name (with rename button)
- Duration and speaker count
- Speaker names (excluding single-letter raw labels) sorted by duration spoken
- Example: `14:38 · 2 speakers (Trey, Abhishek)`

### 6.5 Transcript Export

**Format:** Markdown (`.md`)

```
**Date:** 2026-02-17
**Attendees:** Trey, Abhishek
**Duration:** 15 min

---


## Transcript

[0:00] Trey: So let's talk about the comp plan...

[2:14] Abhishek: Sure, I was thinking...
```

- **Date** extracted from the filename if it contains a `YYYY-MM-DD` pattern; otherwise defaults to the export date
- **Attendees** listed in order of first appearance
- **Duration** rounded to the nearest minute
- **Timestamps** in `M:SS` or `H:MM:SS` format
- **Export dialog** with editable filename, output folder (with native macOS Browse picker), and confirmation showing the saved file path

### 6.6 Audio Clip Export

- Select utterances via checkboxes on each block; badge counter on the clip export button
- Export dialog shows a summary of selected segments with durations
- Supports single or multiple non-contiguous segments
- **Output:** `.m4a` file (AAC codec, 128k bitrate) via ffmpeg
- Multiple segments are concatenated using ffmpeg's `atrim + concat` filter

### 6.7 Settings

Accessed via the gear icon (always visible in the header). Persisted in `settings.json`.

| Setting | Options | Default |
|---------|---------|---------|
| Default export folder | Any folder path (with Browse picker) | `~/Documents/Transcripts` |
| Default transcription engine | Local / AssemblyAI | Local |
| AssemblyAI API key | Password field (alternative to .env file) | Empty |
| AssemblyAI model | Universal-3 Pro / Universal-2 | Universal-3 Pro |
| Local Whisper model | Large V3 Turbo / Large V3 / Small | Large V3 Turbo |

Settings are read at runtime by backend modules with fallback chains: settings.json → `.env` → hardcoded defaults.

---

## 7. API Endpoints

### Transcription
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/transcribe` | Upload file and transcribe (multipart form: file + engine) |
| `POST` | `/api/transcribe/cancel` | Cancel an in-progress local transcription |

### Audio
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/audio` | Serve the current audio file for browser playback |

### Export
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/export` | Export transcript to .md file |
| `POST` | `/api/export-clip` | Export selected audio segments to .m4a clip |
| `GET` | `/api/pick-folder` | Open native macOS folder picker dialog |

### Projects
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/projects` | List all projects (metadata, speaker durations) |
| `POST` | `/api/projects` | Create a new project |
| `GET` | `/api/projects/{id}` | Get full project data including utterances |
| `PUT` | `/api/projects/{id}` | Update project (utterances, speakers, speaker names) |
| `PATCH` | `/api/projects/{id}/rename` | Rename a project's display name |
| `DELETE` | `/api/projects/{id}` | Delete project and all associated files |

### Settings
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/settings` | Get current settings and available Whisper models |
| `PUT` | `/api/settings` | Update settings (partial update supported) |

---

## 8. Keyboard Shortcuts

| Shortcut | Action | Context |
|----------|--------|---------|
| `Space` | Play / Pause | Editor (when not editing text) |
| `←` / `→` | Rewind / Forward 5 seconds | Editor (when not editing text) |
| `Shift+←` / `Shift+→` | Previous / Next segment | Editor (when not editing text) |
| `⌘F` / `Ctrl+F` | Open search | Editor |
| `⌘H` / `Ctrl+H` | Open find & replace | Editor |
| `Enter` | Next match | Search bar focused |
| `Shift+Enter` | Previous match | Search bar focused |
| `Escape` | Close search bar | Search bar open |

Keyboard shortcuts for playback are disabled when a text input is focused (editing utterances, search fields, etc.).

---

## 9. Visual Design

### Color Palette
| Token | Value | Usage |
|-------|-------|-------|
| Background | `#f8f9fa` | Page background |
| Surface | `#ffffff` | Cards, modals, inputs |
| Border | `#dee2e6` | Dividers, card borders |
| Text | `#212529` | Primary text |
| Text muted | `#6c757d` | Secondary text, timestamps |
| Primary | `#4263eb` | Buttons, links, active states |
| Danger | `#e03131` | Delete buttons, errors |
| Success | `#2f9e44` | Toast notifications, export confirmation |

### Typography
- **Body:** System font stack (`-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif`)
- **Monospace:** `SF Mono, Monaco, Menlo` (file paths, code-style text)

### Speaker Colors
10-color palette for utterance block left borders, auto-cycling for additional speakers:
`#4263eb`, `#e8590c`, `#2f9e44`, `#7950f2`, `#e03131`, `#1098ad`, `#f08c00`, `#0ca678`, `#9c36b5`, `#74b816`

### Search Highlights
- Match: Yellow (`#fff3bf`)
- Current match: Orange (`#ffa94d`)

---

## 10. Packaging & Distribution

### For end users (no terminal required):
- **`EarWitness Setup.command`** — One-time double-clickable setup script that:
  - Verifies Python 3.11+ is installed
  - Checks for ffmpeg (installs via Homebrew if missing)
  - Creates virtual environment and installs pip dependencies
  - Creates `.env` file from template
- **`EarWitness.command`** — Double-clickable launcher that:
  - Activates the virtual environment
  - Starts the server
  - Opens the browser to `http://localhost:8000`
  - Displays "Close this window to stop" in the Terminal window

### For development:
```bash
source venv/bin/activate
python run.py --dev    # Enables auto-reload on file changes
```

---

## 11. Project File Structure

```
TranscriptionTool/
├── EarWitness.command          # Double-click launcher
├── EarWitness Setup.command    # One-time setup script
├── run.py                      # Entry point (starts uvicorn server)
├── settings.json               # User settings (auto-generated)
├── requirements.txt            # Python dependencies with pinned versions
├── .env                        # API keys (gitignored)
├── .env.example                # Template for API keys
├── README.md                   # Setup and usage documentation
│
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app and route definitions
│   ├── transcribe.py           # AssemblyAI cloud transcription
│   ├── transcribe_local.py     # Local mlx-whisper + pyannote pipeline
│   ├── export.py               # Markdown formatting, file export, audio clips
│   ├── projects.py             # Project CRUD and storage
│   └── settings.py             # Settings persistence and validation
│
└── frontend/
    └── index.html              # Single-page app (HTML + CSS + JS)
```

---

## 12. Non-Functional Requirements

| Requirement | Expectation |
|-------------|-------------|
| **Processing time** | Cloud: 1–3 min for typical recordings. Local: slower, first run includes ~3GB model download |
| **File size** | Handles recordings up to 2 hours without issues |
| **Concurrency** | Local transcriptions are mutex-locked (one at a time) to prevent OOM on 16GB machines |
| **Reliability** | Graceful error handling for API timeouts, null responses, cancelled transcriptions |
| **Data retention** | Temp files cleaned up after processing; project audio persists until project is deleted |

---

## 13. Out of Scope

The following are not part of the current build:

- Real-time or live recording capture
- System audio / computer speaker recording
- Microphone recording in the browser
- Multi-user access or authentication
- Cloud storage or sync
- AI summarization or analysis
- Batch processing of multiple files
- Undo/redo in the editor
- Cross-platform support (macOS with Apple Silicon only)

---

*End of Specification — v2.0*
