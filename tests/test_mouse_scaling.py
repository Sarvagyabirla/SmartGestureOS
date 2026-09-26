"""Mouse scaling must be usable before calibration and safe on lost data."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.mouse_controller import MouseController


def make_hand(size=0.1):
    hand = [SimpleNamespace(x=0.5, y=0.5, z=0.0, pixel_x=640, pixel_y=360)
            for _ in range(21)]
    hand[9].y -= size
    return hand


@pytest.fixture
def controller():
    controller = MouseController.__new__(MouseController)
    controller.mouse = MagicMock()
    controller.engine = MagicMock()
    return controller


@pytest.mark.parametrize("baseline", [1.0, None, "invalid", float("nan"), -1.0])
def test_uncalibrated_or_invalid_baseline_does_not_amplify_scroll(controller, monkeypatch, baseline):
    monkeypatch.setattr("config.SETTINGS", {"gestures": {"base_hand_size": baseline}})
    controller.process_landmarks(make_hand(0.1), "Two Fingers", "Two Fingers", 1280, 720)
    assert controller.engine.process.call_args.kwargs["scale_factor"] == pytest.approx(1.0)


@pytest.mark.parametrize(("baseline", "size", "expected"), [(0.1, 0.05, 2.0), (0.5, 0.01, 4.0)])
def test_calibrated_distance_scaling_has_a_safe_upper_bound(controller, monkeypatch, baseline, size, expected):
    monkeypatch.setattr("config.SETTINGS", {"gestures": {"base_hand_size": baseline}})
    controller.process_landmarks(make_hand(size), "Two Fingers", "Two Fingers", 1280, 720)
    assert controller.engine.process.call_args.kwargs["scale_factor"] == pytest.approx(expected)


@pytest.mark.parametrize("hand", [[], make_hand()[:20], make_hand(float("nan"))])
def test_missing_or_invalid_landmarks_release_active_input(controller, hand):
    controller.process_landmarks(hand, "Pinch", "Pinch", 1280, 720)
    controller.engine.process.assert_not_called()
    controller.mouse.release_all.assert_called_once_with()
    controller.engine.reset.assert_called_once_with()
