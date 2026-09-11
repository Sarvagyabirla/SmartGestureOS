import os
import sys
from pathlib import Path
from platformdirs import user_data_dir

def get_base_dir() -> Path:
    """
    Get the base directory for read-only resources.
    When frozen by PyInstaller, this is sys._MEIPASS.
    Otherwise, it is the root of the repository.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

RESOURCE_DIR = get_base_dir()

def get_user_data_dir() -> Path:
    """
    Get the base directory for user-writable data.
    On Windows, this is %LOCALAPPDATA%\\SmartGesture.
    """
    return Path(user_data_dir("SmartGesture", appauthor=False))

USER_DATA_DIR = get_user_data_dir()

# Specific user data subdirectories
PROFILES_DIR = USER_DATA_DIR / "profiles"
LOGS_DIR = USER_DATA_DIR / "logs"
SCREENSHOTS_DIR = USER_DATA_DIR / "screenshots"
DRAWINGS_DIR = USER_DATA_DIR / "drawings"
BENCHMARKS_DIR = USER_DATA_DIR / "benchmarks"
CUSTOM_GESTURES_DIR = USER_DATA_DIR / "custom_gestures"
SETTINGS_FILE = USER_DATA_DIR / "settings.json"

def ensure_user_dirs():
    """Ensure all user data directories exist."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    DRAWINGS_DIR.mkdir(parents=True, exist_ok=True)
    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_GESTURES_DIR.mkdir(parents=True, exist_ok=True)

ensure_user_dirs()
