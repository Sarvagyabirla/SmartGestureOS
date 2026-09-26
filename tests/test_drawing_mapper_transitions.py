"""Exercise canvas edits and gesture transitions with all controllers mocked."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

import config
import src.gesture_mapper as mapper_module
from src.drawing import DrawingCanvas
from src.models import ActionResult, Landmark


@pytest.fixture
def mapper_pipeline(monkeypatch):
    for name in (
        "MouseController", "KeyboardController", "MediaController",
        "DesktopController", "ShortcutController", "PresentationController",
        "VolumeController", "BrightnessController", "FeedbackController",
    ):
        monkeypatch.setattr(mapper_module, name, MagicMock())
    monkeypatch.setattr("src.settings_manager.settings_manager.register_callback", lambda cb: None)
    settings = json.loads(
        (Path(__file__).resolve().parents[1] / "config" / "defaults.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(config, "SETTINGS", settings)
    monkeypatch.setattr(mapper_module, "SETTINGS", settings)
    clock = SimpleNamespace(now=10.0)
    monkeypatch.setattr(mapper_module.time, "perf_counter", lambda: clock.now)
    mapper = mapper_module.GestureMapper(200, 200)

    def tick(elapsed, stable, raw=None, x=20, y=20):
        clock.now = 10.0 + elapsed
        hand = [{"landmarks": [
            Landmark(id=i, pixel_x=x, pixel_y=y, x=x / 200, y=y / 200, z=0.0)
            for i in range(21)
        ]}]
        return mapper.process(
            hand, stable, stable if raw is None else raw,
            np.zeros((200, 200, 3), dtype=np.uint8),
        )

    return mapper, tick, settings


def test_clear_after_undo_discards_redo_but_remains_undoable():
    canvas = DrawingCanvas(200, 200)
    canvas.draw(20, 20)
    canvas.end_stroke()
    first_stroke = canvas.canvas.copy()
    canvas.draw(180, 180)
    assert canvas.undo().success
    canvas.clear()
    assert not np.any(canvas.canvas)
    assert not canvas.redo().success
    assert canvas.undo().success
    np.testing.assert_array_equal(canvas.canvas, first_stroke)


def test_clear_ends_stroke_before_next_point():
    canvas = DrawingCanvas(200, 200)
    canvas.draw(20, 20)
    canvas.clear()
    canvas.draw(180, 180)
    assert np.any(canvas.canvas[180, 180])
    assert not np.any(canvas.canvas[90:110, 90:110])
    assert canvas.undo().success
    assert not np.any(canvas.canvas)


def test_resize_preserves_artwork_and_ends_previous_coordinate_history():
    canvas = DrawingCanvas(200, 200)
    canvas.draw(20, 20)
    original = canvas.canvas.copy()
    assert canvas.resize(400, 400).success
    expected = cv2.resize(original, (400, 400), interpolation=cv2.INTER_NEAREST)
    np.testing.assert_array_equal(canvas.canvas, expected)
    canvas.draw(300, 300)
    assert np.any(canvas.canvas[300, 300])
    assert not np.any(canvas.canvas[140:160, 140:160])
    assert canvas.undo().success
    np.testing.assert_array_equal(canvas.canvas, expected)
    assert canvas.redo().success
    assert np.any(canvas.canvas[300, 300])


def test_undo_during_stroke_starts_a_new_history_branch():
    canvas = DrawingCanvas(200, 200)
    canvas.draw(20, 20)
    assert canvas.undo().success
    canvas.draw(180, 180)
    assert not np.any(canvas.canvas[90:110, 90:110])
    assert not canvas.redo().success
    assert canvas.undo().success
    assert not np.any(canvas.canvas)


def test_draw_starts_from_raw_geometry_and_stops_on_raw_release(mapper_pipeline):
    mapper, tick, _ = mapper_pipeline
    mapper.set_mode("DRAW")
    tick(0, "Open Palm", raw="Pointing")
    assert np.any(mapper.canvas.canvas[20, 20])
    before_release = mapper.canvas.canvas.copy()
    tick(0.1, "Pointing", raw="Open Palm", x=180, y=180)
    np.testing.assert_array_equal(mapper.canvas.canvas, before_release)
    tick(0.2, "Unknown", raw="Pointing", x=180, y=180)
    np.testing.assert_array_equal(mapper.canvas.canvas, before_release)
    tick(0.3, "Open Palm", raw="Pointing", x=180, y=180)
    assert np.any(mapper.canvas.canvas[180, 180])
    assert not np.any(mapper.canvas.canvas[90:110, 90:110])


@pytest.mark.parametrize(("mode", "gesture", "action_name"), [
    ("GENERAL", "Crossed Fingers", "lock_pc"),
    ("MEDIA", "Victory", "next_track"),
    ("DRAW", "Closed Fist", "clear_canvas"),
])
def test_raw_release_cancels_mapped_hold_until_a_fresh_hold(
    mapper_pipeline, mode, gesture, action_name,
):
    mapper, tick, _ = mapper_pipeline
    mapper.set_mode(mode)
    execute = MagicMock(return_value=ActionResult(True, action_name, "Mocked action"))
    mapper.action_registry[action_name]["func"] = execute
    tick(0, gesture)
    _, action, progress = tick(0.31, gesture, raw="Pointing")
    execute.assert_not_called()
    assert action is None
    assert progress == 0.0
    tick(0.4, gesture)
    tick(0.61, gesture)
    execute.assert_not_called()
    tick(0.71, gesture)
    tick(1.5, gesture)
    execute.assert_called_once_with()


def test_confidence_gap_does_not_repeat_an_already_consumed_media_gesture(mapper_pipeline):
    mapper, tick, _ = mapper_pipeline
    mapper.set_mode("MEDIA")
    mapper.media.play_pause.return_value = ActionResult(True, "play_pause", "Sent")
    tick(0, "Pinch")
    tick(0.31, "Pinch")
    tick(0.4, "Unknown", raw="Pinch")
    tick(0.5, "Pinch")
    tick(0.9, "Pinch")
    mapper.media.play_pause.assert_called_once_with()
    tick(1.0, "Pointing")
    tick(1.1, "Pinch")
    tick(1.41, "Pinch")
    assert mapper.media.play_pause.call_count == 2


def test_mode_change_resets_hold_sleep_and_active_stroke(mapper_pipeline):
    mapper, tick, _ = mapper_pipeline
    mapper.set_mode("MEDIA")
    tick(0, "Victory")
    mapper.canvas.draw(20, 20)
    mapper.sleep_timer.check("Call Me")
    mapper.last_brightness_y = 0.5
    mapper.brightness_gesture_active = True
    mapper.mouse.release_all.reset_mock()
    mapper.set_mode("DRAW")
    mapper.mouse.release_all.assert_called_once_with()
    assert mapper.sleep_timer.target_gesture is None
    assert mapper.last_brightness_y is None
    assert not mapper.brightness_gesture_active
    assert not mapper.canvas.is_drawing
    before = mapper.canvas.canvas.copy()
    tick(0.31, "Victory")
    np.testing.assert_array_equal(mapper.canvas.canvas, before)
    tick(0.62, "Victory")
    assert not np.any(mapper.canvas.canvas)


def test_mode_switch_gesture_fires_once_until_raw_release(mapper_pipeline):
    mapper, tick, _ = mapper_pipeline
    tick(0, "Call Me")
    tick(0.31, "Call Me")
    assert mapper.mode == "MEDIA"
    for elapsed in (0.7, 1.1, 2.0):
        tick(elapsed, "Call Me")
    assert mapper.mode == "MEDIA"
    tick(2.1, "Call Me", raw="Pointing")
    tick(2.2, "Call Me")
    tick(2.51, "Call Me")
    assert mapper.mode == "DRAW"


def test_sleep_hold_stops_on_raw_release_and_requires_fresh_hold(mapper_pipeline):
    mapper, tick, settings = mapper_pipeline
    settings["mappings"]["GENERAL"]["Rock On"] = "toggle_sleep"
    tick(0, "Rock On")
    tick(3.01, "Rock On", raw="Pointing")
    assert not mapper.is_sleeping
    tick(3.1, "Rock On")
    tick(6.11, "Rock On")
    assert mapper.is_sleeping
    tick(6.2, "Unknown", raw="Rock On")
    tick(6.3, "Rock On")
    tick(9.4, "Rock On")
    assert mapper.is_sleeping


def test_failed_resize_keeps_mapper_dimensions_consistent_with_canvas(mapper_pipeline):
    mapper, _, _ = mapper_pipeline
    mapper.update_frame_dimensions(-1, 100)
    assert (mapper.frame_w, mapper.frame_h) == (200, 200)
    assert (mapper.canvas.width, mapper.canvas.height) == (200, 200)


@pytest.mark.parametrize(("success", "message", "error", "expected"), [
    (True, "Brightness: 60%", None, "Brightness: 60%"),
    (False, "Brightness update pending", None, "Brightness update pending"),
    (False, "No supported display", "unsupported", "Brightness unavailable: No supported display"),
    (False, "Display API failed", "API failure", "Brightness unavailable: Display API failed"),
])
def test_brightness_feedback_reports_controller_result(
    mapper_pipeline, success, message, error, expected,
):
    mapper, tick, _ = mapper_pipeline
    mapper.brightness.set_brightness_from_y.return_value = ActionResult(
        success, "brightness", message, error,
    )
    _, action, _ = tick(0, "Middle Finger")
    assert action == expected
    mapper.brightness.set_brightness_from_y.reset_mock()
    _, action, _ = tick(0.1, "Middle Finger", raw="Pointing")
    mapper.brightness.set_brightness_from_y.assert_not_called()
    assert action is None
