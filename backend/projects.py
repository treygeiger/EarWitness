"""Project persistence — CRUD operations for saved transcription projects."""

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_DIR = os.path.expanduser("~/Documents/Transcripts/Projects")


def _ensure_projects_dir() -> None:
    """Create the projects directory if it doesn't exist."""
    Path(PROJECTS_DIR).mkdir(parents=True, exist_ok=True)


def _validate_project_id(project_id: str) -> str:
    """Sanitize project_id to prevent path traversal."""
    safe = os.path.basename(project_id)
    if not safe or safe != project_id or ".." in project_id:
        raise ValueError("Invalid project ID")
    return safe


def _generate_project_id(name: str) -> str:
    """Create a slug from the project name with a short UUID suffix."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = "project"
    short_id = uuid.uuid4().hex[:8]
    return f"{slug}-{short_id}"


def list_projects() -> list[dict]:
    """Return metadata for all saved projects (no utterances), sorted by modified_at desc."""
    _ensure_projects_dir()
    projects = []

    for entry in os.scandir(PROJECTS_DIR):
        if not entry.is_dir():
            continue
        json_path = os.path.join(entry.path, "project.json")
        if not os.path.isfile(json_path):
            continue
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Compute per-speaker duration from utterances
            speaker_durations = {}
            for utt in data.get("utterances", []):
                s = utt.get("speaker", "")
                dur = utt.get("end", 0) - utt.get("start", 0)
                speaker_durations[s] = speaker_durations.get(s, 0) + dur

            # Return metadata only — strip utterances to keep response small
            projects.append({
                "id": data.get("id", entry.name),
                "name": data.get("name", entry.name),
                "created_at": data.get("created_at", ""),
                "modified_at": data.get("modified_at", ""),
                "duration_ms": data.get("duration_ms", 0),
                "speakers": data.get("speakers", []),
                "speaker_names": data.get("speaker_names", {}),
                "speaker_durations": speaker_durations,
            })
        except (json.JSONDecodeError, OSError):
            # Skip corrupted projects
            continue

    # Most recent first — sort by date in project name (YYYY-MM-DD) when
    # available, otherwise fall back to modified_at timestamp.
    def _sort_key(p):
        name = p.get("name", "")
        match = re.match(r"(\d{4}-\d{2}-\d{2})", name)
        if match:
            return match.group(1)
        return p.get("modified_at", "")

    projects.sort(key=_sort_key, reverse=True)
    return projects


def create_project(
    name: str,
    transcript: dict,
    speaker_names: dict,
    audio_source_path: str,
) -> dict:
    """Create a new project folder with transcript data and a copy of the audio."""
    _ensure_projects_dir()

    project_id = _generate_project_id(name)
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(project_dir, exist_ok=True)

    # Copy audio file into project folder, preserving the original extension
    ext = Path(audio_source_path).suffix or ".m4a"
    audio_filename = f"audio{ext}"
    audio_dest = os.path.join(project_dir, audio_filename)
    shutil.copy2(audio_source_path, audio_dest)

    now = datetime.now(timezone.utc).isoformat()

    project_data = {
        "id": project_id,
        "name": name,
        "created_at": now,
        "modified_at": now,
        "duration_ms": transcript.get("duration_ms", 0),
        "speakers": transcript.get("speakers", []),
        "speaker_names": speaker_names,
        "audio_filename": audio_filename,
        "utterances": transcript.get("utterances", []),
    }

    json_path = os.path.join(project_dir, "project.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(project_data, f, indent=2, ensure_ascii=False)

    return project_data


def get_project(project_id: str) -> dict:
    """Load and return the full project data including utterances."""
    project_id = _validate_project_id(project_id)
    json_path = os.path.join(PROJECTS_DIR, project_id, "project.json")

    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"Project '{project_id}' not found.")

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_project(
    project_id: str,
    utterances: list,
    speaker_names: dict,
    speakers: list,
) -> dict:
    """Update the transcript data in an existing project."""
    project_id = _validate_project_id(project_id)
    json_path = os.path.join(PROJECTS_DIR, project_id, "project.json")

    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"Project '{project_id}' not found.")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["utterances"] = utterances
    data["speaker_names"] = speaker_names
    data["speakers"] = speakers
    data["modified_at"] = datetime.now(timezone.utc).isoformat()

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Return metadata only (no utterances)
    return {
        "id": data["id"],
        "name": data["name"],
        "created_at": data["created_at"],
        "modified_at": data["modified_at"],
        "duration_ms": data["duration_ms"],
        "speakers": data["speakers"],
        "speaker_names": data["speaker_names"],
    }


def rename_project(project_id: str, new_name: str) -> dict:
    """Rename a project (display name only — folder/ID unchanged)."""
    project_id = _validate_project_id(project_id)
    json_path = os.path.join(PROJECTS_DIR, project_id, "project.json")

    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"Project '{project_id}' not found.")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["name"] = new_name.strip()
    data["modified_at"] = datetime.now(timezone.utc).isoformat()

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return {
        "id": data["id"],
        "name": data["name"],
        "created_at": data["created_at"],
        "modified_at": data["modified_at"],
        "duration_ms": data["duration_ms"],
        "speakers": data["speakers"],
        "speaker_names": data["speaker_names"],
    }


def delete_project(project_id: str) -> None:
    """Delete a project folder and all its contents."""
    project_id = _validate_project_id(project_id)
    project_dir = os.path.join(PROJECTS_DIR, project_id)

    if not os.path.isdir(project_dir):
        raise FileNotFoundError(f"Project '{project_id}' not found.")

    shutil.rmtree(project_dir)


def get_project_audio_path(project_id: str) -> str:
    """Return the absolute path to a project's audio file."""
    project_id = _validate_project_id(project_id)
    project_dir = os.path.join(PROJECTS_DIR, project_id)

    # Read the stored audio filename from project.json (supports any extension)
    json_path = os.path.join(project_dir, "project.json")
    audio_filename = "audio.m4a"  # fallback for older projects
    if os.path.isfile(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            audio_filename = data.get("audio_filename", audio_filename)
        except (json.JSONDecodeError, OSError):
            pass

    audio_path = os.path.join(project_dir, audio_filename)

    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file for project '{project_id}' not found.")

    return audio_path
