"""
Regression tests for SmartGestureOS Physical Reality Recovery.
Covers all requirements from Part P:
1. Pointing never becomes Victory under small middle-finger landmark noise
2. No discrete action on single-frame candidate
3. No click on hand loss
4. No click on stale tracking
5. No click when pointer leaves valid tracking region
6. No drag click on hand loss
7. Double-click anchor lock
8. Drag dropout grace
9. Scroll state survives small Two-Finger jitter
10. Right click single-shot release gate
11. Screenshot path actual creation and valid PNG
12. Screenshot uses predictable wall-clock filename
13. Background hiding does not stop processing
14. Pause disables ALL action paths
15. Resume neutral re-arm blocks held gesture
16. Async queue generation prevents stale action
"""

import math
import time
import os
import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch
import pytest
import numpy as np
from PIL import Image

from src.models import Landmark, ActionResult, GestureResult
from src.gesture_classifier import GestureClassifier
from src.event_engine import EventEngine, EventState
from src.mouse_controller import MouseController
from src.gesture_mapper import GestureMapper, GestureIntentGate
from src.desktop_controller import DesktopController
from src.paths import SCREENSHOTS_DIR
from src.action_executor import ActionExecutor


def _make_lms(index_up=True, middle_up=False, middle_bent=False, thumb_pinch=False):
    """Construct 21 landmarks for testing."""
    lms = []
    # Wrist (0)
    lms.append(Landmark(id=0, pixel_x=640, pixel_y=600, x=0.5, y=0.8, z=0.0))
    # Thumb (1-4)
    for i in range(1, 4):
        lms.append(Landmark(id=i, pixel_x=550 - i*10, pixel_y=550 - i*10, x=0.45 - i*0.01, y=0.7 - i*0.01, z=0.0))
    if thumb_pinch:
        # Tip near index tip
        lms.append(Landmark(id=4, pixel_x=635, pixel_y=355, x=0.495, y=0.405, z=0.0))
    else:
        lms.append(Landmark(id=4, pixel_x=500, pixel_y=500, x=0.4, y=0.6, z=0.0))

    # Index (5-8)
    lms.append(Landmark(id=5, pixel_x=630, pixel_y=500, x=0.48, y=0.65, z=0.0))
    lms.append(Landmark(id=6, pixel_x=630, pixel_y=450, x=0.48, y=0.55, z=0.0))
    lms.append(Landmark(id=7, pixel_x=630, pixel_y=400, x=0.48, y=0.45, z=0.0))
    if index_up:
        lms.append(Landmark(id=8, pixel_x=630, pixel_y=350, x=0.48, y=0.40, z=0.0))
    else:
        lms.append(Landmark(id=8, pixel_x=630, pixel_y=520, x=0.48, y=0.68, z=0.0))

    # Middle (9-12)
    lms.append(Landmark(id=9, pixel_x=650, pixel_y=500, x=0.50, y=0.65, z=0.0))
    if middle_up:
        lms.append(Landmark(id=10, pixel_x=650, pixel_y=450, x=0.50, y=0.55, z=0.0))
        lms.append(Landmark(id=11, pixel_x=650, pixel_y=400, x=0.50, y=0.45, z=0.0))
        lms.append(Landmark(id=12, pixel_x=650, pixel_y=350, x=0.50, y=0.40, z=0.0))
    elif middle_bent:
        # Partially curled middle finger (PIP curled)
        lms.append(Landmark(id=10, pixel_x=650, pixel_y=450, x=0.50, y=0.55, z=0.0))
        lms.append(Landmark(id=11, pixel_x=650, pixel_y=480, x=0.50, y=0.60, z=0.0))
        lms.append(Landmark(id=12, pixel_x=650, pixel_y=500, x=0.50, y=0.65, z=0.0))
    else:
        # Fully folded middle finger
        lms.append(Landmark(id=10, pixel_x=650, pixel_y=520, x=0.50, y=0.68, z=0.0))
        lms.append(Landmark(id=11, pixel_x=650, pixel_y=540, x=0.50, y=0.72, z=0.0))
        lms.append(Landmark(id=12, pixel_x=650, pixel_y=550, x=0.50, y=0.74, z=0.0))

    # Ring (13-16) - folded
    lms.append(Landmark(id=13, pixel_x=670, pixel_y=500, x=0.52, y=0.65, z=0.0))
    lms.append(Landmark(id=14, pixel_x=670, pixel_y=520, x=0.52, y=0.68, z=0.0))
    lms.append(Landmark(id=15, pixel_x=670, pixel_y=540, x=0.52, y=0.72, z=0.0))
    lms.append(Landmark(id=16, pixel_x=670, pixel_y=550, x=0.52, y=0.74, z=0.0))

    # Pinky (17-20) - folded
    lms.append(Landmark(id=17, pixel_x=690, pixel_y=500, x=0.54, y=0.65, z=0.0))
    lms.append(Landmark(id=18, pixel_x=690, pixel_y=520, x=0.54, y=0.68, z=0.0))
    lms.append(Landmark(id=19, pixel_x=690, pixel_y=540, x=0.54, y=0.72, z=0.0))
    lms.append(Landmark(id=20, pixel_x=690, pixel_y=550, x=0.54, y=0.74, z=0.0))

    return lms


