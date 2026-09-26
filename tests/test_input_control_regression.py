"""
tests/test_input_control_regression.py
Regression tests for P0 Presentation Input Controls:
- cursor path
- single click
- double click
- drag start/release
- hand loss during drag
- scroll
- right-click gate
"""

import time
import pytest
from unittest.mock import MagicMock, patch, call
from src.event_engine import EventEngine, EventState
from src.models import Landmark


def _make_mock_mouse_and_engine():
    """Create a fully mocked VirtualMouse and EventEngine."""
    fake_user32 = MagicMock()
    fake_user32.SetCursorPos = MagicMock(return_value=1)
    fake_user32.mouse_event = MagicMock()

    with patch("ctypes.windll") as mock_windll, \
         patch("screeninfo.get_monitors", return_value=[MagicMock(x=0, y=0, width=1920, height=1080, is_primary=True)]):
        mock_windll.user32 = fake_user32

        from src.virtual_mouse import VirtualMouse
        vm = VirtualMouse(min_cutoff=0.8, beta=0.2, deadzone=1.0)
        vm.user32 = fake_user32

        from src.mouse_controller import MouseController
        mc = MouseController.__new__(MouseController)
        mc.mouse = vm

        engine = EventEngine(mc)
        engine.mouse = mc
        mc.engine = engine

        return engine, mc, vm, fake_user32


def _make_landmarks(index_x=640, index_y=360, y_norm=0.5):
    """Generate 21 landmarks with customizable index finger position."""
    lms = []
    for i in range(21):
        lms.append(Landmark(
            id=i, pixel_x=index_x, pixel_y=index_y,
            x=index_x / 1280.0, y=y_norm, z=0.0
        ))
    return lms


