import unittest
import numpy as np
import time
from src.utils import OneEuroFilter, PointSmoother, get_angle, cubic_bezier_interpolation
from src.gesture_classifier import GestureClassifier
from src.gesture_mapper import GestureMapper

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
        self.classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=50) # Low hold time for tests
        
    def create_mock_hand(self, thumb_up=False, index_up=False):
        # Create a mock 21-point hand
        lms = [[0, 0.5, 0.9, 0, 0, 0]] * 21 # Format: [id, x, y, x3d, y3d, z3d]
        
        # Set wrist
        lms[0] = [0, 0.5, 0.9, 0, 0, 0]
        # Set middle mcp (for hand size)
        lms[9] = [9, 0.5, 0.5, 0, -0.4, 0]
        
        # Thumb
        if thumb_up:
            lms[4] = [4, 0.9, 0.5, 0.4, -0.4, 0] # Extended tip
            lms[3] = [3, 0.7, 0.6, 0.2, -0.3, 0] # Extended ip
            lms[17] = [17, 0.2, 0.5, -0.3, -0.4, 0] # Pinky mcp
        
        if index_up:
            lms[8] = [8, 0.5, 0.1, 0, -0.8, 0] # Tip
            lms[6] = [6, 0.5, 0.3, 0, -0.6, 0] # Pip
            lms[5] = [5, 0.5, 0.5, 0, -0.4, 0] # Mcp
            
        return [{'landmarks': lms, 'score': 0.9}]

    def test_classify_pointing(self):
        hand = self.create_mock_hand(thumb_up=False, index_up=True)
        # Pump the classifier to overcome confidence EMA and time hold
        gesture = "Unknown"
        conf = 0
        for _ in range(10):
            gesture, conf = self.classifier.classify(hand)
            time.sleep(0.01)
            
        self.assertEqual(gesture, "Pointing")
        self.assertGreater(conf, 30)

class TestGestureMapper(unittest.TestCase):
    def setUp(self):
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

if __name__ == "__main__":
    unittest.main()
