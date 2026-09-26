"""Tracking interruptions must cancel pending actions and drawing coordinates."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

import config
import src.gesture_mapper as mapper_module
from src.event_engine import EventEngine, EventState
from src.models import ActionResult, Landmark


@pytest.fixture
def mapper_and_clock(monkeypatch):
    """Keep real hold timers, drawing and input state, with no desktop effects."""
    for name in (
        "MouseController", "KeyboardController", "MediaController",
        "DesktopController", "ShortcutController", "PresentationController",
        "VolumeController", "BrightnessController", "FeedbackController",
    ):
        monkeypatch.setattr(mapper_module, name, MagicMock())

    from src.settings_manager import settings_manager

    monkeypatch.setattr(settings_manager, "register_callback", lambda callback: None)
    settings = {
        "gestures": {"hold_time_ms": 300, "cooldown_ms": 500},
        "mappings": {
            "MEDIA": {"Victory": "next_track", "Call Me": "toggle_sleep"},
            "DRAW": {},
        },
    }
    monkeypatch.setattr(config, "SETTINGS", settings)
    monkeypatch.setattr(mapper_module, "SETTINGS", settings)
    clock = SimpleNamespace(now=10.0)
    monkeypatch.setattr(mapper_module.time, "perf_counter", lambda: clock.now)

    mapper = mapper_module.GestureMapper(200, 200)
    mapper.mouse.engine = EventEngine(mapper.mouse)
    mapper.media.next_track.return_value = ActionResult(True, "next_track", "Sent")
    return mapper, clock


def hand_at(x, y):
    return [{"landmarks": [
        Landmark(id=i, x=x / 200, y=y / 200, z=0.0, pixel_x=x, pixel_y=y)
        for i in range(21)
    ]}]


@pytest.mark.parametrize(
    ("gesture", "hold_seconds", "expected_action"),
    [("Victory", 0.3, "Executed: next_track"), ("Call Me", 3.0, "System Sleeping")],
)
def test_hand_loss_requires_a_fresh_complete_hold(
    mapper_and_clock, gesture, hold_seconds, expected_action
):
    mapper, clock = mapper_and_clock
    mapper.mode = "MEDIA"
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    hand = hand_at(50, 50)

    mapper.process(hand, gesture, gesture, frame)
    clock.now += hold_seconds / 2
    _, action, progress = mapper.process([], "None", "None", frame)
    assert action is None
    assert progress == 0.0

    # Time with no hand must not count toward either the action or sleep hold.
    clock.now += 10
    _, action, _ = mapper.process(hand, gesture, gesture, frame)
    assert action is None
    clock.now += hold_seconds / 2
    _, action, _ = mapper.process(hand, gesture, gesture, frame)
    assert action is None
    clock.now += hold_seconds / 2 + 0.01
    _, action, _ = mapper.process(hand, gesture, gesture, frame)
    assert action == expected_action


def test_reacquired_hand_starts_a_separate_stroke(mapper_and_clock):
    mapper, clock = mapper_and_clock
    mapper.mode = "DRAW"
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    mapper.process(hand_at(20, 20), "Pointing", "Pointing", frame)
    previous_canvas = mapper.canvas.canvas.copy()
    previous_history = [snapshot.copy() for snapshot in mapper.canvas.undo_stack]

    mapper.process([], "None", "None", frame)
    np.testing.assert_array_equal(mapper.canvas.canvas, previous_canvas)
    assert len(mapper.canvas.undo_stack) == len(previous_history)
    for actual, expected in zip(mapper.canvas.undo_stack, previous_history):
        np.testing.assert_array_equal(actual, expected)

    clock.now += 1
    mapper.process(hand_at(180, 180), "Pointing", "Pointing", frame)
    assert np.any(mapper.canvas.canvas[20, 20])
    assert np.any(mapper.canvas.canvas[180, 180])
    # An accidental old-to-new stroke would paint through the center.
    assert not np.any(mapper.canvas.canvas[90:110, 90:110])
    assert len(mapper.canvas.undo_stack) == len(previous_history) + 1


def test_reset_releases_drag_and_preserves_artwork_idempotently(mapper_and_clock):
    mapper, clock = mapper_and_clock
    canvas = mapper.canvas
    canvas.draw(20, 20)
    canvas.draw(20, 20, draw_mode=False)
    canvas.draw(40, 40)
    canvas.undo()
    canvas.hover_smoother.update(clock.now, 60, 60)
    previous_canvas = canvas.canvas.copy()
    previous_undo = [snapshot.copy() for snapshot in canvas.undo_stack]
    previous_redo = [snapshot.copy() for snapshot in canvas.redo_stack]
    mapper.mouse.engine.state = EventState.DRAGGING
    mapper.brightness_gesture_active = True
    mapper.last_brightness_y = 0.4

    mapper.reset_temporal_state()
    mapper.reset_temporal_state()

    assert mapper.mouse.engine.state is EventState.HAND_LOST
    mapper.mouse.mouse.release_all.assert_called()
    assert mapper.brightness_gesture_active is False
    assert mapper.last_brightness_y is None
    assert canvas.is_drawing is False
    assert canvas.last_point is None
    assert canvas.smoother.filter_x is None
    assert canvas.smoother.filter_y is None
    assert canvas.hover_smoother.filter_x is None
    assert canvas.hover_smoother.filter_y is None
    np.testing.assert_array_equal(canvas.canvas, previous_canvas)
    for actual_stack, expected_stack in (
        (canvas.undo_stack, previous_undo), (canvas.redo_stack, previous_redo)
    ):
        assert len(actual_stack) == len(expected_stack)
        for actual, expected in zip(actual_stack, expected_stack):
            np.testing.assert_array_equal(actual, expected)
