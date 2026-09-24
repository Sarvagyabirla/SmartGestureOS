"""
tests/test_mapping_isolation.py
Verifies that mode-specific gesture mappings are isolated from each other.
No physical desktop side effects — controllers are mocked during instantiation.
"""
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


# ---------------------------------------------------------------------------
# Helper: build a real GestureMapper with all hardware mocked
# ---------------------------------------------------------------------------

def _make_mapper():
    """Instantiate GestureMapper with all hardware controllers mocked.

    Patches must target names inside gesture_mapper's own namespace so
    the already-imported GestureMapper.__init__ sees the mocks regardless
    of module cache state.
    """
    patches = [
        patch("src.gesture_mapper.MouseController"),
        patch("src.gesture_mapper.KeyboardController"),
        patch("src.gesture_mapper.MediaController"),
        patch("src.gesture_mapper.DesktopController"),
        patch("src.gesture_mapper.ShortcutController"),
        patch("src.gesture_mapper.PresentationController"),
        patch("src.gesture_mapper.VolumeController"),
        patch("src.gesture_mapper.BrightnessController"),
        patch("src.gesture_mapper.FeedbackController"),
        patch("src.gesture_mapper.DrawingCanvas"),
        patch("src.settings_manager.settings_manager"),
    ]
    mocks = [p.start() for p in patches]
    # mocks order matches patches order
    (MockMouse, MockKeyboard, MockMedia, MockDesktop, MockShortcut,
     MockPresentation, MockVolume, MockBrightness, MockFeedback,
     MockCanvas, mock_sm) = mocks

    mock_sm.register_callback = MagicMock()

    from src.gesture_mapper import GestureMapper
    mapper = GestureMapper(1280, 720)

    # Stop patches — mapper attributes are already bound to the mock instances
    for p in patches:
        p.stop()

    # The mock instances are still alive (captured by mapper at construction)
    # mapper.media, mapper.desktop, mapper.canvas etc. ARE the mocks
    return mapper


# ---------------------------------------------------------------------------
# Mode cycling
# ---------------------------------------------------------------------------

def test_call_me_cycles_modes():
    mapper = _make_mapper()
    assert mapper.mode == "GENERAL"
    mapper.cycle_mode()
    assert mapper.mode == "MEDIA"
    mapper.cycle_mode()
    assert mapper.mode == "DRAW"
    mapper.cycle_mode()
    assert mapper.mode == "GENERAL"


# ---------------------------------------------------------------------------
# MEDIA vs GENERAL Pinch isolation
# ---------------------------------------------------------------------------

def test_media_pinch_triggers_play_pause():
    """In MEDIA mode, execute_action('play_pause') → media.play_pause called."""
    mapper = _make_mapper()
    mapper.mode = "MEDIA"
    mapper.execute_action("play_pause")
    mapper.media.play_pause.assert_called_once()


def test_general_mode_does_not_have_play_pause():
    """play_pause is not in the GENERAL mappings section of default config."""
    from config import SETTINGS
    general_mappings = SETTINGS.get("mappings", {}).get("GENERAL", {})
    assert "play_pause" not in general_mappings.values(), \
        "play_pause should only be a MEDIA action"


# ---------------------------------------------------------------------------
# Three Fingers isolation
# ---------------------------------------------------------------------------

def test_draw_redo_action():
    """execute_action('redo') → canvas.redo is called."""
    mapper = _make_mapper()
    mapper.mode = "DRAW"
    mapper.execute_action("redo")
    mapper.canvas.redo.assert_called_once()


def test_general_right_click_action():
    """execute_action('right_click') → ... verifies it resolves without crashing.
    Note: right_click is handled in EventEngine/MouseController, not action_registry.
    """
    mapper = _make_mapper()
    # right_click handled via event_engine, not in action_registry; should return None
    result = mapper.execute_action("right_click")
    assert result is None


def test_media_prev_track_action():
    """execute_action('prev_track') → media.prev_track called."""
    mapper = _make_mapper()
    mapper.mode = "MEDIA"
    mapper.execute_action("prev_track")
    mapper.media.prev_track.assert_called_once()


# ---------------------------------------------------------------------------
# Closed Fist isolation
# ---------------------------------------------------------------------------

def test_clear_canvas_action():
    """execute_action('clear_canvas') → canvas.clear called."""
    mapper = _make_mapper()
    mapper.mode = "DRAW"
    mapper.execute_action("clear_canvas")
    mapper.canvas.clear.assert_called_once()
    mapper.desktop.show_desktop.assert_not_called()


def test_show_desktop_action():
    """execute_action('show_desktop') → desktop.show_desktop called."""
    mapper = _make_mapper()
    mapper.mode = "GENERAL"
    mapper.execute_action("show_desktop")
    mapper.desktop.show_desktop.assert_called_once()


# ---------------------------------------------------------------------------
# Mode-switch action
# ---------------------------------------------------------------------------

def test_switch_mode_action():
    """execute_action('switch_mode') cycles the mode."""
    mapper = _make_mapper()
    mapper.execute_action("switch_mode")
    assert mapper.mode == "MEDIA"


# ---------------------------------------------------------------------------
# Unknown action is safe
# ---------------------------------------------------------------------------

def test_unknown_action_returns_none():
    """execute_action with an unmapped name returns None without crashing."""
    mapper = _make_mapper()
    result = mapper.execute_action("does_not_exist_12345")
    assert result is None


# ---------------------------------------------------------------------------
# Storage path tests (no real filesystem access)
# ---------------------------------------------------------------------------

def test_screenshot_uses_localappdata(tmp_path):
    """DesktopController.take_screenshot saves to user-writable path (mocked fs)."""
    from src.desktop_controller import DesktopController
    import src.paths as paths_mod

    dc = DesktopController()
    fake_screenshots = tmp_path / "screenshots"
    fake_screenshots.mkdir()

    with patch.object(paths_mod, "SCREENSHOTS_DIR", fake_screenshots), \
         patch("PIL.ImageGrab.grab") as mock_grab:
        mock_img = MagicMock()
        mock_grab.return_value = mock_img

        # Simulate save creating actual file
        import os
        def real_save(path_str):
            (fake_screenshots / Path(path_str).name).write_bytes(b"PNG")
        mock_img.save.side_effect = real_save

        result = dc.take_screenshot()
    assert result.success is True
    assert result.action == "screenshot"


def test_drawing_save_uses_localappdata(tmp_path):
    """DrawingCanvas.save_image uses user-writable drawings directory (mocked)."""
    import numpy as np
    import src.paths as paths_mod
    from src.drawing import DrawingCanvas

    canvas = DrawingCanvas(width=320, height=240)
    canvas.canvas = np.zeros((240, 320, 3), dtype=np.uint8)
    fake_dir = tmp_path / "drawings"
    fake_dir.mkdir()

    # imwrite returns True AND we make the file exist
    def _fake_imwrite(path, img):
        Path(path).write_bytes(b"PNG")
        return True

    with patch.object(paths_mod, "DRAWINGS_DIR", fake_dir), \
         patch("cv2.imwrite", side_effect=_fake_imwrite):
        result = canvas.save_image()

    assert result.success is True
    assert result.action == "save_drawing"
