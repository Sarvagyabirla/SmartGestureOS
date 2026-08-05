from src.settings_manager import settings_manager

SETTINGS = settings_manager.settings

def save_settings():
    settings_manager.save_profile()
