"""
Tests for GestureClassifier.

NOTE on hold_time_ms (F-12 fix):
    The 'hold_time_ms' parameter has been removed from GestureClassifier.__init__().
    Temporal stabilization is handled by the history deque (mode filter) + EMA,
    NOT by a hold timer inside the classifier.
    The action-intent hold timer lives in GestureHoldTimer inside GestureMapper.
    These tests use confidence_threshold only.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gesture_classifier import GestureClassifier
from src.models import Landmark


def _make_landmark(id_, px, py, x, y, z=0.0):
    return Landmark(id=id_, pixel_x=px, pixel_y=py, x=x, y=y, z=z)


def test_open_palm():
    classifier = GestureClassifier(confidence_threshold=50)
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

    lms_list_3d = [
        _make_landmark(lm[0], int(lm[1]), int(lm[2]), lm[1] / 100.0, lm[2] / 100.0)
        for lm in lms_list
    ]
    hands_data = [{"landmarks": lms_list_3d, "score": 99}]

    # Feed 3 times for history buffer to stabilize
    classifier.classify(hands_data)
    classifier.classify(hands_data)
    result = classifier.classify(hands_data)
    assert result.gesture == "Open Palm"
    assert result.confidence > 60


def test_closed_fist():
    classifier = GestureClassifier(confidence_threshold=50)
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

    # Fingers down (tip y > pip y in image coords)
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[pip] = [pip, 50, 120]
        lms_list[tip] = [tip, 50, 90]

    lms_list_3d = [
        _make_landmark(lm[0], int(lm[1]), int(lm[2]), lm[1] / 100.0, lm[2] / 100.0)
        for lm in lms_list
    ]
    hands_data = [{"landmarks": lms_list_3d, "score": 99}]

    classifier.classify(hands_data)
    classifier.classify(hands_data)
    result = classifier.classify(hands_data)
    assert result.gesture == "Closed Fist"
    assert result.confidence >= 50


def test_invalid_landmarks():
    classifier = GestureClassifier(confidence_threshold=50)
    result = classifier.classify([])
    assert result.confidence < 20

    result2 = classifier.classify([
        {"landmarks": [_make_landmark(0, 0, 0, 0.0, 0.0)], "score": 0}
    ])
    assert result2.confidence < 30


def test_rotation_resilience():
    """Upside-down hand should still classify via vector-distance logic."""
    classifier = GestureClassifier(confidence_threshold=50)
    lms_list = [[i, 0, 0] for i in range(21)]

    # Wrist at top, palm below (inverted Y)
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

    # Fingers up (pointing DOWN in image — still extended)
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[tip] = [tip, 50, 150]
        lms_list[pip] = [pip, 50, 50]

    lms_list_3d = [
        _make_landmark(lm[0], int(lm[1]), int(lm[2]), lm[1] / 100.0, lm[2] / 100.0)
        for lm in lms_list
    ]
    hands_data = [{"landmarks": lms_list_3d, "score": 99}]

    classifier.classify(hands_data)
    classifier.classify(hands_data)
    result = classifier.classify(hands_data)
    assert result.gesture == "Open Palm"


def test_jitter_filtering():
    """
    After 10 stable Open Palm frames, a single Closed Fist frame should NOT
    switch the stable gesture. The history deque (mode filter) provides stability.
    """
    classifier = GestureClassifier(confidence_threshold=50)

    # Build Open Palm data
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
        lms_list[tip] = [tip, 50, 10]
        lms_list[pip] = [pip, 50, 100]

    palm_data = [{"landmarks": [
        _make_landmark(lm[0], int(lm[1]), int(lm[2]), lm[1] / 100.0, lm[2] / 100.0)
        for lm in lms_list
    ], "score": 99}]

    # Build Closed Fist data (jitter)
    fist_list = list(lms_list)
    fist_list[1] = [1, 40, 120]
    fist_list[2] = [2, 50, 100]
    fist_list[3] = [3, 60, 100]
    fist_list[4] = [4, 70, 100]
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        fist_list[pip] = [pip, 50, 120]
        fist_list[tip] = [tip, 50, 90]
    fist_data = [{"landmarks": [
        _make_landmark(lm[0], int(lm[1]), int(lm[2]), lm[1] / 100.0, lm[2] / 100.0)
        for lm in fist_list
    ], "score": 99}]

    # Hold Open Palm for 10 frames to fill history
    for _ in range(10):
        result = classifier.classify(palm_data)

    assert result.gesture == "Open Palm", f"Expected Open Palm, got {result.gesture}"

    # Inject 1 jitter frame — stable gesture must not change
    result = classifier.classify(fist_data)
    assert result.gesture == "Open Palm", (
        f"Single jitter frame switched stable gesture to {result.gesture}"
    )