class TestInputControlRegression:
    def test_pointer_smoothing_setting_updates_live_filter_cutoff(self):
        engine, mc, vm, _ = _make_mock_mouse_and_engine()
        vm.smoother.update(1.0, 0.0, 0.0)

        with patch("config.SETTINGS", {"gestures": {"sensitivity": 0.7, "smoothing": 1}}):
            mc.on_settings_changed()
        responsive_cutoff = vm.smoother.filter_x.min_cutoff

        with patch("config.SETTINGS", {"gestures": {"sensitivity": 0.7, "smoothing": 20}}):
            mc.on_settings_changed()
        smooth_cutoff = vm.smoother.filter_x.min_cutoff

        assert responsive_cutoff > smooth_cutoff
        assert vm.smoother.min_cutoff == smooth_cutoff

    def test_cursor_path(self):
        """Test Pointing gesture translates index fingertip to SetCursorPos along a moving path."""
        engine, mc, vm, fake_user32 = _make_mock_mouse_and_engine()

        # Step 1: Move along a path from (640, 360) to (800, 450)
        path = [(640, 360), (680, 390), (740, 420), (800, 450)]
        for px, py in path:
            lms = _make_landmarks(index_x=px, index_y=py)
            mc.process_landmarks(lms, stable_gesture="Pointing", raw_gesture="Pointing", frame_w=1280, frame_h=720)

        assert fake_user32.SetCursorPos.call_count >= 3
        # Ensure moving coordinates reached SetCursorPos
        first_call = fake_user32.SetCursorPos.call_args_list[0][0]
        last_call = fake_user32.SetCursorPos.call_args_list[-1][0]
        assert last_call[0] > first_call[0], "Cursor X should have moved to the right"
        assert last_call[1] > first_call[1], "Cursor Y should have moved downward"

    def test_single_click(self):
        """Test one short pinch results in exactly one left click (LEFTDOWN + LEFTUP)."""
        engine, mc, vm, fake_user32 = _make_mock_mouse_and_engine()
        lms = _make_landmarks()

        # Pinch enter
        engine.process("Pinch", "Pinch", 640, 360, 1280, 720, lms)
        assert engine.state == EventState.PINCH_DOWN

        # Pinch release (< 350ms)
        engine.process("Pointing", "Pointing", 640, 360, 1280, 720, lms)
        assert engine.state == EventState.PINCH_RELEASE_WAIT

        # Double click window expires
        engine.pinch_release_time -= (engine.double_click_window_ms + 0.05)
        fake_user32.mouse_event.reset_mock()

        # Process next frame
        engine.process("Pointing", "Pointing", 640, 360, 1280, 720, lms)
        assert engine.state == EventState.HOVER

        # Must have exactly 1 click (1 LEFTDOWN + 1 LEFTUP)
        left_events = [c[0][0] for c in fake_user32.mouse_event.call_args_list if c[0][0] in (0x0002, 0x0004)]
        assert left_events == [0x0002, 0x0004]

    def test_double_click(self):
        """Test two short pinches produce double click without extra single clicks."""
        engine, mc, vm, fake_user32 = _make_mock_mouse_and_engine()
        lms = _make_landmarks()

        # First pinch
        engine.process("Pinch", "Pinch", 640, 360, 1280, 720, lms)
        # Release
        engine.process("Pointing", "Pointing", 640, 360, 1280, 720, lms)
        assert engine.state == EventState.PINCH_RELEASE_WAIT

        fake_user32.mouse_event.reset_mock()

        # Second pinch within double-click window
        engine.process("Pinch", "Pinch", 640, 360, 1280, 720, lms)
        assert engine.state == EventState.COOLDOWN

        # Double click produces 4 events: DOWN, UP, DOWN, UP
        left_events = [c[0][0] for c in fake_user32.mouse_event.call_args_list if c[0][0] in (0x0002, 0x0004)]
        assert left_events == [0x0002, 0x0004, 0x0002, 0x0004]

    def test_drag_start_and_release(self):
        """Test holding pinch >= 350ms begins drag, moves cursor, and release drops drag without click."""
        engine, mc, vm, fake_user32 = _make_mock_mouse_and_engine()
        lms = _make_landmarks(640, 360)

        # Enter pinch
        engine.process("Pinch", "Pinch", 640, 360, 1280, 720, lms)
        assert engine.state == EventState.PINCH_DOWN

        # Simulate hold >= 350ms
        engine.pinch_down_time -= (engine.drag_hold_ms + 0.05)
        fake_user32.mouse_event.reset_mock()

        # Next frame triggers DRAGGING
        engine.process("Pinch", "Pinch", 650, 370, 1280, 720, lms)
        assert engine.state == EventState.DRAGGING
        assert vm.is_dragging is True

        # Must have sent LEFTDOWN
        left_down_calls = [c for c in fake_user32.mouse_event.call_args_list if c[0][0] == 0x0002]
        assert len(left_down_calls) == 1

        # Release pinch
        fake_user32.mouse_event.reset_mock()
        engine.process("Pointing", "Pointing", 700, 400, 1280, 720, lms)
        assert engine.state == EventState.COOLDOWN
        assert vm.is_dragging is False

        # Must have sent LEFTUP
        left_up_calls = [c for c in fake_user32.mouse_event.call_args_list if c[0][0] == 0x0004]
        assert len(left_up_calls) == 1

    def test_hand_loss_during_drag(self):
        """Test drag state is safely aborted and left button released if hand disappears."""
        engine, mc, vm, fake_user32 = _make_mock_mouse_and_engine()
        lms = _make_landmarks()

        # Enter drag
        engine.process("Pinch", "Pinch", 640, 360, 1280, 720, lms)
        engine.pinch_down_time -= (engine.drag_hold_ms + 0.05)
        engine.process("Pinch", "Pinch", 640, 360, 1280, 720, lms)
        assert engine.state == EventState.DRAGGING
        assert vm.is_dragging is True

        fake_user32.mouse_event.reset_mock()

        # Hand lost occurs (e.g. hand moved out of camera or camera lost)
        engine.on_hand_lost()
        assert engine.state == EventState.HAND_LOST
        assert vm.is_dragging is False

        # LEFTUP must have been issued
        left_up_calls = [c for c in fake_user32.mouse_event.call_args_list if c[0][0] == 0x0004]
        assert len(left_up_calls) >= 1

    def test_scroll_direction_and_freeze(self):
        """Test Two Fingers recognizes scrolling, sends correct wheel delta, and freezes cursor position."""
        engine, mc, vm, fake_user32 = _make_mock_mouse_and_engine()

        # Enter Two Fingers at y=0.4
        lms_start = _make_landmarks(640, 360, y_norm=0.4)
        engine.process("Two Fingers", "Two Fingers", 640, 360, 1280, 720, lms_start)
        assert engine.state == EventState.SCROLLING

        fake_user32.SetCursorPos.reset_mock()
        fake_user32.mouse_event.reset_mock()

        # Move hand downward (y increases from 0.40 to 0.45, delta > 0.03)
        lms_down = _make_landmarks(640, 400, y_norm=0.45)
        engine.process("Two Fingers", "Two Fingers", 640, 400, 1280, 720, lms_down)

        # Cursor position must NOT move during scrolling
        assert fake_user32.SetCursorPos.call_count == 0, "Cursor should not move while actively scrolling"

        # Downward hand motion should produce downward scroll (-1 * 120 = 0xffffff88)
        wheel_calls = [c[0][3] for c in fake_user32.mouse_event.call_args_list if c[0][0] == 0x0800]
        assert len(wheel_calls) >= 1
        assert wheel_calls[0] == (int(-1 * 120) & 0xFFFFFFFF)

        # Move hand upward (y decreases from 0.45 to 0.39, delta < -0.03)
        fake_user32.mouse_event.reset_mock()
        lms_up = _make_landmarks(640, 300, y_norm=0.39)
        engine.process("Two Fingers", "Two Fingers", 640, 300, 1280, 720, lms_up)

        wheel_up_calls = [c[0][3] for c in fake_user32.mouse_event.call_args_list if c[0][0] == 0x0800]
        assert len(wheel_up_calls) >= 1
        assert wheel_up_calls[0] == (int(1 * 120) & 0xFFFFFFFF)

    def test_right_click_gate(self):
        """Test Three Fingers fires exactly once and requires release before re-arming."""
        engine, mc, vm, fake_user32 = _make_mock_mouse_and_engine()
        lms = _make_landmarks()

        # First press
        engine.process("Three Fingers", "Three Fingers", 640, 360, 1280, 720, lms)
        assert engine.state == EventState.COOLDOWN

        # Must have fired right click (RIGHTDOWN + RIGHTUP)
        right_events = [c[0][0] for c in fake_user32.mouse_event.call_args_list if c[0][0] in (0x0008, 0x0010)]
        assert right_events == [0x0008, 0x0010]

        # Advance past cooldown but keep holding Three Fingers
        engine.last_state_change -= (engine.cooldown_duration + 0.05)
        fake_user32.mouse_event.reset_mock()

        engine.process("Three Fingers", "Three Fingers", 640, 360, 1280, 720, lms)
        right_events_held = [c[0][0] for c in fake_user32.mouse_event.call_args_list if c[0][0] in (0x0008, 0x0010)]
        assert len(right_events_held) == 0, "Right click must not repeat while held"

        # Release Three Fingers to re-arm
        engine.process("Pointing", "Pointing", 640, 360, 1280, 720, lms)
        engine.last_state_change -= (engine.cooldown_duration + 0.05)
        engine.process("Pointing", "Pointing", 640, 360, 1280, 720, lms)
        assert engine.state == EventState.HOVER

        # Now re-enter Three Fingers -> fires again
        fake_user32.mouse_event.reset_mock()
        engine.process("Three Fingers", "Three Fingers", 640, 360, 1280, 720, lms)
        new_right_events = [c[0][0] for c in fake_user32.mouse_event.call_args_list if c[0][0] in (0x0008, 0x0010)]
        assert new_right_events == [0x0008, 0x0010], "Right click should fire after release and re-enter"
