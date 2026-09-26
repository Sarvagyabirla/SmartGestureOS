import unittest
import numpy as np
import time
from unittest.mock import patch
from src.utils import OneEuroFilter, PointSmoother, get_angle, cubic_bezier_interpolation
from src.gesture_classifier import GestureClassifier
from src.gesture_mapper import GestureMapper
from src.models import Landmark

class TestUtils(unittest.TestCase):
    def test_one_euro_filter(self):
        filter_x = OneEuroFilter(t0=1.0, x0=0.0, dx0=0.0, min_cutoff=0.004, beta=0.7, d_cutoff=1.0)
        
        # Test that steady values have no lag
        for i in range(10):
            res = filter_x(1.0 + i*0.033, 10.0)
        self.assertAlmostEqual(res, 10.0, places=1)
        
        # Test smoothing of large jump
        res = filter_x(1.0 + 11*0.033, 100.0)
        self.assertTrue(10.0 < res < 100.0) # Should not immediately reach 100

    def test_point_smoother(self):
        smoother = PointSmoother(min_cutoff=0.1, beta=0.5)
        for i in range(10):
            x, y = smoother.update(i*0.033, 10.0, 20.0)
        self.assertAlmostEqual(x, 10.0, places=1)
        self.assertAlmostEqual(y, 20.0, places=1)
        
    def test_get_angle(self):
        p1, p2, p3 = np.array([1, 0]), np.array([0, 0]), np.array([0, 1])
        angle = get_angle(p1, p2, p3)
        self.assertAlmostEqual(angle, 90.0, places=1)

class TestGestureClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = GestureClassifier(confidence_threshold=50)  # F-12: hold_time_ms removed
        
    def create_mock_hand(self, thumb_up=False, index_up=False):
        # Create a mock 21-point hand
        lms = [Landmark(id=i, pixel_x=500, pixel_y=900, x=0.5, y=0.9, z=0.0) for i in range(21)]
        
        # Set wrist
        lms[0] = Landmark(0, 500, 900, 0.5, 0.9, 0)
        
        # Default folded fingers
        for f_idx in range(5):
            mcp_id = [2, 5, 9, 13, 17][f_idx]
            pip_id = [3, 6, 10, 14, 18][f_idx]
            tip_id = [4, 8, 12, 16, 20][f_idx]
            lms[mcp_id] = Landmark(mcp_id, 500, 500, 0.5, 0.5, 0)
            lms[pip_id] = Landmark(pip_id, 500, 600, 0.5, 0.6, 0) # PIP extended
            lms[tip_id] = Landmark(tip_id, 500, 500, 0.5, 0.5, 0) # TIP folded back
        
        # Thumb
        if thumb_up:
            lms[4] = Landmark(4, 900, 500, 0.9, 0.5, 0) # Extended tip
            lms[3] = Landmark(3, 700, 600, 0.7, 0.6, 0) # Extended ip
            lms[17] = Landmark(17, 200, 500, 0.2, 0.5, 0) # Pinky mcp
        
        if index_up:
            lms[8] = Landmark(8, 500, 100, 0.5, 0.1, 0) # Tip
            lms[6] = Landmark(6, 500, 300, 0.5, 0.3, 0) # Pip
            lms[5] = Landmark(5, 500, 500, 0.5, 0.5, 0) # Mcp
            
        return [{'landmarks': lms, 'score': 90}]

    def test_classify_pointing(self):
        hand = self.create_mock_hand(thumb_up=False, index_up=True)
        # Pump the classifier to overcome confidence EMA and time hold
        gesture = "Unknown"
        conf = 0
        for _ in range(10):
            result = self.classifier.classify(hand)
            gesture = result.gesture
            conf = result.confidence
            time.sleep(0.01)
            
        self.assertEqual(gesture, "Pointing")
        self.assertGreater(conf, 30)

class TestGestureMapper(unittest.TestCase):
    def setUp(self):
        # VirtualMouse retains the fake user32 after these patches end.
        # Keep actual mouse/engine reset logic without desktop input or speech.
        with (
            patch("src.virtual_mouse.ctypes.windll"),
            patch("src.gesture_mapper.VolumeController"),
            patch("src.gesture_mapper.BrightnessController"),
            patch("src.gesture_mapper.FeedbackController"),
            patch("src.settings_manager.settings_manager.register_callback"),
        ):
            self.mapper = GestureMapper(1920, 1080)
        
    def test_mode_switching(self):
        # Initial mode
        self.assertEqual(self.mapper.mode, "GENERAL")
        
        # Test cycle_mode instead of gesture processing for unit test
        self.mapper.cycle_mode()
        self.assertEqual(self.mapper.mode, "MEDIA")
        
        self.mapper.cycle_mode()
        self.assertEqual(self.mapper.mode, "DRAW")
        
        self.mapper.cycle_mode()
        self.assertEqual(self.mapper.mode, "GENERAL")
        
    def test_execute_action_mapping(self):
        # We can't easily test the side effects of volume/chrome/etc in a headless test,
        # but we CAN verify that the methods exist and don't throw AttributeError
        # by checking if the action map contains callable methods
        
        # Call it with an invalid action, should return None
        self.assertIsNone(self.mapper.execute_action("non_existent_action"))
        
        # Test just a safe one like switch_mode
        initial_mode = self.mapper.mode
        res = self.mapper.execute_action("switch_mode")
        self.assertEqual(res, "Executed: switch_mode")
        self.assertNotEqual(self.mapper.mode, initial_mode)

if __name__ == "__main__":
    unittest.main()
