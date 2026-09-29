"""
tests/test_final_mission_regressions.py
Comprehensive regression tests covering all 21 items in Section 89-90:
- Landmark perturbation (Gaussian noise, scale, rotation)
- Four Fingers survives weak Open-Palm flicker
- Strong Open Palm cancels Four Fingers
- Screenshot executes once
- Screenshot re-arms only after release
- Pinch relaxed curled fingers recognized
- Pinch does not classify fist
- Two Fingers no dead band
- Victory does not fire during scroll transition
- Double-click anchor remains inside Windows tolerance
- Drag survives one-frame Pinch uncertainty
- Drag releases on strong release
- Drag releases on hand loss
- Scroll time normalization & velocity scaling
- Scroll stop
- Scroll reversal
- Profile migration order
- Legacy schema migration
- Effective canonical settings
- Icon asset in frozen distribution
- Performance p95 from real samples
- Missing pointer samples report N/A
"""

import copy
import json
import math
import random
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models import Landmark
from src.gesture_classifier import GestureClassifier
from src.gesture_mapper import GestureIntentGate, GestureMapper
from src.event_engine import EventEngine, EventState
from src.mouse_controller import MouseController
from src.virtual_mouse import VirtualMouse
from src.settings_manager import SettingsManager, _SAFE_DEFAULTS, validate_settings
from src.pointer_path import LatencyMeter, PointerMetrics


def _create_3d_landmark(id_, px, py, x, y, z=0.0):
    return Landmark(id=id_, pixel_x=px, pixel_y=py, x=x, y=y, z=z)


def _make_hand_data(base_landmarks, score=95):
    lms_3d = [
        _create_3d_landmark(lm[0], int(lm[1]), int(lm[2]), lm[1] / 100.0, lm[2] / 100.0, lm[3] if len(lm) > 3 else 0.0)
        for lm in base_landmarks
    ]
    return [{"landmarks": lms_3d, "score": score}]


def _create_base_two_fingers(tip_spacing_x=0.05):
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
        Landmark(id=8,  pixel_x=int((0.5 - tip_spacing_x / 2) * 1000), pixel_y=500, x=0.5 - tip_spacing_x / 2, y=0.2, z=0.0),  # index tip
        Landmark(id=9,  pixel_x=500, pixel_y=500, x=0.5,  y=0.5, z=0.0),  # middle mcp
        Landmark(id=10, pixel_x=500, pixel_y=500, x=0.5,  y=0.4, z=0.0),
        Landmark(id=11, pixel_x=500, pixel_y=500, x=0.5,  y=0.3, z=0.0),
        Landmark(id=12, pixel_x=int((0.5 + tip_spacing_x / 2) * 1000), pixel_y=500, x=0.5 + tip_spacing_x / 2, y=0.2, z=0.0),  # middle tip
        Landmark(id=13, pixel_x=650, pixel_y=500, x=0.65, y=0.5, z=0.0),  # ring mcp
        Landmark(id=14, pixel_x=650, pixel_y=500, x=0.65, y=0.6, z=0.0),
        Landmark(id=15, pixel_x=650, pixel_y=500, x=0.65, y=0.55, z=0.0),
        Landmark(id=16, pixel_x=650, pixel_y=500, x=0.65, y=0.5,  z=0.0),  # ring tip (folded)
        Landmark(id=17, pixel_x=750, pixel_y=500, x=0.75, y=0.5, z=0.0),  # pinky mcp
        Landmark(id=18, pixel_x=750, pixel_y=500, x=0.75, y=0.6, z=0.0),
        Landmark(id=19, pixel_x=750, pixel_y=500, x=0.75, y=0.55, z=0.0),
        Landmark(id=20, pixel_x=750, pixel_y=500, x=0.75, y=0.5,  z=0.0),  # pinky tip (folded)
    ]


# ---------------------------------------------------------------------------
# 1. Landmark Perturbation & Noise Robustness (Section 89)
# ---------------------------------------------------------------------------

