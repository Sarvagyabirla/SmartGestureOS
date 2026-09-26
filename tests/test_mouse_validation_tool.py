"""The opt-in diagnostic's input boundary, with no Windows input or webcam."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts.validate_mouse_controls import MouseTarget, TargetMouseAPI, clamp_point


@pytest.mark.parametrize("point,expected", [((-50, 900), (100, 299)), ((200, 250), (200, 250)), ((500, 100), (399, 200))])
def test_clamp_stays_inside_exclusive_client_edges(point, expected):
    assert clamp_point(*point, (100, 200, 400, 300)) == expected


def test_invalid_rectangle_is_rejected():
    with pytest.raises(ValueError):
        clamp_point(10, 10, (20, 20, 20, 40))


def fake_backend(position):
    calls = []

    def get_cursor(point):
        point._obj.x, point._obj.y = position
        return True

    return SimpleNamespace(SetCursorPos=lambda *args: calls.append(("move", args)),
                           mouse_event=lambda *args: calls.append(("event", args)),
                           GetCursorPos=get_cursor), calls


def test_foreground_loss_blocks_movement_press_and_wheel_but_releases_drag():
    backend, calls = fake_backend((150, 250))
    guard = TargetMouseAPI(backend, lambda: None, lambda _point: True)
    guard.SetCursorPos(200, 250)
    for flag in (0x0002, 0x0008, 0x0800, 0x0004, 0x0010):
        guard.mouse_event(flag, 0, 0, 0, 0)
    assert [args[0] for _, args in calls] == [0x0004, 0x0010]
    assert guard.blocked == 4


def test_cursor_outside_target_cannot_click_other_ui_even_with_target_focused():
    backend, calls = fake_backend((80, 250))
    guard = TargetMouseAPI(backend, lambda: (100, 200, 400, 300), lambda _point: True)
    guard.mouse_event(0x0002, 0, 0, 0, 0)
    guard.mouse_event(0x0800, 0, 0, 120, 0)
    assert calls == []


def test_focused_target_forwards_production_input_and_clamps_movement():
    backend, calls = fake_backend((150, 250))
    guard = TargetMouseAPI(backend, lambda: (100, 200, 400, 300), lambda _point: True)
    guard.SetCursorPos(-500, 900)
    guard.mouse_event(0x0002, 0, 0, 0, 0)
    assert calls == [("move", (100, 299)), ("event", (0x0002, 0, 0, 0, 0))]


def test_overlay_covering_target_rejects_click_even_if_target_is_foreground():
    backend, calls = fake_backend((150, 250))
    guard = TargetMouseAPI(backend, lambda: (100, 200, 400, 300), lambda _point: False)
    guard.mouse_event(0x0002, 0, 0, 0, 0)
    assert calls == []


def test_startup_reveals_target_only_once_without_recurring_focus_steals():
    target = MouseTarget.__new__(MouseTarget)
    target.closed = False
    target._shown = False
    target.app = SimpleNamespace(running=True)
    target.window = MagicMock()

    target.show_once()
    target.show_once()

    target.window.lift.assert_called_once_with()
    target.window.focus_set.assert_called_once_with()


@pytest.mark.parametrize("closed,running", [(True, True), (False, False)])
def test_delayed_startup_callback_does_nothing_after_close_or_shutdown(closed, running):
    target = MouseTarget.__new__(MouseTarget)
    target.closed = closed
    target._shown = False
    target.app = SimpleNamespace(running=running)
    target.window = MagicMock()

    target.show_once()

    target.window.lift.assert_not_called()
    target.window.focus_set.assert_not_called()


@pytest.mark.parametrize("delta,direction", [(120, "UP"), (-120, "DOWN")])
def test_wheel_direction_is_visible_without_reading_raw_counters(delta, direction):
    target = MouseTarget.__new__(MouseTarget)
    target.record = MagicMock()
    target.wheel_indicator = MagicMock()
    target.canvas = MagicMock()
    target.square = 1

    target.wheel(SimpleNamespace(delta=delta))

    target.wheel_indicator.config.assert_called_once_with(text=f"Wheel: {direction}")
