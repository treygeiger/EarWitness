"""User settings — persistent configuration for EarWitness."""

import json
import os
from pathlib import Path

SETTINGS_DIR = str(Path(__file__).resolve().parent.parent)  # TranscriptionTool/
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

# Available local Whisper models (value, label)
WHISPER_MODELS = [
    ("mlx-community/whisper-large-v3-turbo", "Large V3 Turbo (default, fastest)"),
    ("mlx-community/whisper-large-v3-mlx", "Large V3 (best accuracy, slowest)"),
    ("mlx-community/whisper-small-mlx", "Small (lightweight, lower accuracy)"),
]

VALID_ENGINES = {"local", "assemblyai"}
VALID_ASSEMBLYAI_MODELS = {"universal-3-pro", "universal-2"}
VALID_WHISPER_MODELS = {m[0] for m in WHISPER_MODELS}

DEFAULTS = {
    "export_folder": "~/Documents/Transcripts",
    "default_engine": "local",
    "assemblyai_api_key": "",
    "assemblyai_model": "universal-3-pro",
    "whisper_model": "mlx-community/whisper-large-v3-turbo",
}


def load_settings() -> dict:
    """Load settings from disk, merged with defaults for any missing keys."""
    settings = dict(DEFAULTS)
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                settings.update(stored)
        except (json.JSONDecodeError, OSError):
            pass  # Corrupted file — fall back to defaults
    return settings


def save_settings(data: dict) -> dict:
    """Merge incoming data into existing settings, validate, and persist."""
    settings = load_settings()

    # Only update known keys
    for key in DEFAULTS:
        if key in data and data[key] is not None:
            settings[key] = data[key]

    # Validate
    if settings["default_engine"] not in VALID_ENGINES:
        settings["default_engine"] = DEFAULTS["default_engine"]
    if settings["assemblyai_model"] not in VALID_ASSEMBLYAI_MODELS:
        settings["assemblyai_model"] = DEFAULTS["assemblyai_model"]
    if settings["whisper_model"] not in VALID_WHISPER_MODELS:
        settings["whisper_model"] = DEFAULTS["whisper_model"]

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    return settings


def get_setting(key: str, fallback=None):
    """Read a single setting value (convenience for other modules)."""
    settings = load_settings()
    return settings.get(key, fallback)
