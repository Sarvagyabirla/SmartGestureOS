import unittest
import numpy as np
import os
import shutil
from src.gesture_trainer import GestureTrainer
from src.paths import CUSTOM_GESTURES_DIR

class TestGestureTrainer(unittest.TestCase):
    def setUp(self):
        self.trainer = GestureTrainer()
        self.test_dir = CUSTOM_GESTURES_DIR.parent / "test_models"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        # override for tests
        self.trainer.models_dir = self.test_dir
        
    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
            
    def create_dummy_landmarks(self, scale=1.0):
        # Create a simple 21-landmark array
        lms = []
        for i in range(21):
            lms.append([i, i * scale, i * scale, i * scale])
        return lms
        
    def test_normalization(self):
        lms1 = self.create_dummy_landmarks(scale=1.0)
        lms2 = self.create_dummy_landmarks(scale=5.0) # Larger hand
        
        norm1 = self.trainer._normalize_landmarks(lms1)
        norm2 = self.trainer._normalize_landmarks(lms2)
        
        # Should be completely identical after scale normalization
        np.testing.assert_array_almost_equal(norm1, norm2)
        
    def test_classification(self):
        lms = self.create_dummy_landmarks(scale=1.0)
        self.trainer.add_sample("Diagonal", lms)
        
        # Test exact match
        name, dist = self.trainer.classify(lms)
        self.assertEqual(name, "Diagonal")
        self.assertLess(dist, 0.01)
        
        # Test scaled match (should still be 0 distance due to normalization)
        lms_large = self.create_dummy_landmarks(scale=10.0)
        name, dist = self.trainer.classify(lms_large)
        self.assertEqual(name, "Diagonal")
        self.assertLess(dist, 0.01)
        
    def test_save_load(self):
        lms = self.create_dummy_landmarks()
        self.trainer.add_sample("MyPose", lms)
        self.trainer.save_models()
        
        trainer2 = GestureTrainer()
        trainer2.models_dir = self.test_dir
        trainer2.load_models()
        
        self.assertIn("MyPose", trainer2.custom_gestures)
        self.assertEqual(len(trainer2.custom_gestures["MyPose"]), 1)
        
if __name__ == "__main__":
    unittest.main()
