import pytest
import customtkinter as ctk
from types import SimpleNamespace
from unittest.mock import MagicMock

def test_ui_startup_no_crash():
    try:
        from src.ui import SmartGestureApp
        
        # Instantiate the UI
        app = SmartGestureApp(close_callback=lambda: None)
        
        # Run a single update cycle to trigger drawing and layout
        app.update_idletasks()
        app.update()
        
        # Verify basic properties to ensure configuration was successful
        assert app.bg_color is not None
        assert app.card_color is not None
        
        # Gracefully destroy to avoid hanging the test suite
        app.destroy()
    except Exception as e:
        pytest.fail(f"UI initialization failed with exception: {e}")


def test_hotkey_failure_and_recovery_keep_pause_available():
    from src.ui import SmartGestureApp
    ui = object.__new__(SmartGestureApp)
    ui.hotkey_status_label = MagicMock()
    ui.pause_btn = MagicMock()
    ui.muted_text = "gray"
    ui.automation_enabled = True

    ui.set_hotkey_available(False)

    assert ui.hotkey_available is False
    assert "unavailable" in ui.hotkey_status_label.configure.call_args.kwargs["text"]
    ui.pause_btn.configure.assert_called_with(text="Pause")
    ui.automation_enabled = False
    ui.set_hotkey_available(True)
    ui.pause_btn.configure.assert_called_with(text="Resume (Ctrl+Alt+G)")


def test_dashboard_reports_independent_measured_performance():
    from src.ui import SmartGestureApp
    ui = SimpleNamespace(camera_fps_label=MagicMock(), detector_fps_label=MagicMock(), inference_label=MagicMock())

    SmartGestureApp.update_performance(ui, camera_fps=29.8, detector_fps=24.2, inference_ms=18.6)

    ui.camera_fps_label.configure.assert_called_once_with(text="Camera: 29.8 fps")
    ui.detector_fps_label.configure.assert_called_once_with(text="Detector: 24.2 fps")
    ui.inference_label.configure.assert_called_once_with(text="Inference: 18.6 ms")
