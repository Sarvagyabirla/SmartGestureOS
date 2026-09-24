"""
tests/test_event_engine.py
Deterministic unit tests for EventEngine.
All mouse operations are mocked — no physical desktop control occurs.
"""
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine():
    """Create an EventEngine with a fully mocked MouseController."""
    # Patch ctypes / screeninfo so VirtualMouse never touches WinAPI
    fake_user32 = MagicMock()
    fake_user32.SetCursorPos = MagicMock(return_value=1)
    fake_user32.mouse_event = MagicMock()
    fake_user32.GetCursorPos = MagicMock(return_value=0)

    with patch("ctypes.windll") as mock_windll, \
         patch("screeninfo.get_monitors", return_value=[MagicMock(width=1920, height=1080)]):
        mock_windll.user32 = fake_user32
        mock_windll.dxva2 = MagicMock()

        from src.virtual_mouse import VirtualMouse
        vm = VirtualMouse.__new__(VirtualMouse)
        vm.smoother = MagicMock()
        vm.smoother.update = MagicMock(return_value=(500.0, 400.0))
        vm.screen_w = 1920
        vm.screen_h = 1080
        vm.deadzone = 1.0
        vm.last_pos = None
        vm.is_dragging = False
        vm.user32 = fake_user32

        from src.mouse_controller import MouseController
        mc = MouseController.__new__(MouseController)
        mc.mouse = vm

        from src.event_engine import EventEngine, EventState
        engine = EventEngine(mc)
        engine.mouse = mc
        return engine, mc, vm, fake_user32


def _lms(y=0.5):
    """Return a minimal 21-point landmark list with index tip at given y."""
    lm = MagicMock()
    lm.y = y
    lms = [MagicMock() for _ in range(21)]
    lms[8] = lm
    return lms


# ---------------------------------------------------------------------------
# TEST 1: Single Click
# ---------------------------------------------------------------------------

def test_single_click():
    """Pinch → release → wait beyond double window → exactly one left click."""
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    lms = _lms()

    # Pinch down
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.PINCH_DOWN

    # Release
    engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.PINCH_RELEASE_WAIT

    # Wait beyond double-click window
    engine.pinch_release_time -= (engine.double_click_window_ms + 0.1)

    # Tick again — should perform single click
    engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.HOVER

    # Verify left click was called
    left_click_calls = [c for c in user32.mouse_event.call_args_list
                        if c[0][0] in (0x0002, 0x0004)]
    assert len(left_click_calls) >= 2, "Expected LEFTDOWN + LEFTUP for single click"


# ---------------------------------------------------------------------------
# TEST 2: Double Click
# ---------------------------------------------------------------------------

def test_double_click_no_extra_single():
    """Pinch → release → second Pinch within window → double click, no extra single."""
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    lms = _lms()

    # First pinch
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms)
    # Release
    engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.PINCH_RELEASE_WAIT

    # Second Pinch within window (immediately)
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.COOLDOWN

    # Verify double_click path (4 mouse_event calls: 2×down 2×up)
    calls = [c for c in user32.mouse_event.call_args_list
             if c[0][0] in (0x0002, 0x0004)]
    assert len(calls) == 4, f"Expected 4 left mouse events for double click, got {len(calls)}"


# ---------------------------------------------------------------------------
# TEST 3: Drag begins after hold
# ---------------------------------------------------------------------------

def test_drag_starts_after_hold():
    """Pinch held beyond drag threshold → drag starts."""
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    lms = _lms()

    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms)
    # Wind time back to simulate hold beyond threshold
    engine.pinch_down_time -= (engine.drag_hold_ms + 0.05)

    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.DRAGGING
    assert vm.is_dragging is True

    leftdown = [c for c in user32.mouse_event.call_args_list if c[0][0] == 0x0002]
    assert len(leftdown) >= 1, "Expected LEFTDOWN for drag start"


# ---------------------------------------------------------------------------
# TEST 4: Drag release
# ---------------------------------------------------------------------------

def test_drag_release():
    """Dragging state → pinch released → mouse button UP."""
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    lms = _lms()

    # Get into dragging
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms)
    engine.pinch_down_time -= (engine.drag_hold_ms + 0.05)
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.DRAGGING

    user32.mouse_event.reset_mock()

    # Release
    engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.COOLDOWN

    leftup = [c for c in user32.mouse_event.call_args_list if c[0][0] == 0x0004]
    assert len(leftup) >= 1, "Expected LEFTUP for drag release"
    assert vm.is_dragging is False


# ---------------------------------------------------------------------------
# TEST 5: Hand lost during drag
# ---------------------------------------------------------------------------