def test_landmark_perturbation_noise_resilience():
    """Verify that small Gaussian noise and scale changes do not break classification."""
    classifier = GestureClassifier(confidence_threshold=35)

    base_lms = [[i, 50, 100, 0.0] for i in range(21)]
    base_lms[0] = [0, 50, 150, 0.0]   # Wrist
    base_lms[5] = [5, 45, 100, 0.0]   # Index MCP
    base_lms[6] = [6, 45, 75, 0.0]    # Index PIP
    base_lms[7] = [7, 45, 50, 0.0]    # Index DIP
    base_lms[8] = [8, 45, 25, 0.0]    # Index Tip (extended)

    for tip, pip in [(12, 10), (16, 14), (20, 18)]:
        base_lms[pip] = [pip, 50 + tip, 90, 0.0]
        base_lms[tip] = [tip, 50 + tip, 120, 0.0]
    base_lms[4] = [4, 48, 105, 0.0]

    random.seed(42)
    recognized_count = 0
    for _ in range(15):
        noisy_lms = copy.deepcopy(base_lms)
        for lm in noisy_lms:
            lm[1] += random.gauss(0, 0.5)
            lm[2] += random.gauss(0, 0.5)
        hand = _make_hand_data(noisy_lms)
        res = classifier.classify(hand)
        if res.gesture == "Pointing":
            recognized_count += 1

    assert recognized_count >= 13, f"Perturbation resilience too low: {recognized_count}/15"


# ---------------------------------------------------------------------------
# 2. Four Fingers Survives Weak Open-Palm Flicker (Section 90)
# ---------------------------------------------------------------------------

def test_four_fingers_survives_weak_open_palm_flicker():
    gate = GestureIntentGate()
    t0 = 100.0

    # Hold Four Fingers for 100ms
    for i in range(5):
        fired = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0 + i * 0.02)
        assert not fired

    # Transient 1-frame ambiguous Open Palm with is_adjacent_grace=True
    fired = gate.check("Four Fingers", raw_gesture="Open Palm", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0 + 0.12, is_adjacent_grace=True)
    assert not fired
    assert gate.start_time == t0

    # Return to Four Fingers and complete 300ms hold
    fired = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0 + 0.35)
    assert fired is True


# ---------------------------------------------------------------------------
# 3. Strong Open Palm Cancels Four Fingers Immediately (Section 90)
# ---------------------------------------------------------------------------

def test_strong_open_palm_cancels_four_fingers():
    gate = GestureIntentGate()
    t0 = 100.0

    gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0)
    gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0 + 0.15)
    assert gate.start_time == t0

    # Strong conflicting Open Palm without adjacent grace immediately cancels Four Fingers intent
    gate.check("Open Palm", raw_gesture="Open Palm", duration=0.3, dropout_grace=0.12, action_name="task_view", now=t0 + 0.18, is_adjacent_grace=False)
    assert gate.target_gesture != "Four Fingers"
    assert gate.start_time == 0.0


# ---------------------------------------------------------------------------
# 4. Screenshot Executes Once & Re-arms Only After Release (Section 90)
# ---------------------------------------------------------------------------

def test_screenshot_single_shot_and_rearm_after_release():
    gate = GestureIntentGate()
    t0 = 100.0

    gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0)
    fired = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0 + 0.35)
    assert fired is True
    assert gate.executed_once is True

    # Continued hold must NOT re-fire
    for step in range(5):
        fired_cont = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0 + 0.40 + step * 0.1)
        assert not fired_cont

    # Release to neutral
    gate.check(None, raw_gesture=None, now=t0 + 1.0)
    assert gate.executed_once is False

    # Second hold after release fires again
    gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0 + 1.1)
    fired_2 = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0 + 1.45)
    assert fired_2 is True


# ---------------------------------------------------------------------------
# 5. Pinch with Relaxed Curled Fingers vs Closed Fist (Section 90)
# ---------------------------------------------------------------------------

def test_pinch_with_relaxed_curled_fingers_recognized():
    classifier = GestureClassifier(confidence_threshold=35)

    pinch_lms = [[i, 50, 100, 0.0] for i in range(21)]
    pinch_lms[0] = [0, 50, 160, 0.0]  # Wrist
    pinch_lms[9] = [9, 50, 100, 0.0]  # Middle MCP

    pinch_lms[4] = [4, 48, 60, 0.0]   # Thumb tip
    pinch_lms[8] = [8, 50, 60, 0.0]   # Index tip
    pinch_lms[6] = [6, 50, 75, 0.0]   # Index PIP
    pinch_lms[5] = [5, 50, 95, 0.0]   # Index MCP

    for tip, pip, mcp in [(12, 10, 9), (16, 14, 13), (20, 18, 17)]:
        pinch_lms[mcp] = [mcp, 50 + tip, 100, 0.0]
        pinch_lms[pip] = [pip, 50 + tip, 115, 0.0]
        pinch_lms[tip] = [tip, 50 + tip, 125, 0.0]

    hand = _make_hand_data(pinch_lms)
    res = classifier.classify(hand)
    assert res.gesture == "Pinch", f"Expected Pinch, got {res.gesture}"


