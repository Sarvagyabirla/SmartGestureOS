"""Mouse resets must discard old pointing coordinates without touching Windows."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.event_engine import EventEngine
from src.mouse_controller import MouseController
from src.virtual_mouse import VirtualMouse


@pytest.fixture
def mouse_controller(monkeypatch):
    user32 = MagicMock()
    monitor = SimpleNamespace(
        x=0, y=0, width=1920, height=1080, is_primary=True,
    )
    monkeypatch.setattr("ctypes.windll", SimpleNamespace(user32=user32))
    monkeypatch.setattr("screeninfo.get_monitors", lambda: [monitor])
    controller = MouseController.__new__(MouseController)
    controller.mouse = VirtualMouse()
    controller.engine = EventEngine(controller)
    return controller, user32


@pytest.mark.parametrize("reset_path", ["pause", "hand_loss"])
def test_same_coordinate_reacquisition_moves_after_reset(mouse_controller, reset_path):
    controller, user32 = mouse_controller
    mouse = controller.mouse
    mouse.move(640, 360, 1280, 720)
    assert user32.SetCursorPos.call_count == 1

    if reset_path == "pause":
        controller.release_all()
    else:
        controller.engine.on_hand_lost()

    # The user may move the physical mouse while gesture control is inactive.
    # Reacquiring the original hand position must issue a new cursor movement.
    mouse.move(640, 360, 1280, 720)
    assert user32.SetCursorPos.call_count == 2
    assert user32.SetCursorPos.call_args.args == (960, 540)


def test_release_error_still_discards_drag_and_pointer_history(mouse_controller):
    controller, user32 = mouse_controller
    mouse = controller.mouse
    mouse.move(640, 360, 1280, 720)
    mouse.drag(start=True)
    assert mouse.is_dragging
    assert mouse.smoother.filter_x is not None
    assert mouse.smoother.filter_y is not None

    user32.mouse_event.side_effect = OSError("simulated input release failure")
    mouse.release_all()

    assert not mouse.is_dragging
    assert mouse.last_pos is None
    assert mouse.smoother.filter_x is None
    assert mouse.smoother.filter_y is None
    mouse.move(640, 360, 1280, 720)
    assert user32.SetCursorPos.call_count == 2