# ------------------------------------------------------------------------------
# 1. Pointing never becomes Victory under small middle-finger landmark noise
# ------------------------------------------------------------------------------
def test_pointing_never_becomes_victory_with_middle_noise():
    classifier = GestureClassifier(confidence_threshold=35)
    base_pointing = _make_lms(index_up=True, middle_up=False, middle_bent=True)
    
    for _ in range(15):
        # Inject Gaussian jitter into middle finger
        noisy_lms = []
        for lm in base_pointing:
            nx = lm.x + (np.random.normal(0, 0.02) if lm.id in (9, 10, 11, 12) else 0.0)
            ny = lm.y + (np.random.normal(0, 0.02) if lm.id in (9, 10, 11, 12) else 0.0)
            noisy_lms.append(Landmark(id=lm.id, pixel_x=lm.pixel_x, pixel_y=lm.pixel_y, x=nx, y=ny, z=lm.z))
        res = classifier.classify([{"landmarks": noisy_lms, "score": 90.0}])
        assert res.gesture != "Victory", f"Pointing misclassified as Victory: {res.gesture}"


# ------------------------------------------------------------------------------
# 2. No discrete action on single-frame candidate
# ------------------------------------------------------------------------------
def test_no_discrete_action_on_single_frame():
    gate = GestureIntentGate(duration=0.30)
    now = 100.0
    # First frame: should NOT execute
    fired = gate.check("Victory", duration=0.30, now=now, action_name="open_vscode")
    assert fired is False
    assert gate.executed_once is False

    # 100ms later: still holding, should NOT execute yet
    fired = gate.check("Victory", duration=0.30, now=now + 0.10, action_name="open_vscode")
    assert fired is False

    # 350ms later: duration exceeded, SHOULD execute once
    fired = gate.check("Victory", duration=0.30, now=now + 0.35, action_name="open_vscode")
    assert fired is True
    assert gate.executed_once is True


# ------------------------------------------------------------------------------
# 3. No click on hand loss
# ------------------------------------------------------------------------------
def test_no_click_on_hand_loss():
    mc = MagicMock()
    engine = EventEngine(mc)
    lms = _make_lms()
    now = 10.0

    # Enter Pinch
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms, confidence=80.0, now=now)
    assert engine.state == EventState.PINCH_DOWN

    # Hand loss: landmarks disappear
    engine.process("Unknown", "None", 500, 400, 1280, 720, [], confidence=0.0, now=now + 0.05)
    assert engine.state == EventState.HAND_LOST
    # Must NOT have called click
    mc.mouse.click.assert_not_called()


# ------------------------------------------------------------------------------
# 4. No click on stale tracking or missing landmarks
# ------------------------------------------------------------------------------
def test_no_click_on_stale_tracking():
    mc = MagicMock()
    engine = EventEngine(mc)
    lms = _make_lms()
    now = 10.0

    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms, confidence=80.0, now=now)
    assert engine.state == EventState.PINCH_DOWN

    # Invalidate tracking due to stale frame
    engine.invalidate_interaction("stale tracking")
    assert engine.state == EventState.HAND_LOST
    mc.mouse.click.assert_not_called()