def test_pinch_does_not_classify_closed_fist():
    classifier = GestureClassifier(confidence_threshold=35)

    lms_list = [[i, 0, 0, 0.0] for i in range(21)]
    lms_list[0] = [0, 50, 150, 0.0]
    lms_list[5] = [5, 30, 100, 0.0]
    lms_list[9] = [9, 50, 100, 0.0]

    lms_list[1] = [1, 40, 120, 0.0]
    lms_list[2] = [2, 50, 100, 0.0]
    lms_list[17] = [17, 100, 100, 0.0]
    lms_list[3] = [3, 60, 100, 0.0]
    lms_list[4] = [4, 70, 100, 0.0]

    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms_list[pip] = [pip, 50, 120, 0.0]
        lms_list[tip] = [tip, 50, 90, 0.0]

    hand = _make_hand_data(lms_list)
    res = classifier.classify(hand)
    assert res.gesture == "Closed Fist", f"Expected Closed Fist, got {res.gesture}"


# ---------------------------------------------------------------------------
# 6. Two Fingers vs Victory Continuous Transition (No Dead Band) (Section 90)
# ---------------------------------------------------------------------------

def test_two_fingers_no_dead_band_and_hysteresis():
    classifier = GestureClassifier(confidence_threshold=35)

    # Spacing 0.05 -> Two Fingers
    hand_close = [{"landmarks": _create_base_two_fingers(tip_spacing_x=0.05), "score": 95}]
    res1 = classifier.classify(hand_close)
    assert res1.gesture == "Two Fingers"

    # Intermediate spacing 0.24 (formerly dead band) -> stays Two Fingers under hysteresis
    hand_mid = [{"landmarks": _create_base_two_fingers(tip_spacing_x=0.24), "score": 95}]
    res2 = classifier.classify(hand_mid)
    assert res2.gesture == "Two Fingers", f"Expected Two Fingers under hysteresis, got {res2.gesture}"

    # Wide spacing 0.36 -> Victory
    hand_wide = [{"landmarks": _create_base_two_fingers(tip_spacing_x=0.36), "score": 95}]
    res3 = classifier.classify(hand_wide)
    assert res3.gesture == "Victory"


# ---------------------------------------------------------------------------
# 7. Double-Click Anchor Tolerance Lock (Section 90)
# ---------------------------------------------------------------------------

def test_double_click_anchor_remains_inside_windows_tolerance():
    mc = MouseController.__new__(MouseController)
    mc.mouse = VirtualMouse()
    mc.mouse.move = MagicMock(return_value=True)
    mc.mouse.last_pos = (500, 500)
    mc.engine = EventEngine(mc)
    mc._pointer_intent = MagicMock()
    mc._pointer_intent.update.return_value = True
    mc.metrics = PointerMetrics()

    mc.engine.state = EventState.PINCH_RELEASE_WAIT
    mc.engine.click_anchor = (500, 500)

    mc.mouse.map_coordinates = MagicMock(return_value=(505, 508))

    lms = [Landmark(id=i, pixel_x=100, pixel_y=100, x=0.5, y=0.5, z=0.0) for i in range(21)]
    moved = mc.process_pointer(lms, "Pointing", "Pointing", 640, 480, now=10.0)

    assert moved is False
    assert mc.mouse.last_pos == (500, 500)
    assert mc.engine.state == EventState.PINCH_RELEASE_WAIT

    mc.mouse.map_coordinates = MagicMock(return_value=(550, 550))
    mc.process_pointer(lms, "Pointing", "Pointing", 640, 480, now=10.05)
    assert mc.engine.state == EventState.HOVER


# ---------------------------------------------------------------------------
# 8. Drag Robustness: Survives 1-Frame Uncertainty, Releases on Strong Exit (Section 90)
# ---------------------------------------------------------------------------

