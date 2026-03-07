"""Local transcription + diarization using mlx-whisper and pyannote.audio.

Models are loaded lazily on first call to avoid slow server startup.
First invocation downloads ~3GB of models to ~/.cache/huggingface/.
"""

import os
import subprocess
import tempfile

from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")

WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"  # fallback default


def _get_whisper_model() -> str:
    """Return the configured Whisper model (reads from settings)."""
    from backend.settings import get_setting
    return get_setting("whisper_model", WHISPER_MODEL)

# Lazy-loaded singletons
_diarization_pipeline = None


def _get_diarization_pipeline():
    global _diarization_pipeline
    if _diarization_pipeline is not None:
        return _diarization_pipeline

    if not HF_TOKEN:
        raise RuntimeError(
            "HF_TOKEN not set in .env. A HuggingFace token is required for "
            "pyannote speaker diarization. Get one at https://huggingface.co/settings/tokens"
        )

    try:
        from pyannote.audio import Pipeline

        _diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-community-1",
            token=HF_TOKEN,
        )
        return _diarization_pipeline
    except Exception as e:
        if "403" in str(e) or "gated" in str(e).lower() or "access" in str(e).lower():
            raise RuntimeError(
                "pyannote model access denied. Please:\n"
                "1. Accept the license at https://huggingface.co/pyannote/speaker-diarization-community-1\n"
                "2. Ensure HF_TOKEN in .env is a valid HuggingFace token"
            ) from e
        raise


def _normalize_speaker(label: str) -> str:
    """Convert 'SPEAKER_00' -> 'A', 'SPEAKER_01' -> 'B', etc."""
    if label.startswith("SPEAKER_"):
        try:
            idx = int(label.split("_")[-1])
            return chr(ord("A") + idx)
        except (ValueError, IndexError):
            pass
    return label


def _find_speaker_at(time_sec: float, segments: list) -> str:
    """Find the speaker whose diarization segment contains the given time point."""
    for start, end, speaker in segments:
        if start <= time_sec <= end:
            return speaker
    # Fallback: nearest segment
    if not segments:
        return "A"
    closest = min(segments, key=lambda s: min(abs(s[0] - time_sec), abs(s[1] - time_sec)))
    return closest[2]


def _group_words_into_utterances(words: list[dict]) -> list[dict]:
    """Group consecutive words with the same speaker into utterances."""
    if not words:
        return []

    utterances = []
    current_speaker = words[0]["speaker"]
    current_words = [words[0]]

    for word in words[1:]:
        if word["speaker"] == current_speaker:
            current_words.append(word)
        else:
            utterances.append(_make_utterance(current_speaker, current_words))
            current_speaker = word["speaker"]
            current_words = [word]

    utterances.append(_make_utterance(current_speaker, current_words))
    return utterances


def _make_utterance(speaker: str, words: list[dict]) -> dict:
    return {
        "speaker": speaker,
        "text": " ".join(w["text"] for w in words),
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "words": words,
    }


def _convert_to_wav(file_path: str) -> str:
    """Convert audio to 16kHz mono WAV for pyannote compatibility.

    M4A files can have slightly irregular sample counts that cause pyannote
    to raise chunk sample mismatch errors. Converting to a standard WAV
    with exact 16kHz sample rate avoids this.
    """
    wav_path = tempfile.mktemp(suffix=".wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", file_path,
            "-ar", "16000", "-ac", "1", "-f", "wav", wav_path,
        ],
        capture_output=True,
        check=True,
    )
    return wav_path


class TranscriptionCancelled(Exception):
    """Raised when the user cancels a local transcription."""


def transcribe_audio_local(file_path: str, on_progress=None, cancel_event=None) -> dict:
    """Transcribe an audio file locally with speaker diarization.

    Uses mlx-whisper for transcription and pyannote.audio for diarization.
    Returns the same dict format as transcribe_audio() in transcribe.py.

    on_progress: optional callback(message: str) for status updates.
    cancel_event: optional threading.Event; if set, cancels between steps.
    """
    import mlx_whisper

    def _progress(msg):
        if on_progress:
            on_progress(msg)

    def _check_cancelled():
        if cancel_event and cancel_event.is_set():
            raise TranscriptionCancelled("Transcription cancelled by user.")

    # Step 1: Transcribe with word-level timestamps
    _check_cancelled()
    _progress("Running speech-to-text (mlx-whisper)…")
    result = mlx_whisper.transcribe(
        file_path,
        path_or_hf_repo=_get_whisper_model(),
        word_timestamps=True,
    )

    # Step 2: Convert to 16kHz WAV for pyannote, then run speaker diarization
    _check_cancelled()
    _progress("Converting audio for speaker detection…")
    wav_path = _convert_to_wav(file_path)
    try:
        _check_cancelled()
        _progress("Running speaker diarization (pyannote)… This is the slowest step.")
        pipeline = _get_diarization_pipeline()
        output = pipeline(wav_path)
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)

    _check_cancelled()

    # Step 3: Build speaker timeline from diarization
    # pyannote.audio 4.x returns DiarizeOutput; use exclusive_speaker_diarization
    # for non-overlapping segments (better for transcription alignment).
    _progress("Aligning speakers to transcript…")
    diarization = output.exclusive_speaker_diarization
    speaker_segments = []
    for turn, speaker in diarization:
        normalized = _normalize_speaker(speaker)
        speaker_segments.append((turn.start, turn.end, normalized))

    # Step 4: Assign each word to a speaker via temporal midpoint
    words_with_speakers = []
    for segment in result.get("segments", []):
        for word_info in segment.get("words", []):
            word_start = word_info["start"]  # seconds (float)
            word_end = word_info["end"]
            midpoint = (word_start + word_end) / 2.0

            speaker = _find_speaker_at(midpoint, speaker_segments)

            words_with_speakers.append({
                "text": word_info["word"].strip(),
                "start": int(word_start * 1000),
                "end": int(word_end * 1000),
                "speaker": speaker,
            })

    # Step 5: Group consecutive same-speaker words into utterances
    utterances = _group_words_into_utterances(words_with_speakers)

    # Step 6: Compute duration and collect speakers
    speakers = sorted(set(w["speaker"] for w in words_with_speakers)) if words_with_speakers else []

    segments = result.get("segments", [])
    duration_ms = int(segments[-1]["end"] * 1000) if segments else 0

    return {
        "utterances": utterances,
        "speakers": speakers,
        "duration_ms": duration_ms,
    }