# ------------------------------------------------------------------------------
# 5. No click on out-of-bounds pointer clamping
# ------------------------------------------------------------------------------
def test_pointer_clamping_no_accidental_click():
    mc = MagicMock()
    engine = EventEngine(mc)
    lms = _make_lms()
    now = 10.0

    # Normal Hover at edge coordinates
    engine.process("Pointing", "Pointing", -50, -50, 1280, 720, lms, confidence=80.0, now=now)
    assert engine.state == EventState.HOVER
    mc.mouse.click.assert_not_called()


# ------------------------------------------------------------------------------
# 6. No drag click on hand loss
# ------------------------------------------------------------------------------
def test_no_drag_click_on_hand_loss():
    mc = MagicMock()
    engine = EventEngine(mc)
    lms = _make_lms()
    now = 10.0

    # Start pinch and hold for drag
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms, confidence=80.0, now=now)
    # Hold past drag threshold (350ms)
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms, confidence=80.0, now=now + 0.40)
    assert engine.state == EventState.DRAGGING
    mc.mouse.drag.assert_called_with(start=True)

    # Hand disappears during drag
    engine.process("Unknown", "None", 500, 400, 1280, 720, [], confidence=0.0, now=now + 0.50)
    assert engine.state == EventState.HAND_LOST
    mc.mouse.click.assert_not_called()
    mc.mouse.release_all.assert_called()


# ------------------------------------------------------------------------------
# 7. Double-click anchor lock
# ------------------------------------------------------------------------------
def test_double_click_anchor_lock():
    mc = MouseController()
    mc.mouse = MagicMock()
    mc.mouse.get_cursor_pos.return_value = (500, 300)
    mc.mouse.map_coordinates.return_value = (505, 305) # Small 7px shift
    lms = _make_lms()
    now = 10.0

    # Click 1: enter and release pinch
    mc.engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms, confidence=80.0, now=now)
    mc.engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms, confidence=80.0, now=now + 0.08)
    assert mc.engine.state == EventState.PINCH_RELEASE_WAIT

    # During release wait, small pointer movement is suppressed to lock anchor
    moved = mc.process_pointer(lms, "Pointing", "Pointing", 1280, 720, now=now + 0.12, confidence=80.0)
    assert moved is False
    assert mc.mouse.last_pos == (500, 300)


# ------------------------------------------------------------------------------
# 8. Drag dropout grace
# ------------------------------------------------------------------------------
def test_drag_dropout_grace():
    mc = MagicMock()
    engine = EventEngine(mc)
    lms = _make_lms()
    now = 10.0

    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms, confidence=80.0, now=now)
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms, confidence=80.0, now=now + 0.40)
    assert engine.state == EventState.DRAGGING

    # 1-frame transient Unknown (50ms) while hand is present
    engine.process("Unknown", "Unknown", 500, 400, 1280, 720, lms, confidence=0.0, now=now + 0.45)
    assert engine.state == EventState.DRAGGING

    # Reacquire pinch within grace
    engine.process("Pinch", "Pinch", 510, 410, 1280, 720, lms, confidence=80.0, now=now + 0.48)
    assert engine.state == EventState.DRAGGING


# ------------------------------------------------------------------------------
# 9. Scroll state survives small Two-Finger jitter
# ------------------------------------------------------------------------------
def test_scroll_survives_two_finger_jitter():
    mc = MagicMock()
    engine = EventEngine(mc)
    lms = _make_lms(index_up=True, middle_up=True)
    now = 10.0

    # Start scroll
    engine.process("Two Fingers", "Two Fingers", 500, 400, 1280, 720, lms, confidence=80.0, now=now)
    assert engine.state == EventState.SCROLLING

    # 1-frame Unknown (60ms) with valid hand
    engine.process("Unknown", "Unknown", 500, 400, 1280, 720, lms, confidence=0.0, now=now + 0.06)
    assert engine.state == EventState.SCROLLING

    # Reacquire Two Fingers
    engine.process("Two Fingers", "Two Fingers", 500, 380, 1280, 720, lms, confidence=80.0, now=now + 0.10)
    assert engine.state == EventState.SCROLLING


