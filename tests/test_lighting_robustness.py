import pytest
import numpy as np
from src.gesture_classifier import GestureClassifier
from src.models import Landmark

def create_base_two_fingers():
    # Base "Two Fingers" gesture (index and middle extended, others closed)
    # y = 0 is top, y = 1 is bottom
    return [
        Landmark(0, 500, 500, 0.5, 0.8, 0.0), # wrist
        Landmark(1, 400, 500, 0.4, 0.7, 0.0), # thumb
        Landmark(2, 300, 500, 0.3, 0.7, 0.0),
        Landmark(3, 300, 500, 0.3, 0.6, 0.0),
        Landmark(4, 400, 500, 0.4, 0.6, 0.0), # thumb tip
        Landmark(5, 450, 500, 0.45, 0.5, 0.0), # index mcp
        Landmark(6, 450, 500, 0.45, 0.4, 0.0), 
        Landmark(7, 450, 500, 0.45, 0.3, 0.0),
        Landmark(8, 450, 500, 0.45, 0.2, 0.0), # index tip
        Landmark(9, 500, 500, 0.5, 0.5, 0.0), # middle mcp
        Landmark(10, 500, 500, 0.5, 0.4, 0.0),
        Landmark(11, 500, 500, 0.5, 0.3, 0.0),
        Landmark(12, 500, 500, 0.5, 0.2, 0.0), # middle tip
        Landmark(13, 650, 500, 0.65, 0.5, 0.0), # ring mcp
        Landmark(14, 650, 500, 0.65, 0.6, 0.0),
        Landmark(15, 650, 500, 0.65, 0.55, 0.0),
        Landmark(16, 650, 500, 0.65, 0.5, 0.0), # ring tip (folded)
        Landmark(17, 750, 500, 0.75, 0.5, 0.0), # pinky mcp
        Landmark(18, 750, 500, 0.75, 0.6, 0.0),
        Landmark(19, 750, 500, 0.75, 0.55, 0.0),
        Landmark(20, 750, 500, 0.75, 0.5, 0.0)  # pinky tip (folded)
    ]

def add_noise(landmarks, noise_level=0.02):
    noisy_landmarks = []
    for lm in landmarks:
        noisy_landmarks.append(Landmark(
            id=lm.id, pixel_x=lm.pixel_x, pixel_y=lm.pixel_y,
            x=lm.x + np.random.normal(0, noise_level),
            y=lm.y + np.random.normal(0, noise_level),
            z=lm.z + np.random.normal(0, noise_level)
        ))
    return noisy_landmarks

def test_lighting_robustness_low_noise():
    classifier = GestureClassifier(hold_time_ms=100) # 100 ms hold time
    base_lms = create_base_two_fingers()
    
    import time
    from unittest.mock import patch
    
    with patch('time.time') as mock_time:
        mock_time.return_value = 1000.0
        
        # 5 frames of low noise (good lighting) over 150ms
        stable_results = []
        for i in range(5):
            mock_time.return_value = 1000.0 + (i * 0.03) # 30ms per frame
            lms = add_noise(base_lms, noise_level=0.01)
            result = classifier.classify([{"landmarks": lms, "score": 90.0}])
            stable, raw, conf = result.gesture, result.raw_gesture, result.confidence
            print(f"Frame {i}: raw={raw}, stable={stable}, conf={conf}")
            stable_results.append(stable)
            
        # By frame 5 (after 120ms), it should be "Two Fingers"
        assert stable_results[-1] == "Two Fingers"

def test_lighting_robustness_high_noise():
    classifier = GestureClassifier(hold_time_ms=200) # 200 ms hold time
    base_lms = create_base_two_fingers()
    
    import time
    from unittest.mock import patch
    
    with patch('time.time') as mock_time:
        mock_time.return_value = 1000.0
        spurious_gestures = set()
        
        # Simulate bad lighting (high noise) over 300ms.
        for i in range(20):
            mock_time.return_value = 1000.0 + (i * 0.015) # 15ms per frame
            lms = add_noise(base_lms, noise_level=0.05) # 5% screen size noise is HUGE
            result = classifier.classify([{"landmarks": lms, "score": 90.0}])
            stable, raw, conf = result.gesture, result.raw_gesture, result.confidence
        
        # It might be "None" or "Unknown" due to noise breaking the kinematics,
        # or it might be "Two Fingers".
        # It should NEVER randomly trigger "Closed Fist" or "Peace" stably.
        if stable not in ["None", "Unknown", "Two Fingers"]:
            spurious_gestures.add(stable)
            
    assert len(spurious_gestures) == 0, f"High noise caused spurious stable gestures: {spurious_gestures}"
