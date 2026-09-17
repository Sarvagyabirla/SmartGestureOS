import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gesture_classifier import GestureClassifier
from src.models import Landmark

def create_hand(fingers_up):
    # fingers_up is a list of 5 ints
    lms = [[i, 0, 0] for i in range(21)]
    # Wrist and Palm
    lms[0] = [0, 50, 150]
    lms[5] = [5, 30, 100]
    lms[9] = [9, 50, 100]
    lms[13] = [13, 65, 100]
    lms[17] = [17, 80, 100]
    
    # Thumb
    lms[1] = [1, 40, 120]
    lms[2] = [2, 50, 100]
    if fingers_up[0]:
        lms[3] = [3, 100, 50] # IP 
        lms[4] = [4, 130, 50] # Tip
    else:
        lms[3] = [3, 60, 100]
        lms[4] = [4, 70, 100] # Curls across the palm
        
    # Index
    if fingers_up[1]:
        lms[6] = [6, 30, 80]
        lms[8] = [8, 30, 50]
    else:
        lms[6] = [6, 30, 120]
        lms[8] = [8, 30, 90]
        
    # Middle
    if fingers_up[2]:
        lms[10] = [10, 50, 80]
        lms[12] = [12, 50, 50]
    else:
        lms[10] = [10, 50, 120]
        lms[12] = [12, 50, 90]
        
    # Ring
    if fingers_up[3]:
        lms[14] = [14, 65, 80]
        lms[16] = [16, 65, 50]
    else:
        lms[14] = [14, 65, 120]
        lms[16] = [16, 65, 90]
        
    # Pinky
    if fingers_up[4]:
        lms[18] = [18, 80, 80]
        lms[20] = [20, 80, 50]
    else:
        lms[18] = [18, 80, 120]
        lms[20] = [20, 80, 90]
        
    lms_3d = [Landmark(id=lm[0], pixel_x=int(lm[1]), pixel_y=int(lm[2]), x=lm[1]/100.0, y=lm[2]/100.0, z=0.0) for lm in lms]
    return [{'landmarks': lms_3d, 'score': 99}]

def check(fingers, expected):
    c = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    # Pump to get past hold time
    for _ in range(5):
        c.classify(create_hand(fingers))
    res = c.classify(create_hand(fingers)).gesture
    assert res == expected, f"Expected {expected}, got {res} for fingers {fingers}"

def test_gestures():
    check([0, 0, 0, 0, 0], "Closed Fist")
    check([0, 1, 1, 1, 1], "Four Fingers")
    check([1, 0, 0, 0, 1], "Call Me")
    check([1, 1, 1, 1, 1], "Open Palm")
    check([1, 0, 0, 0, 0], "Thumb Up")
    check([0, 1, 0, 0, 0], "Pointing")
    check([1, 1, 0, 0, 0], "Pointing")
    
    # The default create_hand makes fingers parallel (no divergence)
    check([0, 1, 1, 0, 0], "Two Fingers")
    
def test_victory():
    # Create a hand with [0, 1, 1, 0, 0] but diverge the tips
    h = create_hand([0, 1, 1, 0, 0])[0]
    
    # Base:
    # index mcp = (30, 100), middle mcp = (50, 100) -> d_mcp = 20
    # index tip = (30, 50), middle tip = (50, 50) -> parallel
    
    # Make index point left
    h['landmarks'][8] = Landmark(id=8, pixel_x=10, pixel_y=50, x=0.1, y=0.5, z=0.0)
    # Make middle point right
    h['landmarks'][12] = Landmark(id=12, pixel_x=70, pixel_y=50, x=0.7, y=0.5, z=0.0)
    
    c = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    for _ in range(5):
        c.classify([h])
    res = c.classify([h]).gesture
    assert res == "Victory", f"Got {res}, expected Victory for diverging fingers"

def test_crossed_fingers():
    h = create_hand([0, 1, 1, 0, 0])[0]
    # Cross index and middle fingers and make them close together
    h['landmarks'][8] = Landmark(id=8, pixel_x=41, pixel_y=h['landmarks'][8].pixel_y, x=0.41, y=h['landmarks'][8].y, z=0.0)
    h['landmarks'][12] = Landmark(id=12, pixel_x=39, pixel_y=h['landmarks'][12].pixel_y, x=0.39, y=h['landmarks'][12].y, z=0.0)
    
    c = GestureClassifier(confidence_threshold=50, hold_time_ms=0)
    for _ in range(5):
        c.classify([h])
    res = c.classify([h]).gesture
    assert res == "Crossed Fingers", f"Got {res}"
