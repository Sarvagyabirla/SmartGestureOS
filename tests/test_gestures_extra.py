import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gesture_classifier import GestureClassifier

def create_hand(fingers_up):
    # fingers_up is a list of 5 ints
    lms = [[i, 0, 0] for i in range(21)]
    # Wrist and Palm
    lms[0] = [0, 50, 150]
    lms[5] = [5, 30, 100]
    lms[9] = [9, 50, 100]
    lms[17] = [17, 80, 100]
    
    # Thumb
    if fingers_up[0]:
        lms[3] = [3, 100, 50] # IP 
        lms[4] = [4, 130, 50] # Tip further from pinky base (17) than IP
    else:
        lms[3] = [3, 40, 110]
        lms[4] = [4, 60, 110] # Folded over palm, close to pinky base
        
    # Index
    if fingers_up[1]:
        lms[6] = [6, 30, 80]
        lms[8] = [8, 30, 50]
    else:
        lms[6] = [6, 30, 110]
        lms[8] = [8, 30, 140]
        
    # Middle
    if fingers_up[2]:
        lms[10] = [10, 50, 80]
        lms[12] = [12, 50, 50]
    else:
        lms[10] = [10, 50, 110]
        lms[12] = [12, 50, 140]
        
    # Ring
    if fingers_up[3]:
        lms[14] = [14, 65, 80]
        lms[16] = [16, 65, 50]
    else:
        lms[14] = [14, 65, 110]
        lms[16] = [16, 65, 140]
        
    # Pinky
    if fingers_up[4]:
        lms[18] = [18, 80, 80]
        lms[20] = [20, 80, 50]
    else:
        lms[18] = [18, 80, 110]
        lms[20] = [20, 80, 140]
        
    lms_3d = [[lm[0], lm[1], lm[2], lm[1]/100, lm[2]/100, 0] for lm in lms]
    return [{'landmarks': lms_3d, 'score': 99}]

def check(fingers, expected):
    c = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    # Pump to get past hold time
    for _ in range(5):
        c.classify(create_hand(fingers))
    res, _ = c.classify(create_hand(fingers))
    assert res == expected, f"Expected {expected}, got {res} for fingers {fingers}"

def test_gestures():
    check([0, 0, 0, 0, 0], "Closed Fist")
    check([0, 1, 1, 1, 1], "Four Fingers")
    check([1, 0, 0, 0, 1], "Call Me")
    check([1, 1, 1, 1, 1], "Open Palm")
    check([1, 0, 0, 0, 0], "Thumb Up")
    check([0, 1, 0, 0, 0], "Pointing")
    check([1, 1, 0, 0, 0], "Pointing")
    check([0, 1, 1, 0, 0], "Victory")
    # Pinch test requires tight thumb and index
    
def test_crossed_fingers():
    h = create_hand([0, 1, 1, 0, 0])[0]
    # Cross index and middle fingers and make them close together
    h['landmarks'][8] = [8, 41, h['landmarks'][8][2], 0.41, h['landmarks'][8][4], 0]
    h['landmarks'][12] = [12, 39, h['landmarks'][12][2], 0.39, h['landmarks'][12][4], 0]
    
    c = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    for _ in range(5):
        c.classify([h])
    res, _ = c.classify([h])
    assert res == "Crossed Fingers", f"Got {res}"
