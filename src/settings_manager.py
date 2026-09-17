import json
import shutil
from pathlib import Path
from src.paths import RESOURCE_DIR, PROFILES_DIR

class SettingsManager:
    """
    Manages application settings.
    - Active Profile: Saved in profiles/<name>.json (e.g. profiles/default.json). This is the active user profile and where settings are saved.
    - Fallback/Defaults: config/defaults.json is loaded first as a fallback structure. 
    - Active Settings: self.settings contains the merged result.
    """
    def __init__(self):
        self.profiles_dir = PROFILES_DIR
        self.current_profile = "default"
        self.settings = {}
        self.callbacks = []
        self.load_profile(self.current_profile)
        
    def register_callback(self, callback):
        if callback not in self.callbacks:
            self.callbacks.append(callback)
            
    def apply_settings(self):
        for callback in self.callbacks:
            try:
                callback()
            except Exception as e:
                import logging
                logging.error(f"Error in settings callback: {e}")
        
    def _get_default_settings(self):
        defaults_path = RESOURCE_DIR / "config" / "defaults.json"
        if defaults_path.exists():
            try:
                with open(defaults_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                import logging
                logging.error(f"Failed to load authoritative defaults.json: {e}")
        return {"profile_name": "default"}
        
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
                    self.apply_settings()
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
        self.apply_settings()
        return True
        
    def save_profile(self):
        path = self._get_profile_path(self.current_profile)
        try:
            with open(path, "w") as f:
                json.dump(self.settings, f, indent=4)
            self.apply_settings()
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
