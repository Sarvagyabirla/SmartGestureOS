"""
SettingsManager — profile loading, saving, and validation.

Architecture:
    config/defaults.json        = immutable factory defaults (read-only resource)
    LOCALAPPDATA/.../profiles/  = user profiles (read-write)

Profile names are sanitized: only letters, numbers, spaces, underscores,
and hyphens are allowed; max 64 characters; reserved Windows filenames rejected.
"""

import json
import re
import shutil
from pathlib import Path
from src.paths import RESOURCE_DIR, PROFILES_DIR
from src.logger import logger

# F-09 FIX: profile name validation
_PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _\-]{1,64}$")
_WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})


def validate_profile_name(name: str) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    Allowed: letters, numbers, spaces, underscores, hyphens, 1–64 chars.
    """
    if not name:
        return False, "Profile name cannot be empty."
    if not _PROFILE_NAME_PATTERN.match(name):
        return False, (
            "Profile name may only contain letters, numbers, spaces, "
            "underscores, and hyphens (max 64 characters)."
        )
    if name.upper() in _WINDOWS_RESERVED_NAMES:
        return False, f"'{name}' is a reserved Windows filename."
    return True, ""


class SettingsManager:
    """
    Manages application settings and user profiles.

    - Active Profile: stored in LOCALAPPDATA/.../profiles/<name>.json
    - Factory Defaults: config/defaults.json (read-only; merged as base)
    - Active Settings: self.settings = merged result
    """

    def __init__(self):
        self.profiles_dir = PROFILES_DIR
        self.current_profile = "default"
        self.settings: dict = {}
        self.callbacks: list = []
        self.load_profile(self.current_profile)

    def register_callback(self, callback) -> None:
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def apply_settings(self) -> None:
        for callback in self.callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in settings callback: {e}")

    def _get_default_settings(self) -> dict:
        defaults_path = RESOURCE_DIR / "config" / "defaults.json"
        if defaults_path.exists():
            try:
                with open(defaults_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load defaults.json: {e}")
        return {"profile_name": "default"}

    def _get_profile_path(self, profile_name: str) -> Path:
        # Path is always constructed internally — never from raw user input after validation
        return self.profiles_dir / f"{profile_name}.json"

    def get_all_profiles(self) -> list[str]:
        profiles = [f.stem for f in self.profiles_dir.glob("*.json")]
        if "default" not in profiles:
            profiles.append("default")
        return sorted(set(profiles))

    def load_profile(self, profile_name: str) -> bool:
        # F-09 FIX: validate before building path
        valid, reason = validate_profile_name(profile_name)
        if not valid:
            logger.error(f"Refused to load profile '{profile_name}': {reason}")
            return False

        path = self._get_profile_path(profile_name)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = self._merge_dicts(self._get_default_settings(), data)
                self.settings.clear()
                self.settings.update(merged)
                self.current_profile = profile_name
                self.apply_settings()
                return True
            except Exception as e:
                logger.error(f"Failed to load profile '{profile_name}': {e}")

        # Profile doesn't exist — create with defaults
        self.settings.clear()
        self.settings.update(self._get_default_settings())
        self.settings["profile_name"] = profile_name
        self.current_profile = profile_name
        self.save_profile()
        self.apply_settings()
        return True

    def save_profile(self) -> bool:
        valid, reason = validate_profile_name(self.current_profile)
        if not valid:
            logger.error(f"Refused to save profile '{self.current_profile}': {reason}")
            return False

        path = self._get_profile_path(self.current_profile)
        # Atomic write: write to temp file then rename
        tmp_path = path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
            tmp_path.replace(path)
            self.apply_settings()
            return True
        except Exception as e:
            logger.error(f"Failed to save profile '{self.current_profile}': {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

    def delete_profile(self, profile_name: str) -> bool:
        if profile_name == "default":
            return False  # Cannot delete default

        valid, reason = validate_profile_name(profile_name)
        if not valid:
            logger.error(f"Refused to delete profile '{profile_name}': {reason}")
            return False

        path = self._get_profile_path(profile_name)
        if path.exists():
            path.unlink()
            if self.current_profile == profile_name:
                self.load_profile("default")
            return True
        return False

    def _merge_dicts(self, default_dict: dict, user_dict: dict) -> dict:
        """Deep-merge user_dict into default_dict. User values take precedence."""
        result = default_dict.copy()
        for k, v in user_dict.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._merge_dicts(result[k], v)
            else:
                result[k] = v
        return result


# Global singleton
settings_manager = SettingsManager()
