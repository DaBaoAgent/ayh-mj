```python
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Constants
VIDEO_FOLDER = ROOT / "out"
LOGS_FOLDER = ROOT / "logs"
MANIFEST_FOLDER = ROOT / "manifests"
SUBTITLES_FOLDER = ROOT / "subtitles"
UPLOAD_FOLDER = ROOT / "upload"
CACHE_FOLDER = ROOT / "cache"
CACHE_MAX_AGE_DAYS = 7

# Environment variables
INPUT_FOLDER_ENV = "INPUT_FOLDER"
OUTPUT_FOLDER_ENV = "OUTPUT_FOLDER"
SUBTITLES_FOLDER_ENV = "SUBTITLES_FOLDER"
UPLOAD_FOLDER_ENV = "UPLOAD_FOLDER"
CACHE_FOLDER_ENV = "CACHE_FOLDER"
CACHE_MAX_AGE_DAYS_ENV = "CACHE_MAX_AGE_DAYS"

# Utility functions
def get_input_folder():
    return os.environ[INPUT_FOLDER_ENV]

def get_output_folder():
    return os.environ[OUTPUT_FOLDER_ENV]

def get_subtitles_folder():
    return os.environ[SUBTITLES_FOLDER_ENV]

def get_upload_folder():
    return os.environ[UPLOAD_FOLDER_ENV]

def get_cache_folder():
    return os.environ[CACHE_FOLDER_ENV]

def get_cache_max_age_days():
    return int(os.environ[CACHE_MAX_AGE_DAYS_ENV])

def clear_cache():
    cache_folder = get_cache_folder()
    for item in cache_folder.iterdir():
        if item.is_file() and item.stat().st_mtime < time.time() - CACHE_MAX_AGE_DAYS * 86400:
            item.unlink()

# Main
if __name__ == "__main__":
    # Clear cache
    clear_cache()

    # Get environment variables
    input_folder = get_input_folder()
    output_folder = get_output_folder()
    subtitles_folder = get_subtitles_folder()
    upload_folder = get_upload_folder()
    cache_folder = get_cache_folder()
    cache_max_age_days = get_cache_max_age_days()

    # Download media
    download_media(input_folder, output_folder)

    # Transcribe subtitles
    transcribe_subtitles(input_folder, subtitles_folder)

    # Upload media
    upload_media(upload_folder)

    # Clean up cache
    clear_cache()
```