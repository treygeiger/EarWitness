"""FastAPI app and route definitions."""

import asyncio
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.transcribe import transcribe_audio
from backend.transcribe_local import transcribe_audio_local, TranscriptionCancelled
from backend.export import build_transcript_md, save_transcript, export_audio_clip, get_default_output_dir
from backend.settings import load_settings, save_settings, WHISPER_MODELS
from backend.projects import (
    list_projects, create_project, get_project,
    update_project, rename_project, delete_project, get_project_audio_path,
)

# Prevent concurrent local transcriptions (OOM risk on 16GB)
_local_lock = threading.Lock()

# Cancellation signal for the running local transcription
_cancel_event = threading.Event()

# Persist the most recent audio file for in-browser playback
_current_audio_path: str | None = None


def _save_audio_for_playback(src_path: str) -> None:
    """Copy the uploaded audio to a persistent temp file for the player."""
    global _current_audio_path
    _cleanup_current_audio()
    suffix = Path(src_path).suffix
    fd, persist_path = tempfile.mkstemp(suffix=suffix, prefix="transcriber_audio_")
    os.close(fd)
    shutil.copy2(src_path, persist_path)
    _current_audio_path = persist_path


def _cleanup_current_audio() -> None:
    """Remove the persisted audio file (only if it's a temp file, not a project file)."""
    global _current_audio_path
    if _current_audio_path and os.path.exists(_current_audio_path):
        # Only delete temp files — never delete audio stored inside a project folder
        if _current_audio_path.startswith(tempfile.gettempdir()):
            os.unlink(_current_audio_path)
    _current_audio_path = None


