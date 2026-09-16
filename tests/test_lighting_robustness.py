import pytest
import numpy as np
from src.gesture_classifier import GestureClassifier
from src.models import Landmark

def create_base_two_fingers():
    # Base "Two Fingers" gesture (index and middle extended, others closed)
    # y = 0 is top, y = 1 is bottom
    return [
        Landmark(id=0, pixel_x=500, pixel_y=500, x=0.5, y=0.8, z=0.0), # wrist
        Landmark(id=1, pixel_x=400, pixel_y=500, x=0.4, y=0.7, z=0.0), # thumb
        Landmark(id=2, pixel_x=300, pixel_y=500, x=0.3, y=0.7, z=0.0),
        Landmark(id=3, pixel_x=300, pixel_y=500, x=0.3, y=0.6, z=0.0),
        Landmark(id=4, pixel_x=400, pixel_y=500, x=0.4, y=0.6, z=0.0), # thumb tip
        Landmark(id=5, pixel_x=450, pixel_y=500, x=0.45, y=0.5, z=0.0), # index mcp
        Landmark(id=6, pixel_x=450, pixel_y=500, x=0.45, y=0.4, z=0.0), 
        Landmark(id=7, pixel_x=450, pixel_y=500, x=0.45, y=0.3, z=0.0),
        Landmark(id=8, pixel_x=450, pixel_y=500, x=0.45, y=0.2, z=0.0), # index tip
        Landmark(id=9, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0), # middle mcp
        Landmark(id=10, pixel_x=500, pixel_y=500, x=0.5, y=0.4, z=0.0),
        Landmark(id=11, pixel_x=500, pixel_y=500, x=0.5, y=0.3, z=0.0),
        Landmark(id=12, pixel_x=500, pixel_y=500, x=0.5, y=0.2, z=0.0), # middle tip
        Landmark(id=13, pixel_x=650, pixel_y=500, x=0.65, y=0.5, z=0.0), # ring mcp
        Landmark(id=14, pixel_x=650, pixel_y=500, x=0.65, y=0.6, z=0.0),
        Landmark(id=15, pixel_x=650, pixel_y=500, x=0.65, y=0.55, z=0.0),
        Landmark(id=16, pixel_x=650, pixel_y=500, x=0.65, y=0.5, z=0.0), # ring tip (folded)
        Landmark(id=17, pixel_x=750, pixel_y=500, x=0.75, y=0.5, z=0.0), # pinky mcp
        Landmark(id=18, pixel_x=750, pixel_y=500, x=0.75, y=0.6, z=0.0),
        Landmark(id=19, pixel_x=750, pixel_y=500, x=0.75, y=0.55, z=0.0),
        Landmark(id=20, pixel_x=750, pixel_y=500, x=0.75, y=0.5, z=0.0)  # pinky tip (folded)
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