def test_hand_lost_during_drag():
    """DRAGGING + on_hand_lost() → LEFTUP immediately → HAND_LOST state."""
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    lms = _lms()

    # Get into dragging
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms)
    engine.pinch_down_time -= (engine.drag_hold_ms + 0.05)
    engine.process("Pinch", "Pinch", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.DRAGGING

    user32.mouse_event.reset_mock()
    engine.on_hand_lost()

    assert engine.state == EventState.HAND_LOST
    leftup = [c for c in user32.mouse_event.call_args_list if c[0][0] == 0x0004]
    assert len(leftup) >= 1, "Expected LEFTUP on hand lost during drag"


# ---------------------------------------------------------------------------
# TEST 6: Hand reacquisition
# ---------------------------------------------------------------------------

def test_hand_reacquisition():
    """HAND_LOST → valid hand with stable gesture → transitions to HOVER."""
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    engine.on_hand_lost()
    assert engine.state == EventState.HAND_LOST

    lms = _lms()
    engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.HOVER


# ---------------------------------------------------------------------------
# TEST 7: Two Fingers scroll ticks
# ---------------------------------------------------------------------------

def test_two_fingers_scroll_ticks():
    """Two Fingers with normalized Y movement → scroll ticks generated."""
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    lms = _lms(y=0.5)
    # Enter scrolling
    engine.process("Two Fingers", "Two Fingers", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.SCROLLING

    # Simulate downward movement beyond threshold
    for i in range(10):
        lms2 = _lms(y=0.5 + (i + 1) * 0.01)
        engine.process("Two Fingers", "Two Fingers", 500, 400, 1280, 720, lms2)

    scroll_calls = [c for c in user32.mouse_event.call_args_list if c[0][0] == 0x0800]
    assert len(scroll_calls) >= 1, "Expected scroll events from two-finger movement"


# ---------------------------------------------------------------------------
# TEST 8: Scroll accumulator reset
# ---------------------------------------------------------------------------

def test_scroll_accumulator_reset():
    """Two Fingers → different gesture → scroll accumulator resets."""
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    lms = _lms(y=0.5)
    engine.process("Two Fingers", "Two Fingers", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.SCROLLING

    engine.scroll_accumulator = 99.9  # Force a large value

    # Switch gesture
    engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.HOVER
    assert engine.scroll_start_y is None
    assert engine.scroll_accumulator == 0.0


# ---------------------------------------------------------------------------
# TEST 9: Right Click from Three Fingers
# ---------------------------------------------------------------------------

def test_right_click():
    """Three Fingers → exactly one right click."""
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    lms = _lms()
    engine.process("Three Fingers", "Three Fingers", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.COOLDOWN

    right_clicks = [c for c in user32.mouse_event.call_args_list
                    if c[0][0] in (0x0008, 0x0010)]
    assert len(right_clicks) >= 2, "Expected RIGHTDOWN + RIGHTUP"


# ---------------------------------------------------------------------------
# TEST 10: Right-click release gate (F-06 fix)
# ---------------------------------------------------------------------------

def test_right_click_no_repeat_while_held():
    """
    Three Fingers held continuously must not fire a second right-click,
    even after COOLDOWN expires. Only after Three Fingers is released and
    re-entered should a new right-click be allowed.
    """
    engine, mc, vm, user32 = _make_engine()
    from src.event_engine import EventState

    lms = _lms()

    # First press → right-click fires
    engine.process("Three Fingers", "Three Fingers", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.COOLDOWN

    right_click_count_after_first = len([
        c for c in user32.mouse_event.call_args_list
        if c[0][0] in (0x0008, 0x0010)
    ])
    assert right_click_count_after_first >= 2, "Expected at least one right-click"

    # Advance time past cooldown to let engine return to HOVER
    engine.last_state_change -= (engine.cooldown_duration + 0.1)
    engine.process("Three Fingers", "Three Fingers", 500, 400, 1280, 720, lms)
    # Should be back in HOVER or COOLDOWN, but NOT fire a second right-click
    right_click_count_held = len([
        c for c in user32.mouse_event.call_args_list
        if c[0][0] in (0x0008, 0x0010)
    ])
    assert right_click_count_held == right_click_count_after_first, (
        "F-06: Second right-click fired while Three Fingers still held! "
        f"Expected {right_click_count_after_first} events, got {right_click_count_held}"
    )

    # Now release Three Fingers (any other gesture)
    engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms)
    # Ensure cooldown clears
    engine.last_state_change -= (engine.cooldown_duration + 0.1)
    engine.process("Pointing", "Pointing", 500, 400, 1280, 720, lms)
    assert engine.state == EventState.HOVER

    # Re-enter Three Fingers — should fire a new right-click
    engine.process("Three Fingers", "Three Fingers", 500, 400, 1280, 720, lms)
    right_click_count_second = len([
        c for c in user32.mouse_event.call_args_list
        if c[0][0] in (0x0008, 0x0010)
    ])
    assert right_click_count_second > right_click_count_after_first, (
        "F-06: After release+re-enter, a new right-click should have fired"
    )
