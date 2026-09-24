"""
Tests for SettingsManager.

F-09: Covers profile name sanitization (allowlist, reserved name guard, path traversal).
"""

import unittest
import shutil
from src.settings_manager import SettingsManager, validate_profile_name, PROFILES_DIR


class TestSettingsManager(unittest.TestCase):
    def setUp(self):
        # Use a clean test directory isolated from real profiles
        self.test_dir = PROFILES_DIR.parent / "test_profiles"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.sm = SettingsManager()
        self.sm.profiles_dir = self.test_dir

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    # ── Basic functionality ───────────────────────────────────────────────────

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

    # ── F-09: Profile name sanitization ──────────────────────────────────────

    def test_validate_profile_name_valid(self):
        """Valid profile names must pass validation."""
        valid = [
            "default", "user1", "My Profile", "work-setup",
            "profile_2", "A" * 64,
        ]
        for name in valid:
            ok, reason = validate_profile_name(name)
            self.assertTrue(ok, f"Expected '{name}' to be valid. Reason: {reason}")

    def test_validate_profile_name_empty(self):
        ok, reason = validate_profile_name("")
        self.assertFalse(ok)
        self.assertTrue(len(reason) > 0)

    def test_validate_profile_name_too_long(self):
        ok, reason = validate_profile_name("A" * 65)
        self.assertFalse(ok)

    def test_validate_profile_name_path_traversal(self):
        """Path traversal attempts must be rejected (F-09)."""
        dangerous = [
            "../secrets",
            "../../windows",
            "name/with/slash",
            "name\\backslash",
        ]
        for name in dangerous:
            ok, reason = validate_profile_name(name)
            self.assertFalse(ok, f"Expected '{name!r}' to fail but got ok=True")

    def test_validate_profile_name_reserved_windows(self):
        """Windows reserved filenames must be rejected (F-09)."""
        reserved = ["CON", "PRN", "NUL", "COM1", "LPT9"]
        for name in reserved:
            ok, reason = validate_profile_name(name)
            self.assertFalse(ok, f"Expected '{name}' to be rejected")

    def test_load_profile_rejects_path_traversal(self):
        """load_profile must refuse to load a path-traversal profile name (F-09)."""
        # Should return False without creating any file
        result = self.sm.load_profile("../evil")
        self.assertFalse(result)
        # No files should have been created in parent dir
        evil_path = self.test_dir.parent / "evil.json"
        self.assertFalse(
            evil_path.exists(),
            f"Path traversal created a file at {evil_path}!"
        )

    def test_delete_default_profile_prevented(self):
        """Deleting the 'default' profile must always return False."""
        result = self.sm.delete_profile("default")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
