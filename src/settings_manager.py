"""
SettingsManager — profile loading, saving, and validation.

Architecture:
    config/defaults.json        = immutable factory defaults (read-only resource)
    LOCALAPPDATA/.../profiles/  = user profiles (read-write)

Profile names are sanitized: only letters, numbers, spaces, underscores,
and hyphens are allowed; max 64 characters; reserved Windows filenames rejected.
"""

import json
import math
import re
from copy import deepcopy
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

# Complete, conservative startup settings if the packaged defaults are damaged.
# Empty action maps keep camera/mouse operation available without inventing actions.
_SAFE_DEFAULTS = {
    "profile_name": "default",
    "camera": {"index": 0, "width": 1280, "height": 720, "fps": 30},
    "gestures": {"sensitivity": 0.7, "cooldown_ms": 500, "smoothing": 2,
                 "hold_time_ms": 300, "base_hand_size": 1.0},
    "ui": {"theme": "dark", "color_theme": "blue"},
    "mappings": {"GENERAL": {}, "MEDIA": {}, "DRAW": {}},
    "calibration": {"confidence_threshold": 50.0, "hand_size_baseline": 1.0,
                    "pointer_extension_ratio": 0.4, "pinch_enter_threshold": 0.45,
                    "pinch_release_threshold": 0.6, "two_finger_max_spacing": 0.2,
                    "victory_min_spacing": 0.35, "active_roi_margin": 0.2},
}

_NUMBER_RULES = {
    "camera": {"index": (0, 255, True), "width": (1, 7680, True),
               "height": (1, 4320, True), "fps": (1, 240, True)},
    "gestures": {"sensitivity": (0.1, 1, False), "smoothing": (1, 20, True),
                 "hold_time_ms": (1, 10000, True), "cooldown_ms": (0, 10000, True),
                 "base_hand_size": (0.000001, 1, False)},
    "calibration": {"confidence_threshold": (0, 100, False),
                    "hand_size_baseline": (0.000001, 1, False),
                    "pointer_extension_ratio": (0, 2, False),
                    "pinch_enter_threshold": (0.001, 5, False),
                    "pinch_release_threshold": (0.001, 5, False),
                    "two_finger_max_spacing": (0.001, 5, False),
                    "victory_min_spacing": (0.001, 5, False),
                    "active_roi_margin": (0, 0.49, False)},
}


def validate_settings(settings: dict) -> None:
    """Reject unsafe known values while retaining additional compatible keys."""
    if not isinstance(settings, dict):
        raise ValueError("Profile must be a JSON object.")
    for section in ("camera", "gestures", "calibration", "ui", "mappings"):
        if not isinstance(settings.get(section), dict):
            raise ValueError(f"{section} must be an object.")
    for section, rules in _NUMBER_RULES.items():
        for name, (minimum, maximum, integer) in rules.items():
            value = settings[section].get(name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not minimum <= value <= maximum
                    or (integer and not isinstance(value, int))):
                raise ValueError(f"{section}.{name} must be a finite {'integer' if integer else 'number'} from {minimum} to {maximum}.")
    calibration = settings["calibration"]
    if calibration["pinch_enter_threshold"] >= calibration["pinch_release_threshold"]:
        raise ValueError("Pinch release threshold must exceed the enter threshold.")
    if calibration["two_finger_max_spacing"] >= calibration["victory_min_spacing"]:
        raise ValueError("Victory spacing must exceed Two Fingers spacing.")
    for mode, mappings in settings["mappings"].items():
        if not isinstance(mappings, dict):
            raise ValueError(f"mappings.{mode} must be an object.")
        if any(not isinstance(name, str) or (action is not None and not isinstance(action, str))
               for name, action in mappings.items()):
            raise ValueError(f"mappings.{mode} must map gesture names to action names or null.")
    for name in ("theme", "color_theme"):
        if not isinstance(settings["ui"].get(name), str):
            raise ValueError(f"ui.{name} must be a string.")


def validate_profile_name(name: str) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    Allowed: letters, numbers, spaces, underscores, hyphens, 1–64 chars.
    """
    if not isinstance(name, str) or not name:
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

    def __init__(self, profiles_dir: Path | None = None):
        self.profiles_dir = profiles_dir if profiles_dir is not None else PROFILES_DIR
        self.current_profile = "default"
        self.settings: dict = self._get_default_settings()
        self.callbacks: list = []
        self.last_error: str | None = None
        # Startup can recover in memory without replacing an unreadable profile.
        self.load_profile(self.current_profile, create_missing=False)

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
                    defaults = self._merge_dicts(deepcopy(_SAFE_DEFAULTS), json.load(f))
                validate_settings(defaults)
                return defaults
            except Exception as e:
                logger.error(f"Failed to load defaults.json: {e}")
        return deepcopy(_SAFE_DEFAULTS)

    def _get_profile_path(self, profile_name: str) -> Path:
        # Path is always constructed internally — never from raw user input after validation
        return self.profiles_dir / f"{profile_name}.json"

    def get_all_profiles(self) -> list[str]:
        profiles = [f.stem for f in self.profiles_dir.glob("*.json")]
        if "default" not in profiles:
            profiles.append("default")
        return sorted(set(profiles))

    def load_profile(self, profile_name: str, *, create_missing: bool = True) -> bool:
        # F-09 FIX: validate before building path
        valid, reason = validate_profile_name(profile_name)
        if not valid:
            self.last_error = reason
            logger.error(f"Refused to load profile '{profile_name}': {reason}")
            return False

        path = self._get_profile_path(profile_name)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = self._merge_dicts(self._get_default_settings(), data)
                validate_settings(merged)
                merged["profile_name"] = profile_name
                self.settings.clear()
                self.settings.update(merged)
                self.current_profile = profile_name
                self.last_error = None
                self.apply_settings()
                return True
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Failed to load profile '{profile_name}': {e}")
                return False

        # Profile doesn't exist — create with defaults
        previous_settings, previous_profile = deepcopy(self.settings), self.current_profile
        self.settings.clear()
        self.settings.update(self._get_default_settings())
        self.settings["profile_name"] = profile_name
        self.current_profile = profile_name
        if create_missing and not self.save_profile():
            self.settings.clear()
            self.settings.update(previous_settings)
            self.current_profile = previous_profile
            return False
        self.last_error = None
        self.apply_settings()
        return True

    def save_profile(self) -> bool:
        valid, reason = validate_profile_name(self.current_profile)
        if not valid:
            self.last_error = reason
            logger.error(f"Refused to save profile '{self.current_profile}': {reason}")
            return False

        path = self._get_profile_path(self.current_profile)
        # Atomic write: write to temp file then rename
        tmp_path = path.with_suffix(".tmp")
        try:
            validate_settings(self.settings)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, allow_nan=False)
            tmp_path.replace(path)
            self.apply_settings()
            self.last_error = None
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Failed to save profile '{self.current_profile}': {e}")
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
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
        if not isinstance(user_dict, dict):
            raise ValueError("Profile must be a JSON object.")
        result = deepcopy(default_dict)
        for k, v in user_dict.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._merge_dicts(result[k], v)
            else:
                result[k] = v
        return result


# Global singleton
settings_manager = SettingsManager()
