import logging
import shutil
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
    On Windows, this is %LOCALAPPDATA%\\SmartGestureOS.
    """
    return Path(user_data_dir("SmartGestureOS", appauthor=False))

USER_DATA_DIR = get_user_data_dir()
LEGACY_USER_DATA_DIR = Path(user_data_dir("SmartGesture", appauthor=False))


def migrate_legacy_user_data(source: Path, destination: Path) -> bool:
    """Copy previous releases' local data once, retaining originals and new files.

    This runs before opening the log or loading profiles. A completion marker
    prevents deliberately removed files from reappearing on the next launch.
    A failed copy is retried at the next launch without replacing user data.
    """
    marker = destination / ".legacy-data-copied"
    if marker.exists() or not source.is_dir():
        return True
    try:
        destination.mkdir(parents=True, exist_ok=True)
        for folder in ("profiles", "custom_gestures", "screenshots", "drawings", "logs", "benchmarks"):
            old_folder = source / folder
            if not old_folder.is_dir() or old_folder.is_symlink():
                continue
            for old_file in old_folder.iterdir():
                if not old_file.is_file() or old_file.is_symlink():
                    continue
                new_folder = destination / folder
                new_folder.mkdir(parents=True, exist_ok=True)
                new_file = new_folder / old_file.name
                if new_file.exists():
                    continue
                # Publish only a complete copy. Original files stay untouched.
                temporary = new_file.with_name(new_file.name + ".migration.tmp")
                try:
                    shutil.copy2(old_file, temporary)
                    temporary.replace(new_file)
                finally:
                    temporary.unlink(missing_ok=True)
        marker.touch()
        return True
    except OSError as exc:
        logging.getLogger("SmartGestureOS").warning("Legacy local-data copy incomplete: %s", exc)
        return False

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
    for directory in (PROFILES_DIR, LOGS_DIR, SCREENSHOTS_DIR, DRAWINGS_DIR,
                      BENCHMARKS_DIR, CUSTOM_GESTURES_DIR):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # Saving features report the error; unavailable storage need not
            # disable camera preview, gesture detection or emergency pause.
            logging.getLogger("SmartGestureOS").warning("User-data directory unavailable: %s: %s", directory, exc)

migrate_legacy_user_data(LEGACY_USER_DATA_DIR, USER_DATA_DIR)
ensure_user_dirs()
