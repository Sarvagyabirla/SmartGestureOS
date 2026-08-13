import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILES_DIR = BASE_DIR / "profiles"

class SettingsManager:
    def __init__(self):
        self.profiles_dir = PROFILES_DIR
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.current_profile = "default"
        self.settings = {}
        self.load_profile(self.current_profile)
        
    def _get_default_settings(self):
        return {
            "profile_name": "default",
            "camera": {"index": 0, "width": 1280, "height": 720, "fps": 30},
            "gestures": {"sensitivity": 0.7, "cooldown": 0.5, "smoothing": 5, "hold_time_ms": 300},
            "ui": {"theme": "dark", "color_theme": "blue"},
            "mappings": {
                "GENERAL": {
                    "Victory": "open_vscode",
                    "Rock On": "open_chrome",
                    "Four Fingers": "screenshot",
                    "Thumb Up": "volume_up",
                    "Thumb Down": "volume_down",
                    "Open Palm": "task_view",
                    "Closed Fist": "show_desktop",
                    "Crossed Fingers": "lock_pc",
                    "Call Me": "switch_mode"
                },
                "MEDIA": {
                    "Pinch": "play_pause",
                    "Victory": "next_track",
                    "Three Fingers": "prev_track",
                    "Closed Fist": "mute",
                    "Call Me": "switch_mode"
                },
                "DRAW": {
                    "Victory": "undo",
                    "Three Fingers": "redo",
                    "Four Fingers": "save_drawing",
                    "Thumb Up": "cycle_color",
                    "Thumb Down": "toggle_eraser",
                    "Call Me": "switch_mode"
                }
            },
            "calibration": {
                "hand_size_baseline": 1.0,
                "pointer_extension_ratio": 0.4
            }
        }
        
    def _get_profile_path(self, profile_name):
        return self.profiles_dir / f"{profile_name}.json"
        
    def get_all_profiles(self):
        profiles = []
        for file in self.profiles_dir.glob("*.json"):
            profiles.append(file.stem)
        if "default" not in profiles:
            profiles.append("default")
        return sorted(list(set(profiles)))
        
    def load_profile(self, profile_name):
        path = self._get_profile_path(profile_name)
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    merged = self._merge_dicts(self._get_default_settings(), data)
                    self.settings.clear()
                    self.settings.update(merged)
                    self.current_profile = profile_name
                    return True
            except Exception as e:
                import logging
                logging.error(f"Failed to load profile {profile_name}: {e}")
                
        # If it doesn't exist, create it with defaults
        self.settings.clear()
        self.settings.update(self._get_default_settings())
        self.settings["profile_name"] = profile_name
        self.current_profile = profile_name
        self.save_profile()
        return True
        
    def save_profile(self):
        path = self._get_profile_path(self.current_profile)
        try:
            with open(path, "w") as f:
                json.dump(self.settings, f, indent=4)
            return True
        except Exception as e:
            import logging
            logging.error(f"Failed to save profile {self.current_profile}: {e}")
            return False
            
    def delete_profile(self, profile_name):
        if profile_name == "default":
            return False # Cannot delete default
            
        path = self._get_profile_path(profile_name)
        if path.exists():
            path.unlink()
            if self.current_profile == profile_name:
                self.load_profile("default")
            return True
        return False
        
    def _merge_dicts(self, default_dict, user_dict):
        result = default_dict.copy()
        for k, v in user_dict.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._merge_dicts(result[k], v)
            else:
                result[k] = v
        return result

# Global instance
settings_manager = SettingsManager()