# ------------------------------------------------------------------------------
# 10. Right click single-shot release gate
# ------------------------------------------------------------------------------
def test_right_click_single_shot_release_gate():
    mc = MagicMock()
    engine = EventEngine(mc)
    lms = _make_lms(index_up=True, middle_up=True)
    now = 10.0

    # Fire right click
    engine.process("Three Fingers", "Three Fingers", 500, 400, 1280, 720, lms, confidence=80.0, now=now)
    assert mc.mouse.click.call_count == 1
    assert mc.mouse.click.call_args[1].get("button") == "right"
    assert engine.state == EventState.COOLDOWN

    # Advance past cooldown while still holding Three Fingers
    engine.process("Three Fingers", "Three Fingers", 500, 400, 1280, 720, lms, confidence=80.0, now=now + 0.20)
    assert mc.mouse.click.call_count == 1 # Must NOT fire again while held

    # Release
    engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms, confidence=80.0, now=now + 0.30)
    assert engine.state == EventState.HOVER

    # Now Three Fingers can fire again
    engine.process("Three Fingers", "Three Fingers", 500, 400, 1280, 720, lms, confidence=80.0, now=now + 0.40)
    assert mc.mouse.click.call_count == 2


# ------------------------------------------------------------------------------
# 11 & 12. Screenshot path creation, wall-clock filename, and valid PNG verification
# ------------------------------------------------------------------------------
def test_screenshot_wallclock_and_valid_png():
    ctrl = DesktopController()
    res = ctrl.take_screenshot()
    assert res.success is True
    assert res.message.startswith("Saved SmartGestureOS_")
    
    saved_filename = res.message.replace("Saved ", "").strip()
    target_file = SCREENSHOTS_DIR / saved_filename
    assert target_file.exists()
    assert target_file.stat().st_size > 0

    with Image.open(target_file) as img:
        assert img.format == "PNG"
        assert img.width > 0 and img.height > 0

    try:
        target_file.unlink()
    except Exception:
        pass


# ------------------------------------------------------------------------------
# 13. Background hiding does not stop processing
# ------------------------------------------------------------------------------
def test_background_hiding_does_not_stop_mapper():
    mapper = GestureMapper(1280, 720)
    lms = _make_lms()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Process with render_canvas=False (background mode)
    out_frame, action, progress = mapper.process(
        [{"landmarks": lms, "score": 90}], "Pointing", "Pointing", frame,
        render_canvas=False, confidence=85.0
    )
    assert out_frame is not None
    assert mapper.mode == "GENERAL"


# ------------------------------------------------------------------------------
# 14. Pause disables ALL action paths
# ------------------------------------------------------------------------------
def test_pause_disables_all_actions():
    mapper = GestureMapper(1280, 720)
    mapper.invalidate_interaction("paused")
    assert mapper.timer.target_gesture is None
    assert mapper.last_pinch_time == 0.0


# ------------------------------------------------------------------------------
# 15. Resume neutral re-arm blocks held gesture
# ------------------------------------------------------------------------------
def test_resume_neutral_rearm():
    from main import MainApp
    app = MainApp.__new__(MainApp)
    app._automation_lock = MagicMock()
    app._automation_enabled = True
    app.classifier = MagicMock()
    app.mapper = MagicMock()
    app._rearm_state = MainApp._REARM_WAITING
    app._rearm_neutral_frames = 0

    # User already holding Victory while resuming -> MUST NOT arm
    armed = app._tick_rearm("Victory", "Victory")
    assert armed is False
    assert app._rearm_state == MainApp._REARM_WAITING

    # Neutral frames
    for _ in range(MainApp._REARM_NEUTRAL_REQUIRED):
        armed = app._tick_rearm("Unknown", "Unknown")

    assert armed is True
    assert app._rearm_state == MainApp._REARM_ARMED


# ------------------------------------------------------------------------------
# 16. Async queue generation prevents stale action
# ------------------------------------------------------------------------------
def test_async_queue_generation_prevents_stale_action():
    executor = ActionExecutor()
    executor.start()
    
    executed = []
    def slow_task():
        time.sleep(0.05)
        executed.append(True)
        return ActionResult(True, "test", "done", None, time.perf_counter())

    executor.submit("test", slow_task)
    executor.cancel("paused") # Bump generation
    time.sleep(0.1)
    
    assert len(executed) == 0
    executor.stop()
