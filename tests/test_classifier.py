import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gesture_classifier import GestureClassifier

def test_open_palm():
    classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    lms_list = [[i, 0, 0] for i in range(21)]
    
    # Wrist and Palm Center
    lms_list[0] = [0, 50, 150]
    lms_list[5] = [5, 30, 100]
    lms_list[9] = [9, 50, 100]
    
    # Thumb open
    lms_list[17] = [17, 100, 100]
    lms_list[3] = [3, 20, 100]
    lms_list[2] = [2, 50, 100]
    lms_list[4] = [4, 10, 50] 
    
    # Fingers up
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[tip] = [tip, 50, 10]
        lms_list[pip] = [pip, 50, 100]
        
    lms_list_3d = [[lm[0], lm[1], lm[2], lm[1]/100, lm[2]/100, 0] for lm in lms_list]
    hands_data = [{'landmarks': lms_list_3d, 'score': 99}]
    
    # Feed 3 times for history buffer
    classifier.classify(hands_data)
    classifier.classify(hands_data)
    res, score = classifier.classify(hands_data)
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
    lms_list[17] = [17, 100, 100]
    lms_list[3] = [3, 40, 110]
    lms_list[2] = [2, 50, 100]
    lms_list[4] = [4, 80, 110]
    
    # Fingers down
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[tip] = [tip, 50, 140]
        lms_list[pip] = [pip, 50, 100]
        
    lms_list_3d = [[lm[0], lm[1], lm[2], lm[1]/100, lm[2]/100, 0] for lm in lms_list]
    hands_data = [{'landmarks': lms_list_3d, 'score': 99}]
    
    classifier.classify(hands_data)
    classifier.classify(hands_data)
    res, score = classifier.classify(hands_data)
    assert res == "Closed Fist"
    assert score > 60
    
def test_invalid_landmarks():
    classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    _, score = classifier.classify([])
    assert score < 20
    _, score2 = classifier.classify([{'landmarks':[[0,0,0]], 'score':0}])
    assert score2 < 30

def test_rotation_resilience():
    # If the hand is upside down, the basic y-coordinate check fails.
    # Our new vector logic should handle it.
    classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    lms_list = [[i, 0, 0] for i in range(21)]
    
    # Wrist (top) and Palm Center
    lms_list[0] = [0, 50, 10]
    lms_list[5] = [5, 30, 50]
    lms_list[9] = [9, 50, 50]
    
    # Thumb open (pointing right)
    lms_list[17] = [17, 100, 50]
    lms_list[3] = [3, 20, 50]
    lms_list[2] = [2, 50, 50]
    lms_list[4] = [4, 10, 100] 
    
    # Fingers up (pointing DOWN)
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[tip] = [tip, 50, 150]
        lms_list[pip] = [pip, 50, 50]
        
    lms_list_3d = [[lm[0], lm[1], lm[2], lm[1]/100, lm[2]/100, 0] for lm in lms_list]
    hands_data = [{'landmarks': lms_list_3d, 'score': 99}]
    
    classifier.classify(hands_data)
    classifier.classify(hands_data)
    res, score = classifier.classify(hands_data)
    assert res == "Open Palm"

def test_jitter_filtering():
    # Test that a single frame of a different gesture doesn't break the stable gesture
    # We need hold_time > 0 to test stability filtering
    classifier = GestureClassifier(confidence_threshold=50, hold_time_ms=300)
    
    # Create Open Palm hands data
    lms_list = [[i, 0, 0] for i in range(21)]
    lms_list[0] = [0, 50, 150]; lms_list[5] = [5, 30, 100]; lms_list[9] = [9, 50, 100]
    lms_list[17] = [17, 100, 100]; lms_list[3] = [3, 20, 100]; lms_list[2] = [2, 50, 100]; lms_list[4] = [4, 10, 50]
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[tip] = [tip, 50, 10]; lms_list[pip] = [pip, 50, 100]
    
    palm_data = [{'landmarks': [[lm[0], lm[1], lm[2], lm[1]/100, lm[2]/100, 0] for lm in lms_list], 'score': 99}]
    
    # Create Closed Fist hands data (noise)
    fist_list = list(lms_list)
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        fist_list[tip] = [tip, 50, 140]
    fist_data = [{'landmarks': [[lm[0], lm[1], lm[2], lm[1]/100, lm[2]/100, 0] for lm in fist_list], 'score': 99}]
    
    # Hold Open Palm for 10 frames (simulate 333ms at 30fps)
    import time
    for _ in range(10):
        res, _ = classifier.classify(palm_data)
        time.sleep(0.04) # 40ms per frame
        
    assert res == "Open Palm"
    
    # Inject 1 frame of Closed Fist
    res, _ = classifier.classify(fist_data)
    # The result should STILL be Open Palm because hold_time filters out single-frame anomalies
    assert res == "Open Palm"
