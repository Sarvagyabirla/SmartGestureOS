"""
Tests for GestureTrainer.

F-37: Covers gesture name sanitization (allowlist, built-in guard, sample limit).
"""

import unittest
import numpy as np
import shutil
from src.gesture_trainer import GestureTrainer, validate_gesture_name
from src.paths import CUSTOM_GESTURES_DIR


class TestGestureTrainer(unittest.TestCase):
    def setUp(self):
        self.trainer = GestureTrainer()
        self.test_dir = CUSTOM_GESTURES_DIR.parent / "test_models"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.trainer.models_dir = self.test_dir

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def create_dummy_landmarks(self, scale=1.0):
        """Create 21 landmarks as list-of-4-element-lists [id, x, y, z]."""
        return [[i, i * scale, i * scale, i * scale] for i in range(21)]

    # ── Normalization ─────────────────────────────────────────────────────────

    def test_normalization(self):
        """Scale-normalized landmarks from different hand sizes must be identical."""
        lms1 = self.create_dummy_landmarks(scale=1.0)
        lms2 = self.create_dummy_landmarks(scale=5.0)
        norm1 = self.trainer._normalize_landmarks(lms1)
        norm2 = self.trainer._normalize_landmarks(lms2)
        np.testing.assert_array_almost_equal(norm1, norm2)

    # ── Classification ────────────────────────────────────────────────────────

    def test_classification(self):
        """add_sample then classify should find exact match."""
        lms = self.create_dummy_landmarks(scale=1.0)
        ok, msg = self.trainer.add_sample("Diagonal", lms)
        self.assertTrue(ok, f"add_sample failed: {msg}")

        name, dist = self.trainer.classify(lms)
        self.assertEqual(name, "Diagonal")
        self.assertLess(dist, 0.01)

        # Scale-invariant: different hand size must also match
        lms_large = self.create_dummy_landmarks(scale=10.0)
        name, dist = self.trainer.classify(lms_large)
        self.assertEqual(name, "Diagonal")
        self.assertLess(dist, 0.01)

    # ── Save / Load ───────────────────────────────────────────────────────────

    def test_save_load(self):
        """Gestures saved to disk must survive round-trip."""
        lms = self.create_dummy_landmarks()
        ok, _ = self.trainer.add_sample("MyPose", lms)
        self.assertTrue(ok)
        self.trainer.save_models()

        trainer2 = GestureTrainer()
        trainer2.models_dir = self.test_dir
        trainer2.load_models()

        self.assertIn("MyPose", trainer2.custom_gestures)
        self.assertEqual(len(trainer2.custom_gestures["MyPose"]), 1)

    # ── F-37: Gesture name sanitization ──────────────────────────────────────

    def test_validate_gesture_name_valid(self):
        """Valid names must pass validate_gesture_name."""
        valid_names = ["MyPose", "Pose 1", "custom-pose", "my_pose", "A" * 32]
        for name in valid_names:
            ok, reason = validate_gesture_name(name)
            self.assertTrue(ok, f"Expected '{name}' to be valid, got: {reason}")

    def test_validate_gesture_name_invalid(self):
        """Invalid names must fail validate_gesture_name."""
        invalid_names = [
            "",                        # empty
            "A" * 33,                  # too long
            "../etc/passwd",           # path traversal
            "name\x00null",           # null byte
            "pose<script>",           # HTML injection attempt
        ]
        for name in invalid_names:
            ok, reason = validate_gesture_name(name)
            self.assertFalse(ok, f"Expected '{name!r}' to be invalid")
            self.assertTrue(len(reason) > 0)

    def test_add_sample_rejects_builtin_names(self):
        """Built-in gesture names must be rejected by add_sample (F-37)."""
        builtin_names = ["Pinch", "Open Palm", "Victory", "Unknown", "None"]
        lms = self.create_dummy_landmarks()
        for name in builtin_names:
            ok, reason = self.trainer.add_sample(name, lms)
            self.assertFalse(ok, f"Expected built-in gesture '{name}' to be rejected")
            self.assertIn("built-in", reason.lower())

    def test_add_sample_rejects_path_traversal(self):
        """Path traversal gesture names must be rejected (F-37)."""
        dangerous_names = [
            "../evil",
            "../../windows/system32",
            "name/with/slash",
        ]
        lms = self.create_dummy_landmarks()
        for name in dangerous_names:
            ok, reason = self.trainer.add_sample(name, lms)
            self.assertFalse(ok, f"Expected '{name!r}' to be rejected, but got ok=True")

    def test_add_sample_enforces_limit(self):
        """add_sample must reject after MAX_SAMPLES_PER_GESTURE is reached (F-37)."""
        from src.gesture_trainer import _MAX_SAMPLES_PER_GESTURE
        lms = self.create_dummy_landmarks()
        for i in range(_MAX_SAMPLES_PER_GESTURE):
            ok, msg = self.trainer.add_sample("LimitTest", lms)
            self.assertTrue(ok, f"Sample {i+1} should succeed: {msg}")

        # Next one should fail
        ok, msg = self.trainer.add_sample("LimitTest", lms)
        self.assertFalse(ok)
        self.assertIn("Maximum", msg)


if __name__ == "__main__":
    unittest.main()
