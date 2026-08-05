import unittest
import os
import json
import shutil
from src.settings_manager import SettingsManager, PROFILES_DIR

class TestSettingsManager(unittest.TestCase):
    def setUp(self):
        # Create a clean test environment
        self.test_dir = PROFILES_DIR.parent / "test_profiles"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.sm = SettingsManager()
        self.sm.profiles_dir = self.test_dir # override to test dir
        
    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
            
    def test_default_profile_creation(self):
        self.sm.load_profile("default")
        self.assertEqual(self.sm.current_profile, "default")
        self.assertIn("gestures", self.sm.settings)
        self.assertIn("GENERAL", self.sm.settings["mappings"])
        
    def test_custom_profile_save_load(self):
        self.sm.load_profile("user1")
        self.sm.settings["gestures"]["smoothing"] = 10
        self.sm.save_profile()
        
        sm2 = SettingsManager()
        sm2.profiles_dir = self.test_dir
        sm2.load_profile("user1")
        
        self.assertEqual(sm2.settings["gestures"]["smoothing"], 10)
        self.assertEqual(sm2.current_profile, "user1")
        
    def test_get_all_profiles(self):
        self.sm.load_profile("p1")
        self.sm.load_profile("p2")
        
        profiles = self.sm.get_all_profiles()
        self.assertIn("p1", profiles)
        self.assertIn("p2", profiles)
        self.assertIn("default", profiles)
        
if __name__ == "__main__":
    unittest.main()