app = FastAPI(title="EarWitness")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Serve static assets if any exist
static_dir = FRONTEND_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the single-page app."""
    index_path = FRONTEND_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.post("/api/transcribe")
async def api_transcribe(file: UploadFile, engine: str = Form("assemblyai")):
    """Upload an audio file and return the diarized transcript."""
    SUPPORTED_EXTENSIONS = {
        # Audio
        ".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".wma",
        # Video (audio track will be used)
        ".mp4", ".mov", ".webm", ".mkv",
    }
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if not file.filename or ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Supported: "
                   + ", ".join(sorted(SUPPORTED_EXTENSIONS)),
        )

    # Save uploaded file to a temp location
    tmp_dir = tempfile.mkdtemp(prefix="transcriber_")
    tmp_path = os.path.join(tmp_dir, file.filename)

    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Persist a copy for the audio player
        _save_audio_for_playback(tmp_path)

        loop = asyncio.get_event_loop()

        if engine == "local":
            if not _local_lock.acquire(blocking=False):
                raise HTTPException(
                    status_code=429,
                    detail="A local transcription is already in progress. Please wait.",
                )

            # Reset cancellation flag for this run
            _cancel_event.clear()

            # Stream progress via SSE for local engine
            queue = asyncio.Queue()

            def on_progress(msg):
                loop.call_soon_threadsafe(queue.put_nowait, ("progress", msg))

            def run_local():
                try:
                    result = transcribe_audio_local(
                        tmp_path,
                        on_progress=on_progress,
                        cancel_event=_cancel_event,
                    )
                    loop.call_soon_threadsafe(queue.put_nowait, ("result", result))
                except TranscriptionCancelled:
                    loop.call_soon_threadsafe(queue.put_nowait, ("cancelled", ""))
                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))
                finally:
                    _local_lock.release()

            async def sse_generator():
                try:
                    loop.run_in_executor(None, run_local)
                    while True:
                        event_type, data = await queue.get()
                        if event_type == "progress":
                            yield f"event: progress\ndata: {data}\n\n"
                        elif event_type == "result":
                            yield f"event: result\ndata: {json.dumps(data)}\n\n"
                            return
                        elif event_type == "error":
                            yield f"event: error\ndata: {data}\n\n"
                            return
                        elif event_type == "cancelled":
                            yield f"event: cancelled\ndata: Transcription cancelled.\n\n"
                            return
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            return StreamingResponse(
                sse_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        else:
            result = await loop.run_in_executor(None, transcribe_audio, tmp_path)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return result

    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except RuntimeError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@app.post("/api/transcribe/cancel")
async def api_cancel_transcribe():
    """Signal the running local transcription to stop."""
    _cancel_event.set()
    return {"ok": True}


class ExportRequest(BaseModel):
    filename: str
    duration_ms: int
    utterances: list[dict]
    speaker_names: dict[str, str]
    output_dir: str | None = None


class ExportClipRequest(BaseModel):
    segments: list[dict]  # [{"start_ms": int, "end_ms": int}]
    filename: str
    folder: str | None = None


class CreateProjectRequest(BaseModel):
    name: str
    transcript: dict  # {utterances, speakers, duration_ms}
    speaker_names: dict[str, str]


class UpdateProjectRequest(BaseModel):
    utterances: list[dict]
    speaker_names: dict[str, str]
    speakers: list[str]


class RenameProjectRequest(BaseModel):
    name: str


class SettingsRequest(BaseModel):
    export_folder: str | None = None
    default_engine: str | None = None
    assemblyai_api_key: str | None = None
    assemblyai_model: str | None = None
    whisper_model: str | None = None


@app.post("/api/export")
async def api_export(req: ExportRequest):
    """Export the edited transcript as a .md file."""
    output_dir = req.output_dir or get_default_output_dir()

    content = build_transcript_md(
        filename=req.filename,
        duration_ms=req.duration_ms,
        utterances=req.utterances,
        speaker_names=req.speaker_names,
    )

    file_path = save_transcript(
        filename=req.filename,
        content=content,
        output_dir=output_dir,
    )

    return {"file_path": file_path}


@app.post("/api/export-clip")
async def api_export_clip(req: ExportClipRequest):
    """Export selected transcript segments as a standalone audio clip."""
    if not _current_audio_path or not os.path.exists(_current_audio_path):
        raise HTTPException(status_code=400, detail="No audio file available.")

    if not req.segments:
        raise HTTPException(status_code=400, detail="No segments provided.")

    for seg in req.segments:
        if "start_ms" not in seg or "end_ms" not in seg:
            raise HTTPException(status_code=400, detail="Each segment must have start_ms and end_ms.")
        if seg["start_ms"] >= seg["end_ms"]:
            raise HTTPException(status_code=400, detail="Segment start must be before end.")

    try:
        file_path = export_audio_clip(
            audio_path=_current_audio_path,
            segments=req.segments,
            filename=req.filename,
            output_dir=req.folder or get_default_output_dir(),
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"FFmpeg error: {e.stderr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    return {"file_path": file_path}


@app.get("/api/pick-folder")
async def api_pick_folder():
    """Open a native macOS folder picker dialog and return the selected path."""
    script = '''
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
    end tell
    set chosenFolder to choose folder with prompt "Select output folder" default location (path to documents folder)
    tell application frontApp to activate
    return POSIX path of chosenFolder
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"folder": None}
        folder = result.stdout.strip()
        return {"folder": folder}
    except subprocess.TimeoutExpired:
        return {"folder": None}


@app.get("/api/audio")
async def api_audio():
    """Serve the most recently transcribed audio file for in-browser playback."""
    if not _current_audio_path or not os.path.exists(_current_audio_path):
        raise HTTPException(status_code=404, detail="No audio file available.")
    mime, _ = mimetypes.guess_type(_current_audio_path)
    suffix = Path(_current_audio_path).suffix or ".m4a"
    return FileResponse(
        _current_audio_path,
        media_type=mime or "application/octet-stream",
        filename=f"audio{suffix}",
    )


# ── Project endpoints ──────────────────────────────────────────────────────


@app.get("/api/projects")
async def api_list_projects():
    """Return metadata for all saved projects."""
    return list_projects()


@app.post("/api/projects")
async def api_create_project(req: CreateProjectRequest):
    """Create a new project from the current transcript and audio."""
    global _current_audio_path

    if not _current_audio_path or not os.path.exists(_current_audio_path):
        raise HTTPException(
            status_code=400,
            detail="No audio file available. Transcribe a file first.",
        )

    try:
        project = create_project(
            name=req.name,
            transcript=req.transcript,
            speaker_names=req.speaker_names,
            audio_source_path=_current_audio_path,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create project: {e}")

    # Point playback at the project's own audio copy
    _current_audio_path = get_project_audio_path(project["id"])

    return project


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str):
    """Load a saved project and set audio for playback."""
    try:
        project = get_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID.")

    # Point the audio player at this project's audio file
    global _current_audio_path
    _cleanup_current_audio()
    try:
        _current_audio_path = get_project_audio_path(project_id)
    except FileNotFoundError:
        pass  # Project exists but audio file is missing — player will 404

    return project


@app.put("/api/projects/{project_id}")
async def api_update_project(project_id: str, req: UpdateProjectRequest):
    """Save updated transcript edits to an existing project."""
    try:
        updated = update_project(
            project_id=project_id,
            utterances=req.utterances,
            speaker_names=req.speaker_names,
            speakers=req.speakers,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID.")

    return updated


@app.patch("/api/projects/{project_id}/rename")
async def api_rename_project(project_id: str, req: RenameProjectRequest):
    """Rename a project."""
    new_name = req.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")

    try:
        updated = rename_project(project_id=project_id, new_name=new_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID.")

    return updated


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str):
    """Delete a project and all its files."""
    global _current_audio_path

    # If we're currently playing this project's audio, clear the reference
    try:
        audio_path = get_project_audio_path(project_id)
        if _current_audio_path == audio_path:
            _current_audio_path = None
    except (FileNotFoundError, ValueError):
        pass

    try:
        delete_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID.")

    return {"ok": True}


# ── Settings endpoints ─────────────────────────────────────────────────────


@app.get("/api/settings")
async def api_get_settings():
    """Return current settings and available model options."""
    settings = load_settings()
    settings["whisper_model_options"] = WHISPER_MODELS
    return settings


@app.put("/api/settings")
async def api_put_settings(req: SettingsRequest):
    """Update settings (partial update — only supplied fields are changed)."""
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No settings provided.")
    updated = save_settings(data)
    updated["whisper_model_options"] = WHISPER_MODELS
    return updated