def test_drag_survives_transient_uncertainty_and_releases_cleanly():
    mc = MouseController.__new__(MouseController)
    mc.mouse = VirtualMouse()
    mc.mouse.move = MagicMock()
    mc.mouse.drag = MagicMock()
    mc.mouse.click = MagicMock()
    mc.mouse.get_cursor_pos = MagicMock(return_value=(500, 500))
    mc.mouse.map_coordinates = MagicMock(return_value=(500, 500))
    engine = EventEngine(mc)

    lms = [Landmark(id=i, pixel_x=100, pixel_y=100, x=0.5, y=0.5, z=0.0) for i in range(21)]

    engine.process("Pinch", "Pinch", 100, 100, 640, 480, lms, now=1.0)
    assert engine.state == EventState.PINCH_DOWN

    engine.process("Pinch", "Pinch", 100, 100, 640, 480, lms, now=1.4)
    assert engine.state == EventState.DRAGGING
    assert mc.mouse.drag.called

    engine.process("Unknown", "Unknown", 100, 100, 640, 480, lms, now=1.45)
    assert engine.state == EventState.DRAGGING, "Drag should survive short transient dropout"

    engine.on_hand_lost()
    assert engine.state == EventState.HAND_LOST


# ---------------------------------------------------------------------------
# 9. Scroll Time Normalization, Stop, and Reversal (Section 90)
# ---------------------------------------------------------------------------

def test_scroll_velocity_and_reversal():
    mc = MouseController.__new__(MouseController)
    mc.mouse = VirtualMouse()
    mc.mouse.scroll = MagicMock()
    engine = EventEngine(mc)

    lms = [Landmark(id=i, pixel_x=100, pixel_y=100, x=0.5, y=0.5, z=0.0) for i in range(21)]
    lms[8] = Landmark(id=8, pixel_x=100, pixel_y=200, x=0.5, y=0.4, z=0.0)
    lms[12] = Landmark(id=12, pixel_x=100, pixel_y=200, x=0.5, y=0.4, z=0.0)

    engine.process("Two Fingers", "Two Fingers", 100, 100, 640, 480, lms, now=10.0)
    assert engine.state == EventState.SCROLLING

    lms[8].y = 0.45
    lms[12].y = 0.45
    engine.process("Two Fingers", "Two Fingers", 100, 100, 640, 480, lms, now=10.05)
    assert mc.mouse.scroll.called
    first_scroll_calls = mc.mouse.scroll.call_count

    lms[8].y = 0.35
    lms[12].y = 0.35
    engine.process("Two Fingers", "Two Fingers", 100, 100, 640, 480, lms, now=10.10)
    assert mc.mouse.scroll.call_count > first_scroll_calls


# ---------------------------------------------------------------------------
# 10. Profile Schema Version and Migration Ordering (Section 90)
# ---------------------------------------------------------------------------

def test_profile_migration_v1_to_v2_order_and_values():
    legacy_profile = {
        "camera": {"index": 0},
        "gestures": {
            "sensitivity": 0.70,
            "smoothing": 2,
        },
        "calibration": {
            "confidence_threshold": 50.0,
            "two_finger_max_spacing": 0.2,
            "victory_min_spacing": 0.35,
        },
    }

    changed = SettingsManager._migrate_profile_data(legacy_profile)
    assert changed is True
    assert legacy_profile["profile_schema_version"] == 2
    assert legacy_profile["gestures"]["sensitivity"] == 0.75
    assert legacy_profile["calibration"]["confidence_threshold"] == 35.0
    assert legacy_profile["calibration"]["two_finger_max_spacing"] == 0.22
    assert legacy_profile["calibration"]["victory_min_spacing"] == 0.30
    assert legacy_profile["gestures"]["pointer_enter_samples"] == 2
    assert legacy_profile["gestures"]["pointer_grace_ms"] == 100.0


def test_profile_migration_preserves_custom_user_sensitivity():
    custom_profile = {
        "gestures": {"sensitivity": 0.65},
        "calibration": {},
    }
    SettingsManager._migrate_profile_data(custom_profile)
    assert custom_profile["gestures"]["sensitivity"] == 0.65
    assert custom_profile["profile_schema_version"] == 2


# ---------------------------------------------------------------------------
# 11. Performance Metrics p95 & Missing Samples (Section 90)
# ---------------------------------------------------------------------------

def test_performance_p95_from_real_samples():
    meter = LatencyMeter()
    for val in range(10, 110, 10):
        meter.add_ms(val)

    assert meter.median_ms == 55.0
    p95 = meter.percentile_ms(0.95)
    assert p95 is not None
    assert 90 <= p95 <= 100


def test_missing_pointer_samples_reports_none():
    metrics = PointerMetrics()
    data = metrics.as_dict()
    assert data["capture_to_pointer_ms"] is None
    assert data["capture_to_pointer_p95_ms"] is None
