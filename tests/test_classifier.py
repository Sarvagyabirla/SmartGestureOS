import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gesture_classifier import GestureClassifier
from src.models import Landmark

def test_open_palm():
    classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    lms_list = [[i, 0, 0] for i in range(21)]
    
    # Wrist and Palm Center
    lms_list[0] = [0, 50, 150]
    lms_list[5] = [5, 50, 100]
    lms_list[9] = [9, 50, 100]
    lms_list[13] = [13, 50, 100]
    lms_list[17] = [17, 50, 100]
    
    # Thumb open
    lms_list[1] = [1, 40, 120]
    lms_list[2] = [2, 50, 100]
    lms_list[3] = [3, 60, 100]
    lms_list[4] = [4, 70, 100]
    
    # Fingers up
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[tip] = [tip, 50, 10]
        lms_list[pip] = [pip, 50, 100]
        
    lms_list_3d = [Landmark(id=lm[0], pixel_x=int(lm[1]), pixel_y=int(lm[2]), x=lm[1]/100.0, y=lm[2]/100.0, z=0.0) for lm in lms_list]
    hands_data = [{'landmarks': lms_list_3d, 'score': 99}]
    
    # Feed 3 times for history buffer
    classifier.classify(hands_data)
    classifier.classify(hands_data)
    result = classifier.classify(hands_data)
    res, raw, score = result.gesture, result.raw_gesture, result.confidence
    assert res == "Open Palm"
    assert score > 60
    
def test_closed_fist():
    classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    lms_list = [[i, 0, 0] for i in range(21)]
        
    # Wrist and Palm Center
    lms_list[0] = [0, 50, 150]
    lms_list[5] = [5, 30, 100]
    lms_list[9] = [9, 50, 100]
    
    # Thumb closed
    lms_list[1] = [1, 40, 120]
    lms_list[2] = [2, 50, 100]
    lms_list[17] = [17, 100, 100]
    lms_list[3] = [3, 60, 100]
    lms_list[4] = [4, 70, 100]

    # Fingers down
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[pip] = [pip, 50, 120]
        lms_list[tip] = [tip, 50, 90]
        
    lms_list_3d = [Landmark(id=lm[0], pixel_x=int(lm[1]), pixel_y=int(lm[2]), x=lm[1]/100.0, y=lm[2]/100.0, z=0.0) for lm in lms_list]
    hands_data = [{'landmarks': lms_list_3d, 'score': 99}]
    
    classifier.classify(hands_data)
    classifier.classify(hands_data)
    result = classifier.classify(hands_data)
    res, raw, score = result.gesture, result.raw_gesture, result.confidence
    assert res == "Closed Fist"
    assert score >= 50
    
def test_invalid_landmarks():
    classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    result = classifier.classify([])
    assert result.confidence < 20
    
    result2 = classifier.classify([{'landmarks':[Landmark(0,0,0,0.0,0.0,0.0)], 'score':0}])
    assert result2.confidence < 30

def test_rotation_resilience():
    # If the hand is upside down, the basic y-coordinate check fails.
    # Our new vector logic should handle it.
    classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    lms_list = [[i, 0, 0] for i in range(21)]
    
    # Wrist (top) and Palm Center
    lms_list[0] = [0, 50, 10]
    lms_list[5] = [5, 50, 50]
    lms_list[9] = [9, 50, 50]
    lms_list[13] = [13, 50, 50]
    lms_list[17] = [17, 50, 50]
    
    # Thumb open (pointing right)
    lms_list[17] = [17, 100, 50]
    lms_list[3] = [3, 20, 50]
    lms_list[2] = [2, 50, 50]
    lms_list[4] = [4, 10, 100] 
    
    # Fingers up (pointing DOWN)
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[tip] = [tip, 50, 150]
        lms_list[pip] = [pip, 50, 50]
        
    lms_list_3d = [Landmark(id=lm[0], pixel_x=int(lm[1]), pixel_y=int(lm[2]), x=lm[1]/100.0, y=lm[2]/100.0, z=0.0) for lm in lms_list]
    hands_data = [{'landmarks': lms_list_3d, 'score': 99}]
    
    classifier.classify(hands_data)
    classifier.classify(hands_data)
    result = classifier.classify(hands_data)
    assert result.gesture == "Open Palm"

def test_jitter_filtering():
    # Test that a single frame of a different gesture doesn't break the stable gesture
    # We need hold_time > 0 to test stability filtering
    classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=300)
    
    # Create Open Palm hands data
    lms_list = [[i, 0, 0] for i in range(21)]
    lms_list[0] = [0, 50, 150]
    lms_list[5] = [5, 50, 100]
    lms_list[9] = [9, 50, 100]
    lms_list[13] = [13, 50, 100]
    lms_list[17] = [17, 50, 100]
    lms_list[1] = [1, 40, 120]
    lms_list[2] = [2, 50, 100]
    lms_list[3] = [3, 60, 100]
    lms_list[4] = [4, 70, 50]
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[tip] = [tip, 50, 10]; lms_list[pip] = [pip, 50, 100]
    
    palm_data = [{'landmarks': [Landmark(id=lm[0], pixel_x=int(lm[1]), pixel_y=int(lm[2]), x=lm[1]/100.0, y=lm[2]/100.0, z=0.0) for lm in lms_list], 'score': 99}]
    
    # Create Closed Fist hands data (noise)
    fist_list = list(lms_list)
    fist_list[1] = [1, 40, 120]
    fist_list[2] = [2, 50, 100]
    fist_list[3] = [3, 60, 100]
    fist_list[4] = [4, 70, 100]
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        fist_list[pip] = [pip, 50, 120]
        fist_list[tip] = [tip, 50, 90]
    fist_data = [{'landmarks': [Landmark(id=lm[0], pixel_x=int(lm[1]), pixel_y=int(lm[2]), x=lm[1]/100.0, y=lm[2]/100.0, z=0.0) for lm in fist_list], 'score': 99}]
    
    # Hold Open Palm for 10 frames (simulate 333ms at 30fps)
    import time
    for _ in range(10):
        result = classifier.classify(palm_data)
        time.sleep(0.04) # 40ms per frame
        
    assert result.gesture == "Open Palm"
    
    # Inject 1 frame of Closed Fist
    result = classifier.classify(fist_data)
    # The result should STILL be Open Palm because hold_time filters out single-frame anomalies
    assert result.gesture == "Open Palm"
