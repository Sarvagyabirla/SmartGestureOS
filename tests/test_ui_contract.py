"""Tests for explicit UI <-> Backend contract and clean callback architecture."""

import threading
from unittest.mock import MagicMock, patch
import pytest

from src.models import AppStateSnapshot
from src.ui import SmartGestureApp
from src.ui_gesture_test import GestureTestUI
import main as main_module


def test_no_import_main_in_src():
    """Verify that no source file in src/ imports the main module or scans __dict__.values()."""
    import os
    import re

    src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
    import_main_pattern = re.compile(r"^\s*import\s+main\b|^\s*from\s+main\s+import")
    dict_scan_pattern = re.compile(r"__dict__\.values")

    violations = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8") as fh:
                    for line_idx, line in enumerate(fh, 1):
                        if import_main_pattern.search(line):
                            violations.append(f"{path}:{line_idx}: imports main directly: {line.strip()}")
                        if dict_scan_pattern.search(line):
                            violations.append(f"{path}:{line_idx}: scans globals: {line.strip()}")

    assert not violations, f"Found architectural violations in src/:\n" + "\n".join(violations)


def test_manual_mode_buttons_call_set_mode_callback():
    """Verify GENERAL, MEDIA, and DRAW buttons invoke the real set_mode_callback."""
    called_modes = []

    def mock_set_mode(mode: str):
        called_modes.append(mode)

    ui = object.__new__(SmartGestureApp)
    ui.set_mode_callback = mock_set_mode
    ui.mode_label = MagicMock()
    ui._last_configure_values = {}

    for mode in ("GENERAL", "MEDIA", "DRAW"):
        ui._on_manual_mode(mode)
        assert called_modes[-1] == mode
        assert ui.mode_label.configure.called


def test_mainapp_set_mode_resets_and_updates():
    """Verify MainApp.set_mode calls mapper.set_mode, resets temporal state, and notifies UI."""
    app = main_module.MainApp.__new__(main_module.MainApp)
    app._automation_lock = threading.RLock()
    app.mapper = MagicMock()
    app.classifier = MagicMock()
    app.ui_commands = MagicMock()
    app.ui = MagicMock()

    app.set_mode("MEDIA")

    app.mapper.set_mode.assert_called_once_with("MEDIA")
    app.classifier.reset.assert_called_once()
    app.ui_commands.post.assert_called_once_with(app.ui.set_mode_display, "MEDIA")


def test_app_state_snapshot_returned_by_get_state_snapshot():
    """Verify get_state_snapshot returns a valid AppStateSnapshot without scanning globals."""
    app = main_module.MainApp.__new__(main_module.MainApp)
    app._automation_lock = threading.RLock()
    app._state_lock = threading.RLock()
    app._automation_enabled = True
    app._rearm_state = "armed"
    app.mapper = MagicMock()
    app.mapper.mode = "DRAW"
    app.camera = MagicMock()
    app.camera.is_connected = True
    app.camera.current_fps = 30.0
    app.detector_fps = 28.5
    app._pointer_fps = 28.0
    app._inference_ms = 12.4
    app._frame_age_ms = 18.2
    app._latest_raw_gesture = "Pointing"
    app._latest_stable_gesture = "Pointing"
    app._latest_confidence = 88
    app._latest_hands_data = [1]

    snapshot = app.get_state_snapshot()

    assert isinstance(snapshot, AppStateSnapshot)
    assert snapshot.automation_state == "ACTIVE"
    assert snapshot.mode == "DRAW"
    assert snapshot.raw_gesture == "Pointing"
    assert snapshot.stable_gesture == "Pointing"
    assert snapshot.confidence == 88
    assert snapshot.camera_connected is True
    assert snapshot.camera_fps == 30.0
    assert snapshot.detector_fps == 28.5
    assert snapshot.hands_detected == 1


def test_gesture_test_ui_uses_explicit_providers():
    """Verify GestureTestUI updates using explicit state and preview providers."""
    mock_snapshot = AppStateSnapshot(
        automation_state="ACTIVE",
        mode="GENERAL",
        raw_gesture="Pinch",
        stable_gesture="Pinch",
        confidence=92.0,
        camera_connected=True,
        camera_fps=30.0,
        detector_fps=30.0,
        pointer_fps=30.0,
        inference_ms=10.0,
        frame_age_ms=15.0,
        hands_detected=1,
    )

    test_ui = object.__new__(GestureTestUI)
    test_ui.get_state_callback = lambda: mock_snapshot
    test_ui.get_preview_callback = lambda: (None, 0)
    test_ui.gesture_label = MagicMock()
    test_ui.conf_label = MagicMock()
    test_ui.preview_label = MagicMock()
    test_ui.status_badge = MagicMock()
    test_ui._prev_stable = ""
    test_ui._last_gesture = ""
    test_ui._last_preview_id = -1
    test_ui.winfo_exists = MagicMock(return_value=False)
    test_ui.after = MagicMock()

    # Call _poll
    test_ui._poll()

    test_ui.gesture_label.configure.assert_called_with(text="Pinch")
    test_ui.conf_label.configure.assert_called_with(text="92%")
