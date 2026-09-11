# Test Baseline

**Command:** `python -m pytest -q`

**Initial Result:**
- 23 passed
- 7 failed

**Failing Tests:**
1. `tests/test_classifier.py::test_closed_fist` - Closed Fist classified as Open Palm
2. `tests/test_gestures_extra.py::test_gestures` - Closed Fist classified as Open Palm
3. `tests/test_gestures_extra.py::test_crossed_fingers` - Crossed Fingers classified as Open Palm
4. `tests/test_pipeline.py::TestGestureClassifier::test_classify_pointing` - Pointing returns Unknown
5. `tests/test_classifier.py::test_jitter_filtering` - Tuple/API unpack mismatch (`ValueError: too many values to unpack (expected 2)`)
6. `tests/test_distance_scaling.py::test_distance_scaling` - Dict/object landmark mismatch (`AttributeError: 'dict' object has no attribute 'pixel_x'`)
7. `tests/test_utils_extra.py::test_virtual_mouse_deadzone` - VirtualMouse deadzone test does not move even for a large displacement (`assert (960, 540) != (960, 540)`)
