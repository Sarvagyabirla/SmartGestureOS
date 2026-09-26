"""The frozen startup probe never opens a camera or GUI."""

from unittest.mock import MagicMock

import main


def test_self_check_loads_model_runs_one_frame_and_closes(monkeypatch):
    detector = MagicMock(detector_available=True, frames_processed=1)
    detector.process_frame.return_value = object()
    create = MagicMock(return_value=detector)
    monkeypatch.setattr(main, "GestureDetector", create)

    assert main.run_self_check() is True
    create.assert_called_once_with()
    frame, timestamp = detector.process_frame.call_args.args
    assert frame.shape == (360, 640, 3)
    assert timestamp == 1
    detector.close.assert_called_once_with()


def test_self_check_reports_native_failure_and_closes(monkeypatch):
    detector = MagicMock(detector_available=True, frames_processed=0)
    detector.process_frame.return_value = None
    monkeypatch.setattr(main, "GestureDetector", MagicMock(return_value=detector))

    assert main.run_self_check() is False
    detector.close.assert_called_once_with()
