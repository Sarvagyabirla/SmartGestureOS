from src.gesture_classifier import GestureClassifier
from tests.test_lighting_robustness import create_base_two_fingers, add_noise
import numpy as np

classifier = GestureClassifier()
lms = add_noise(create_base_two_fingers(), noise_level=0.01)

h1 = {"landmarks": lms, "score": 0.9}
fingers, angles = classifier.fingers_up(lms)
print("FINGERS:", fingers)

thumb_is_higher_than_mcp = True
true_pinch = False

if fingers == [1, 1, 1, 1, 1]: 
    print("Hit: Open Palm")
elif true_pinch: 
    print("Hit: Pinch")
elif fingers == [0, 0, 0, 0, 0]: 
    print("Hit: Closed Fist")
elif fingers == [1, 0, 0, 0, 0]: 
    print("Hit: Thumb Up/Down")
elif fingers[1:] == [0, 0, 0, 0]: 
    print("Hit: Closed Fist 2")
elif fingers[1:] == [0, 1, 0, 0]: 
    print("Hit: Middle Finger")
elif fingers[1:] == [1, 0, 0, 0]: 
    print("Hit: Pointing")
elif fingers[1:3] == [1, 1] and fingers[3:] == [0, 0]:
    print("Hit: Two Fingers Block")
elif fingers[1:] == [1, 1, 1, 0]: 
    print("Hit: Three Fingers")
elif fingers[1:] == [1, 1, 1, 1]: 
    print("Hit: Four Fingers")
elif fingers[1:] == [1, 0, 0, 1]: 
    print("Hit: Rock On")
elif fingers[1:] == [0, 0, 0, 1]: 
    print("Hit: Call Me")
else:
    print("Hit: Unknown")

