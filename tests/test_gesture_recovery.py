"""
Regression tests for SmartGestureOS Gesture Recovery.
Covers:
- Four Fingers vs Open Palm discrimination
- Strong Four Fingers hold with short Unknown dropout grace
- Explicit Open Palm conflicting gesture immediately cancels Four Fingers intent
- Screenshot single-fire and release-rearm gating
- ActionExecutor screenshot execution and pause cancellation
- Canonical mappings consistency across modes
- Gesture-specific shape confidence scoring
- Direct DesktopController take_screenshot execution (physical file, size > 0, valid PNG)
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.desktop_controller import DesktopController, SCREENSHOTS_DIR
from src.gesture_classifier import GestureClassifier
from src.gesture_mapper import GestureIntentGate, GestureMapper, _ACTION_POLICY, _get_action_policy
from src.action_executor import ActionExecutor
from src.models import Landmark, ActionResult
from config import SETTINGS


def _make_landmark(id_, px, py, x, y, z=0.0):
    return Landmark(id=id_, pixel_x=px, pixel_y=py, x=x, y=y, z=z)


def _make_hand_landmarks(thumb_up: bool = False, thumb_abducted: bool = False):
    """Generate 21 landmarks with 4 extended non-thumb fingers."""
    lms = [[i, 50, 100] for i in range(21)]
    # Wrist & palm base
    lms[0] = [0, 50, 160]
    lms[5] = [5, 40, 100]
    lms[9] = [9, 50, 100]
    lms[13] = [13, 60, 100]
    lms[17] = [17, 70, 100]

    # Non-thumb fingers fully extended (tip y < pip y)
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lms[tip] = [tip, lms[pip][1], 20]
        lms[pip] = [pip, lms[pip][1], 90]

    if thumb_up and thumb_abducted:
        # Fully abducted/extended thumb for Open Palm
        lms[1] = [1, 35, 130]
        lms[2] = [2, 25, 115]
        lms[3] = [3, 15, 105]
        lms[4] = [4, 5, 95]   # Far to the left, away from palm center
    elif thumb_up:
        # Mildly open thumb
        lms[1] = [1, 40, 130]
        lms[2] = [2, 35, 120]
        lms[3] = [3, 30, 110]
        lms[4] = [4, 25, 105]
    else:
        # Tucked thumb against palm for Four Fingers
        lms[1] = [1, 45, 135]
        lms[2] = [2, 47, 125]
        lms[3] = [3, 49, 115]
        lms[4] = [4, 50, 108]  # Right in front of palm center

    lms_3d = [
        _make_landmark(lm[0], int(lm[1]), int(lm[2]), lm[1] / 100.0, lm[2] / 100.0)
        for lm in lms
    ]
    return [{"landmarks": lms_3d, "score": 95}]


# ==============================================================================
# 1. Four Fingers vs Open Palm Discrimination
# ==============================================================================

def test_four_fingers_vs_open_palm():
    classifier = GestureClassifier(confidence_threshold=40)

    # 1. Tucked thumb -> Four Fingers
    tucked_hand = _make_hand_landmarks(thumb_up=False)
    for _ in range(3):
        res_tucked = classifier.classify(tucked_hand)
    assert res_tucked.gesture == "Four Fingers"
    assert res_tucked.confidence >= 50

    # 2. Abducted thumb -> Open Palm
    classifier.reset()
    abducted_hand = _make_hand_landmarks(thumb_up=True, thumb_abducted=True)
    for _ in range(3):
        res_abducted = classifier.classify(abducted_hand)
    assert res_abducted.gesture == "Open Palm"
    assert res_abducted.confidence >= 50


# ==============================================================================
# 2. Gesture Intent Gate: Dropout Grace vs Explicit Conflict Cancellation
# ==============================================================================

def test_four_fingers_hold_with_unknown_dropout_grace():
    gate = GestureIntentGate()
    t0 = 1000.0

    # Frame 1: Initial Four Fingers
    fired = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0)
    assert not fired
    assert gate.start_time == t0

    # Frame 2 (after 100ms): raw drops to Unknown, stable is Four Fingers
    t1 = t0 + 0.10
    fired = gate.check("Four Fingers", raw_gesture="Unknown", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t1)
    assert not fired
    # Hold start time should be preserved across dropout grace!
    assert gate.start_time == t0

    # Frame 3 (after 200ms): raw returns to Four Fingers
    t2 = t0 + 0.20
    fired = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t2)
    assert not fired
    assert gate.start_time == t0

    # Frame 4 (after 310ms): duration exceeded -> fires!
    t3 = t0 + 0.31
    fired = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t3)
    assert fired
    assert gate.executed_once is True


def test_explicit_conflicting_gesture_cancels_intent():
    gate = GestureIntentGate()
    t0 = 1000.0

    # Frame 1: Four Fingers starts
    gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0)
    assert gate.start_time == t0

    # Frame 2: Conflicting raw gesture arrives: Open Palm
    t1 = t0 + 0.10
    fired = gate.check("Four Fingers", raw_gesture="Open Palm", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t1)
    assert not fired
    # Conflicting gesture must reset the gate immediately
    assert gate.start_time == 0.0
    assert gate.target_gesture is None


# ==============================================================================
# 3. Screenshot Single Fire and Release-Rearm
# ==============================================================================

def test_screenshot_single_fire_and_release_rearm():
    gate = GestureIntentGate()
    t0 = 1000.0

    # Hold until firing at 300ms
    gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0)
    fired_1 = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t0 + 0.31)
    assert fired_1 is True

    # Continue holding Four Fingers for another 500ms -> MUST NOT fire again!
    for step in range(5):
        t_cont = t0 + 0.40 + (step * 0.1)
        fired_cont = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t_cont)
        assert not fired_cont, f"Repeated fire at step {step}!"

    # Release gesture (target becomes None)
    t_rel = t0 + 1.0
    gate.check(None, raw_gesture=None, now=t_rel)
    assert gate.executed_once is False

    # Second hold after release -> should fire again after 300ms
    t_new = t_rel + 0.1
    gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t_new)
    fired_2 = gate.check("Four Fingers", raw_gesture="Four Fingers", duration=0.3, dropout_grace=0.12, action_name="screenshot", now=t_new + 0.31)
    assert fired_2 is True


# ==============================================================================
# 4. ActionExecutor: Screenshot Success & Cancellation on Pause
# ==============================================================================

def test_action_executor_screenshot_execution():
    results = []

    def on_result(name, result, duration):
        results.append((name, result, duration))

    executor = ActionExecutor(on_result=on_result)
    executor.start()

    # Submit screenshot action with mock action func
    mock_action = MagicMock(return_value=ActionResult(True, "screenshot", "Saved screen_test.png", None, time.perf_counter()))
    success = executor.submit("screenshot", mock_action)
    assert success is True

    # Wait briefly for worker thread to process
    time.sleep(0.15)
    executor.stop(timeout=1.0)

    assert len(results) == 1
    name, res, dur = results[0]
    assert name == "screenshot"
    assert res.success is True
    assert "Saved screen_test.png" in res.message


def test_action_executor_cancellation_when_paused():
    results = []

    def on_result(name, result, duration):
        results.append((name, result, duration))

    executor = ActionExecutor(on_result=on_result)
    executor.start()

    # Re-validation predicate returning False (simulates pause or invalidated state)
    mock_action = MagicMock()
    success = executor.submit("screenshot", mock_action, is_valid=lambda: False)
    assert success is True

    time.sleep(0.15)
    executor.stop(timeout=1.0)

    # Callable was rejected before execution due to is_valid returning False
    mock_action.assert_not_called()
    assert len(results) == 0


# ==============================================================================
# 5. Canonical Mappings Consistency Verification
# ==============================================================================

def test_all_canonical_mappings_consistency():
    """Verify all discrete mappings defined in prompt section 3 match defaults exactly."""
    canonical_general_discrete = {
        "Victory": "open_vscode",
        "Rock On": "open_chrome",
        "Four Fingers": "screenshot",
        "Thumb Up": "volume_up",
        "Thumb Down": "volume_down",
        "Open Palm": "task_view",
        "Closed Fist": "show_desktop",
        "Crossed Fingers": "lock_pc",
        "Call Me": "switch_mode",
    }
    canonical_media_discrete = {
        "Pinch": "play_pause",
        "Victory": "next_track",
        "Three Fingers": "prev_track",
        "Closed Fist": "mute",
        "Call Me": "switch_mode",
    }
    canonical_draw_discrete = {
        "Victory": "undo",
        "Three Fingers": "redo",
        "Four Fingers": "save_drawing",
        "Thumb Up": "cycle_color",
        "Thumb Down": "toggle_eraser",
        "Closed Fist": "clear_canvas",
        "Call Me": "switch_mode",
    }

    cfg_mappings = SETTINGS.get("mappings", {})

    for gesture, action in canonical_general_discrete.items():
        assert cfg_mappings.get("GENERAL", {}).get(gesture) == action, f"GENERAL {gesture} mismatch!"

    for gesture, action in canonical_media_discrete.items():
        assert cfg_mappings.get("MEDIA", {}).get(gesture) == action, f"MEDIA {gesture} mismatch!"

    for gesture, action in canonical_draw_discrete.items():
        assert cfg_mappings.get("DRAW", {}).get(gesture) == action, f"DRAW {gesture} mismatch!"


# ==============================================================================
# 6. Action Policy Verification
# ==============================================================================

def test_action_policy_table_values():
    """Verify explicit hold times, dropout grace, and release gates."""
    screenshot_policy = _get_action_policy("screenshot")
    assert screenshot_policy["hold_ms"] == 300
    assert screenshot_policy["dropout_grace_ms"] == 120
    assert screenshot_policy["require_release"] is True

    vol_policy = _get_action_policy("volume_up")
    assert vol_policy["hold_ms"] == 200
    assert vol_policy["require_release"] is False

    lock_policy = _get_action_policy("lock_pc")
    assert lock_policy["hold_ms"] >= 300
    assert lock_policy["require_release"] is True


# ==============================================================================
# 7. Direct DesktopController Physical Screenshot Test
# ==============================================================================

def test_direct_screenshot_controller_creates_valid_png():
    """Test Layer A: DesktopController.take_screenshot() creates valid PNG on Windows."""
    ctrl = DesktopController()
    res = ctrl.take_screenshot()

    assert res.success is True, f"take_screenshot failed: {res.error}"
    # Parse filename from message: "Saved screen_..."
    assert res.message and res.message.startswith("Saved ")
    saved_name = res.message.replace("Saved ", "").strip()
    file_path = SCREENSHOTS_DIR / saved_name

    assert file_path.exists(), f"Screenshot file does not exist: {file_path}"
    assert file_path.stat().st_size > 0, "Screenshot file is 0 bytes"

    # Verify Pillow can open and read valid PNG
    with Image.open(file_path) as img:
        assert img.format == "PNG"
        assert img.width > 0 and img.height > 0

    # Clean up test artifact
    try:
        file_path.unlink()
    except Exception:
        pass
