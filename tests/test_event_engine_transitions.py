"""Regressions for observed cross-frame mouse state failures; no OS input."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.event_engine import EventEngine, EventState


@pytest.fixture
def pipeline(monkeypatch):
    clock = SimpleNamespace(now=10.0)
    monkeypatch.setattr("src.event_engine.time.perf_counter", lambda: clock.now)
    mouse = MagicMock()
    engine = EventEngine(SimpleNamespace(mouse=mouse))

    def tick(elapsed, raw, stable=None, y=0.5, scale=1.0):
        clock.now = 10.0 + elapsed
        landmarks = [SimpleNamespace(y=y) for _ in range(21)]
        engine.process(stable if stable is not None else raw, raw,
                       600, int(y * 720) if y == y and abs(y) != float("inf") else 360,
                       1280, 720, landmarks, scale)

    return engine, mouse, tick


def test_short_pinch_release_does_not_become_drag_from_stale_stable_pose(pipeline):
    engine, mouse, tick = pipeline
    tick(0, "Pinch")
    tick(0.34, "Pointing", stable="Pinch")
    assert engine.state == EventState.PINCH_RELEASE_WAIT
    tick(0.40, "Pointing", stable="Pinch")
    mouse.drag.assert_not_called()
    tick(0.57, "Pointing")
    mouse.click.assert_called_once_with(button="left")


def test_release_crossing_hold_deadline_keeps_click_when_drag_never_started(pipeline):
    engine, mouse, tick = pipeline
    tick(0, "Pinch")
    tick(0.33, "Pinch")
    # At camera cadence the next sample may show release just past the drag
    # threshold, without any held sample having dispatched a button press.
    tick(0.36, "Pointing", stable="Pinch")
    assert engine.state == EventState.PINCH_RELEASE_WAIT
    mouse.drag.assert_not_called()
    tick(0.59, "Pointing")
    mouse.click.assert_called_once_with(button="left")
    mouse.double_click.assert_not_called()


def test_drag_drops_on_raw_release_before_stable_pose_catches_up(pipeline):
    engine, mouse, tick = pipeline
    tick(0, "Pinch")
    tick(0.36, "Pinch")
    assert engine.state == EventState.DRAGGING
    mouse.reset_mock()
    tick(0.4, "Pointing", stable="Pinch")
    mouse.drag.assert_called_once_with(start=False)
    mouse.move.assert_not_called()  # Drop at last held position.
    assert engine.state == EventState.COOLDOWN


def test_held_second_pinch_cannot_generate_an_extra_click_or_drag(pipeline):
    engine, mouse, tick = pipeline
    tick(0, "Pinch")
    tick(0.1, "Pointing")
    tick(0.2, "Pinch")
    for elapsed in (0.36, 0.4, 0.8, 1.0):
        tick(elapsed, "Pinch")
    mouse.double_click.assert_called_once_with()
    mouse.click.assert_not_called()
    mouse.drag.assert_not_called()
    tick(1.1, "Pointing")
    tick(1.2, "Pinch")
    tick(1.56, "Pinch")
    mouse.drag.assert_called_once_with(start=True)


def test_pending_click_keeps_its_cursor_target_until_dispatched(pipeline):
    engine, mouse, tick = pipeline
    tick(0, "Pointing")
    mouse.reset_mock()
    tick(0.01, "Pinch")
    tick(0.1, "Pointing")
    tick(0.2, "Pointing", y=0.8)
    tick(0.33, "Pointing", y=0.9)
    mouse.move.assert_not_called()
    mouse.click.assert_called_once_with(button="left")


def test_scroll_freezes_on_entry_and_stops_on_raw_exit(pipeline):
    engine, mouse, tick = pipeline
    tick(0, "Two Fingers")
    mouse.move.assert_not_called()
    tick(0.1, "Pointing", stable="Two Fingers", y=0.8)
    assert engine.state == EventState.HOVER
    mouse.scroll.assert_not_called()


def test_scroll_jump_is_bounded_and_does_not_leak_into_stationary_frames(pipeline):
    engine, mouse, tick = pipeline
    tick(0, "Two Fingers", y=0.1)
    tick(0.1, "Two Fingers", y=0.9, scale=100.0)
    assert mouse.scroll.call_count == 1
    assert -3 <= mouse.scroll.call_args.args[0] < 0
    mouse.reset_mock()
    tick(0.2, "Two Fingers", y=0.9, scale=100.0)
    mouse.scroll.assert_not_called()


@pytest.mark.parametrize("invalid_y", [float("nan"), float("inf"), -0.2, 1.2])
def test_invalid_scroll_landmark_resets_anchor_then_recovers(pipeline, invalid_y):
    engine, mouse, tick = pipeline
    tick(0, "Two Fingers", y=0.4)
    tick(0.1, "Two Fingers", y=invalid_y)
    mouse.scroll.assert_not_called()
    assert engine.scroll_start_y is None
    tick(0.2, "Two Fingers", y=0.5)
    mouse.scroll.assert_not_called()
    tick(0.3, "Two Fingers", y=0.57)
    assert mouse.scroll.call_args.args[0] < 0


@pytest.mark.parametrize("raw", ["Pinch", "Two Fingers", "Three Fingers"])
def test_low_confidence_raw_pose_cannot_start_mouse_action(pipeline, raw):
    engine, mouse, tick = pipeline
    tick(0, raw, stable="Unknown")
    tick(0.5, raw, stable="Unknown")
    assert engine.state == EventState.HOVER
    mouse.click.assert_not_called()
    mouse.drag.assert_not_called()
    mouse.scroll.assert_not_called()


def test_right_click_waits_for_stabilized_three_fingers(pipeline):
    engine, mouse, tick = pipeline
    tick(0, "Three Fingers", stable="Pointing")
    mouse.click.assert_not_called()
    tick(0.1, "Three Fingers")
    tick(0.3, "Three Fingers")
    tick(0.5, "Three Fingers")
    mouse.click.assert_called_once_with(button="right")
