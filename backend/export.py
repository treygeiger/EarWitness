"""Transcript formatting and file export."""

import os
import re
import subprocess
from datetime import date
from pathlib import Path

DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Documents/Transcripts")


def get_default_output_dir() -> str:
    """Return the configured default export folder (reads from settings)."""
    from backend.settings import get_setting
    return os.path.expanduser(get_setting("export_folder", "~/Documents/Transcripts"))


def format_timestamp(ms: int) -> str:
    """Convert milliseconds to MM:SS or H:MM:SS format."""
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_duration(ms: int) -> str:
    """Convert milliseconds to a human-readable duration string."""
    return format_timestamp(ms)


def _extract_date(filename: str) -> str:
    """Try to extract a YYYY-MM-DD date from the filename, else return today."""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if match:
        return match.group(1)
    return date.today().isoformat()


def _format_duration_rounded(ms: int) -> str:
    """Round duration to the nearest minute for the header."""
    minutes = round(ms / 60_000)
    if minutes < 1:
        return "< 1 min"
    return f"{minutes} min"


def build_transcript_md(
    filename: str,
    duration_ms: int,
    utterances: list[dict],
    speaker_names: dict[str, str],
) -> str:
    """Build the Markdown export content.

    Args:
        filename: The project / file name (without extension).
        duration_ms: Total audio duration in milliseconds.
        utterances: List of utterance dicts with speaker, text, start keys.
        speaker_names: Mapping of raw speaker labels to display names.
    """
    # Collect speaker display names in order of first appearance
    seen = []
    for utt in utterances:
        raw = utt["speaker"]
        name = speaker_names.get(raw, raw)
        if name not in seen:
            seen.append(name)

    date_str = _extract_date(filename)
    attendees_str = ", ".join(seen)
    duration_str = _format_duration_rounded(duration_ms)

    lines = [
        f"**Date:** {date_str}",
        f"**Attendees:** {attendees_str}",
        f"**Duration:** {duration_str}",
        "",
        "---",
        "",
        "## Transcript",
        "",
    ]

    for utt in utterances:
        raw = utt["speaker"]
        name = speaker_names.get(raw, raw)
        ts = format_timestamp(utt["start"])
        lines.append(f"[{ts}] {name}: {utt['text']}")
        lines.append("")

    return "\n".join(lines)


def save_transcript(
    filename: str,
    content: str,
    output_dir: str | None = None,
) -> str:
    """Write transcript content to a .md file.

    Returns the absolute path of the saved file.
    """
    folder = os.path.expanduser(output_dir or DEFAULT_OUTPUT_DIR)
    Path(folder).mkdir(parents=True, exist_ok=True)

    # Strip any old .txt extension and ensure .md
    if filename.endswith(".txt"):
        filename = filename[:-4]
    if not filename.endswith(".md"):
        filename += ".md"

    file_path = os.path.join(folder, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


def export_audio_clip(
    audio_path: str,
    segments: list[dict],
    filename: str,
    output_dir: str | None = None,
) -> str:
    """Extract and concatenate audio segments into a single clip file.

    Args:
        audio_path: Path to the source audio file.
        segments: List of dicts with ``start_ms`` and ``end_ms`` keys (int, milliseconds).
        filename: Output filename (without extension).
        output_dir: Destination folder.  Defaults to ~/Documents/Transcripts/.

    Returns:
        Absolute path of the exported clip file.
    """
    folder = os.path.expanduser(output_dir or DEFAULT_OUTPUT_DIR)
    Path(folder).mkdir(parents=True, exist_ok=True)

    if not filename.endswith(".m4a"):
        filename += ".m4a"
    output_path = os.path.join(folder, filename)

    # Sort segments by start time
    segs = sorted(segments, key=lambda s: s["start_ms"])

    if len(segs) == 1:
        # Single segment — simple trim
        start_sec = segs[0]["start_ms"] / 1000.0
        end_sec = segs[0]["end_ms"] / 1000.0
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-c:a", "aac", "-b:a", "128k",
            output_path,
        ]
    else:
        # Multiple segments — use filter_complex with atrim + concat
        filter_parts = []
        stream_labels = []
        for i, seg in enumerate(segs):
            start_sec = seg["start_ms"] / 1000.0
            end_sec = seg["end_ms"] / 1000.0
            label = f"a{i}"
            filter_parts.append(
                f"[0]atrim=start={start_sec}:end={end_sec},asetpts=PTS-STARTPTS[{label}]"
            )
            stream_labels.append(f"[{label}]")

        concat_input = "".join(stream_labels)
        filter_parts.append(
            f"{concat_input}concat=n={len(segs)}:v=0:a=1[out]"
        )
        filter_complex = ";".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:a", "aac", "-b:a", "128k",
            output_path,
        ]

    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return os.path.abspath(output_path)
