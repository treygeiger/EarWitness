"""AssemblyAI integration for transcription and speaker diarization.

Uses the REST API directly instead of the SDK to avoid Python 3.14
compatibility issues with the assemblyai package.
"""

import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.assemblyai.com/v2"
POLL_INTERVAL = 5  # seconds


def _get_api_key() -> str:
    """Return the AssemblyAI API key (settings first, then .env fallback)."""
    from backend.settings import get_setting
    key = get_setting("assemblyai_api_key", "")
    if not key:
        key = os.getenv("ASSEMBLYAI_API_KEY", "")
    return key


def _get_assemblyai_model() -> str:
    """Return the configured AssemblyAI model."""
    from backend.settings import get_setting
    return get_setting("assemblyai_model", "universal-3-pro")


def _headers(json=False):
    h = {"Authorization": _get_api_key()}
    if json:
        h["Content-Type"] = "application/json"
    return h


def transcribe_audio(file_path: str) -> dict:
    """Transcribe an audio file with speaker diarization via AssemblyAI.

    Returns a dict with:
        - utterances: list of utterance dicts (speaker, text, start, end, words)
        - speakers: list of unique speaker labels
        - duration_ms: total audio duration in milliseconds
    """
    if not _get_api_key():
        raise RuntimeError("ASSEMBLYAI_API_KEY not set. Configure it in Settings or your .env file.")

    # Step 1: Upload the file
    with open(file_path, "rb") as f:
        upload_resp = httpx.post(
            f"{BASE_URL}/upload",
            headers=_headers(),
            content=f,
            timeout=300.0,
        )
    if upload_resp.status_code != 200:
        raise RuntimeError(f"Upload failed ({upload_resp.status_code}): {upload_resp.text}")
    upload_url = upload_resp.json()["upload_url"]

    # Step 2: Request transcription with speaker diarization
    import json as json_mod
    body = json_mod.dumps({
        "audio_url": upload_url,
        "speaker_labels": True,
        "speech_models": [_get_assemblyai_model()],
    })
    transcript_resp = httpx.post(
        f"{BASE_URL}/transcript",
        headers=_headers(json=True),
        content=body,
        timeout=30.0,
    )
    if transcript_resp.status_code != 200:
        raise RuntimeError(
            f"Transcript request failed ({transcript_resp.status_code}): {transcript_resp.text}"
        )
    transcript_id = transcript_resp.json()["id"]

    # Step 3: Poll until complete
    while True:
        poll_resp = httpx.get(
            f"{BASE_URL}/transcript/{transcript_id}",
            headers=_headers(),
            timeout=30.0,
        )
        if poll_resp.status_code != 200:
            raise RuntimeError(f"Poll failed ({poll_resp.status_code}): {poll_resp.text}")
        data = poll_resp.json()

        if data["status"] == "completed":
            break
        elif data["status"] == "error":
            raise RuntimeError(f"Transcription failed: {data.get('error', 'Unknown error')}")

        time.sleep(POLL_INTERVAL)

    # Step 4: Parse the response
    utterances = []
    speakers = set()

    for utt in (data.get("utterances") or []):
        speaker = utt["speaker"]
        speakers.add(speaker)
        words = [
            {"text": w["text"], "start": w["start"], "end": w["end"], "speaker": w["speaker"]}
            for w in utt.get("words", [])
        ]
        utterances.append({
            "speaker": speaker,
            "text": utt["text"],
            "start": utt["start"],
            "end": utt["end"],
            "words": words,
        })

    duration_ms = data.get("audio_duration", 0) * 1000

    return {
        "utterances": utterances,
        "speakers": sorted(speakers),
        "duration_ms": int(duration_ms),
    }
