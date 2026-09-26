"""
tests/test_emergency_pause_regression.py — P0 Emergency Pause & Hotkey Regression Tests.

Validates:
1. pause idle: pauses from idle, releases all states
2. pause during drag: immediately releases left mouse button, clears dragging, resets EventEngine
3. pause during scroll: clears scroll accumulator, resets EventEngine to HAND_LOST
4. pause during held action: resets hold timers in GestureMapper, prevents action execution
5. resume neutral gate: blocks actions on resume if gesture is held; requires 5 neutral frames to re-arm
6. hotkey cleanup at shutdown: unregisters hook handle cleanly, idempotent on second shutdown
7. idempotent toggle: repeated set_automation_enabled calls with same state do not duplicate operations
8. UI pause button direct callback: calls set_automation_enabled directly without keyboard.send simulation
9. UI dashboard visual reflection: button text changes to Resume/Pause, status label reflects state
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.event_engine import EventEngine, EventState
from src.gesture_classifier import GestureClassifier
from src.gesture_mapper import GestureMapper
from src.models import Landmark
import main as m_module


def _21_landmarks(x=0.5, y=0.5):
    return [
        Landmark(id=i, x=x, y=y, z=0.0, pixel_x=int(x * 640), pixel_y=int(y * 480))
        for i in range(21)
    ]


@pytest.fixture
def simulated_app():
    """Build a lightweight MainApp instance without opening hardware or threads."""
    app = object.__new__(m_module.MainApp)
    app._automation_lock = threading.RLock()
    app._tracking_generation = 0
    app._automation_enabled = True
    app._rearm_state = m_module.MainApp._REARM_ARMED
    app._rearm_neutral_frames = 0
    app._REARM_NEUTRAL_REQUIRED = m_module.MainApp._REARM_NEUTRAL_REQUIRED
    app._shutdown_started = False
    app._shutdown_lock = threading.Lock()
    app._hotkey_handle = None

    # Concrete subsystems with mocked OS mouse_event
    with patch("ctypes.windll.user32.mouse_event"):
        app.mapper = GestureMapper(640, 480)
        app.classifier = GestureClassifier()

    return app


# ── 1. Pause Idle ─────────────────────────────────────────────────────────────

def test_pause_idle(simulated_app):
    """Test pausing from an idle state releases all mouse buttons and resets temporal state."""
    app = simulated_app
    assert app.automation_enabled is True
    assert app._rearm_state == m_module.MainApp._REARM_ARMED

    with patch.object(app.mapper.mouse.mouse, "release_all") as mock_mouse_rel, \
         patch.object(app.mapper, "reset_temporal_state") as mock_mapper_rel, \
         patch.object(app.classifier, "reset") as mock_clf_reset:
        app.set_automation_enabled(False)

        assert app.automation_enabled is False
        assert app._rearm_state == m_module.MainApp._REARM_IDLE
        assert mock_mouse_rel.call_count >= 1
        mock_mapper_rel.assert_called_once()
        mock_clf_reset.assert_called_once()


# ── 2. Pause During Drag ──────────────────────────────────────────────────────

def test_pause_during_drag(simulated_app):
    """Test that pausing while in an active DRAGGING state releases mouse and resets engine."""
    app = simulated_app
    engine = app.mapper.mouse.engine
    mouse = app.mapper.mouse.mouse

    # Simulate entering drag state
    engine.state = EventState.DRAGGING
    mouse.is_dragging = True

    # Track calls to user32.mouse_event
    with patch.object(mouse.user32, "mouse_event") as mock_mouse_event:
        app.set_automation_enabled(False)

        assert app.automation_enabled is False
        assert mouse.is_dragging is False
        assert engine.state == EventState.HAND_LOST
        # mouse_event called with MOUSEEVENTF_LEFTUP (0x0004) and MOUSEEVENTF_RIGHTUP (0x0010)
        assert mock_mouse_event.call_count >= 2
        calls = [c.args[0] for c in mock_mouse_event.call_args_list]
        assert 0x0004 in calls  # MOUSEEVENTF_LEFTUP


# ── 3. Pause During Scroll ────────────────────────────────────────────────────

def test_pause_during_scroll(simulated_app):
    """Test that pausing while scrolling resets scroll accumulator and engine state."""
    app = simulated_app
    engine = app.mapper.mouse.engine

    # Simulate active scrolling
    engine.state = EventState.SCROLLING
    engine.scroll_start_y = 200.0
    engine.scroll_accumulator = 0.08

    app.set_automation_enabled(False)

    assert app.automation_enabled is False
    assert engine.state == EventState.HAND_LOST
    assert engine.scroll_start_y is None
    assert engine.scroll_accumulator == 0.0


# ── 4. Pause During Held Action ───────────────────────────────────────────────

def test_pause_during_held_action(simulated_app):
    """Test that pausing while a gesture hold timer is accumulating resets the timer."""
    app = simulated_app
    timer = app.mapper.timer

    # Simulate gesture being held
    timer.target_gesture = "Open Chrome"
    timer.start_time = time.perf_counter() - 0.2
    timer.executed_once = False

    app.set_automation_enabled(False)

    assert app.automation_enabled is False
    assert timer.target_gesture is None
    assert timer.executed_once is False


# ── 5. Resume Neutral Gate ────────────────────────────────────────────────────

def test_resume_neutral_gate(simulated_app):
    """Test that resuming requires 5 consecutive neutral frames before arming."""
    app = simulated_app
    # First pause
    app.set_automation_enabled(False)
    assert app._rearm_state == m_module.MainApp._REARM_IDLE

    # Resume
    app.set_automation_enabled(True)
    assert app.automation_enabled is True
    assert app._rearm_state == m_module.MainApp._REARM_WAITING
    assert app._rearm_neutral_frames == 0

    # User keeps holding an action gesture: must NOT arm
    for _ in range(6):
        armed = app._tick_rearm("Pointing")
        assert armed is False
        assert app._rearm_state == m_module.MainApp._REARM_WAITING
        assert app._rearm_neutral_frames == 0

    # User presents 3 neutral frames: still NOT armed
    for i in range(1, 4):
        armed = app._tick_rearm("Unknown")
        assert armed is False
        assert app._rearm_neutral_frames == i

    # User briefly jerks back into Pointing: resets count
    armed = app._tick_rearm("Pointing")
    assert armed is False
    assert app._rearm_neutral_frames == 0

    # 4 consecutive neutral frames: still waiting
    for i in range(1, 5):
        armed = app._tick_rearm("None")
        assert armed is False
        assert app._rearm_neutral_frames == i

    # 5th neutral frame: ARMS automation!
    armed = app._tick_rearm("None")
    assert armed is True
    assert app._rearm_state == m_module.MainApp._REARM_ARMED

    # Subsequent action gestures now pass immediately
    assert app._tick_rearm("Pointing") is True


# ── 6. Hotkey Cleanup at Shutdown ─────────────────────────────────────────────

def test_hotkey_cleanup_at_shutdown(simulated_app):
    """Test that shutdown unregisters the hotkey handle and is idempotent."""
    app = simulated_app
    fake_handle = object()
    app._hotkey_handle = fake_handle
    app.running = True
    app.frame_queue = MagicMock()
    app.camera = MagicMock()
    app.detector = MagicMock()
    app.process_thread = None
    app.stats_thread = None

    with patch("keyboard.remove_hotkey") as mock_remove:
        app.stop_system()

        mock_remove.assert_called_once_with(fake_handle)
        assert app._hotkey_handle is None
        assert app.running is False

        # Second call to stop_system must be a no-op (idempotent)
        app.stop_system()
        assert mock_remove.call_count == 1  # not called again


# ── 7. Idempotent Toggle ──────────────────────────────────────────────────────

def test_idempotent_toggle(simulated_app):
    """Test that calling set_automation_enabled with the current state is a no-op."""
    app = simulated_app
    assert app.automation_enabled is True

    with patch.object(app.mapper.mouse, "release_all") as mock_rel:
        # Already enabled, call True again
        app.set_automation_enabled(True)
        assert mock_rel.call_count == 0

        # Pause
        app.set_automation_enabled(False)
        assert mock_rel.call_count == 1

        # Call False again: no-op
        app.set_automation_enabled(False)
        assert mock_rel.call_count == 1


# ── 8. UI Pause Button Direct Invocation ──────────────────────────────────────

# ── 8. UI Pause Button Direct Invocation ──────────────────────────────────────

def test_ui_pause_button_direct_invocation():
    """Verify UI toggle_pause invokes set_automation_callback directly without keyboard.send."""
    from src.ui import SmartGestureApp

    callback_called = []

    ui = object.__new__(SmartGestureApp)
    ui.set_automation_callback = lambda val: callback_called.append(val)
    ui.toggle_pause_callback = None
    ui.automation_enabled = True

    with patch("keyboard.send") as mock_kb_send:
        # Click pause button
        SmartGestureApp.toggle_pause(ui)

        # Must have called set_automation_callback(False)
        assert callback_called == [False]
        # Must NEVER have called keyboard.send("ctrl+alt+g")
        mock_kb_send.assert_not_called()


# ── 9. UI Dashboard Visual Reflection ─────────────────────────────────────────

def test_ui_dashboard_visual_reflection():
    """Verify update_dashboard changes pause_btn text and status label correctly."""
    from src.ui import SmartGestureApp

    ui = object.__new__(SmartGestureApp)
    ui.mode_label = MagicMock()
    ui.confidence_bar = MagicMock()
    ui.confidence_bar.get.return_value = 0.0
    ui.gesture_label = MagicMock()
    ui.raw_gesture_label = MagicMock()
    ui.conf_label = MagicMock()
    ui.fps_label = MagicMock()
    ui.latency_label = MagicMock()
    ui.cpu_label = MagicMock()
    ui.ram_label = MagicMock()
    ui.camera_state_label = MagicMock()
    ui.automation_state_label = MagicMock()
    ui.pause_btn = MagicMock()
    ui.last_stat_update = time.time()
    ui.accent_color = "#00E5FF"
    ui.add_to_history = MagicMock()

    # Update when paused
    SmartGestureApp.update_dashboard(
        ui, mode="GENERAL", stable_gesture="None", raw_gesture="None",
        confidence=0, action="Paused", fps=30, automation_enabled=False
    )
    assert ui.automation_enabled is False
    ui.automation_state_label.configure.assert_called_with(
        text="● AUTOMATION PAUSED", text_color="#d64545"
    )
    ui.pause_btn.configure.assert_called_with(
        text="Resume (Ctrl+Alt+G)", fg_color="#2fa572", hover_color="#26855c"
    )

    # Update when resumed
    SmartGestureApp.update_dashboard(
        ui, mode="GENERAL", stable_gesture="Pointing", raw_gesture="Pointing",
        confidence=90, action="None", fps=30, automation_enabled=True
    )
    assert ui.automation_enabled is True
    ui.automation_state_label.configure.assert_called_with(
        text="● AUTOMATION ON", text_color=ui.accent_color
    )
    ui.pause_btn.configure.assert_called_with(
        text="Pause (Ctrl+Alt+G)", fg_color="#d64545", hover_color="#b33939"
    )
