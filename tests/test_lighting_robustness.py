"""
Tests: Landmark Noise Robustness for GestureClassifier.

F-35 FIX: These tests are correctly named 'landmark noise robustness'.
They do NOT test real lighting conditions (which would require actual images/video).
They test the classifier's tolerance to Gaussian perturbations of landmark coordinates.

NOTE: hold_time_ms removed from GestureClassifier (F-12 fix).
"""

import pytest
import numpy as np
from src.gesture_classifier import GestureClassifier
from src.models import Landmark


def create_base_two_fingers():
    """Create a geometrically valid 'Two Fingers' pose (index+middle extended, rest closed)."""
    return [
        Landmark(id=0,  pixel_x=500, pixel_y=500, x=0.5,  y=0.8, z=0.0),  # wrist
        Landmark(id=1,  pixel_x=400, pixel_y=500, x=0.4,  y=0.7, z=0.0),  # thumb mcp
        Landmark(id=2,  pixel_x=300, pixel_y=500, x=0.3,  y=0.7, z=0.0),
        Landmark(id=3,  pixel_x=300, pixel_y=500, x=0.3,  y=0.6, z=0.0),
        Landmark(id=4,  pixel_x=400, pixel_y=500, x=0.4,  y=0.6, z=0.0),  # thumb tip
        Landmark(id=5,  pixel_x=450, pixel_y=500, x=0.45, y=0.5, z=0.0),  # index mcp
        Landmark(id=6,  pixel_x=450, pixel_y=500, x=0.45, y=0.4, z=0.0),
        Landmark(id=7,  pixel_x=450, pixel_y=500, x=0.45, y=0.3, z=0.0),
        Landmark(id=8,  pixel_x=450, pixel_y=500, x=0.45, y=0.2, z=0.0),  # index tip (extended)
        Landmark(id=9,  pixel_x=500, pixel_y=500, x=0.5,  y=0.5, z=0.0),  # middle mcp
        Landmark(id=10, pixel_x=500, pixel_y=500, x=0.5,  y=0.4, z=0.0),
        Landmark(id=11, pixel_x=500, pixel_y=500, x=0.5,  y=0.3, z=0.0),
        Landmark(id=12, pixel_x=500, pixel_y=500, x=0.5,  y=0.2, z=0.0),  # middle tip (extended)
        Landmark(id=13, pixel_x=650, pixel_y=500, x=0.65, y=0.5, z=0.0),  # ring mcp
        Landmark(id=14, pixel_x=650, pixel_y=500, x=0.65, y=0.6, z=0.0),
        Landmark(id=15, pixel_x=650, pixel_y=500, x=0.65, y=0.55, z=0.0),
        Landmark(id=16, pixel_x=650, pixel_y=500, x=0.65, y=0.5,  z=0.0),  # ring tip (folded)
        Landmark(id=17, pixel_x=750, pixel_y=500, x=0.75, y=0.5, z=0.0),  # pinky mcp
        Landmark(id=18, pixel_x=750, pixel_y=500, x=0.75, y=0.6, z=0.0),
        Landmark(id=19, pixel_x=750, pixel_y=500, x=0.75, y=0.55, z=0.0),
        Landmark(id=20, pixel_x=750, pixel_y=500, x=0.75, y=0.5,  z=0.0),  # pinky tip (folded)
    ]


def add_noise(landmarks, noise_level=0.02):
    """Add Gaussian noise to normalized landmark coordinates."""
    noisy = []
    for lm in landmarks:
        noisy.append(Landmark(
            id=lm.id, pixel_x=lm.pixel_x, pixel_y=lm.pixel_y,
            x=lm.x + np.random.normal(0, noise_level),
            y=lm.y + np.random.normal(0, noise_level),
            z=lm.z + np.random.normal(0, noise_level),
        ))
    return noisy


def test_landmark_noise_robustness_low():
    """
    With low landmark noise (0.01), classifier should stabilize on 'Two Fingers'
    after 5 frames. Tests noise tolerance, NOT real lighting conditions.
    """
    np.random.seed(42)
    # F-12: no hold_time_ms argument
    classifier = GestureClassifier(confidence_threshold=50)
    base_lms = create_base_two_fingers()

    stable_results = []
    for i in range(5):
        lms = add_noise(base_lms, noise_level=0.01)
        result = classifier.classify([{"landmarks": lms, "score": 90.0}])
        stable_results.append(result.gesture)

    assert stable_results[-1] == "Two Fingers", (
        f"Expected 'Two Fingers' with low noise, got {stable_results}"
    )


def test_landmark_noise_robustness_high():
    """
    With very high landmark noise (0.05 = 5% screen width), the classifier
    should never spuriously lock onto a completely unrelated gesture stably.
    Tests noise resilience, NOT real lighting conditions.
    """
    np.random.seed(42)
    # F-12: no hold_time_ms argument
    classifier = GestureClassifier(confidence_threshold=50)
    base_lms = create_base_two_fingers()

    spurious_gestures = set()
    stable = "Unknown"
    for i in range(20):
        lms = add_noise(base_lms, noise_level=0.05)  # 5% noise — very large
        result = classifier.classify([{"landmarks": lms, "score": 90.0}])
        stable = result.gesture

    # High noise may produce Unknown/None/Two Fingers — but never e.g. "Closed Fist" stably
    if stable not in {"None", "Unknown", "Two Fingers"}:
        spurious_gestures.add(stable)

    assert len(spurious_gestures) == 0, (
        f"High landmark noise caused spurious stable gestures: {spurious_gestures}"
    )
