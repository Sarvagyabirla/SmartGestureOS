"""Deterministic camera lifecycle and newest-frame checks without a webcam."""

from unittest.mock import patch

import numpy as np
import pytest

from src.camera import Camera


@pytest.fixture(autouse=True)
def mock_capture():
    """Every test in this module must use a fake camera backend."""
    with patch("src.camera.cv2.VideoCapture") as create:
        create.return_value.isOpened.return_value = True
        yield create


def test_camera_init_does_not_open_hardware(mock_capture):
    camera = Camera(index=3, width=640, height=360)

    assert camera.running is False
    assert camera.is_connected is False
    assert camera.read_with_timestamp() == (None, -1, None)
    mock_capture.assert_not_called()


def test_camera_start_stop_releases_capture_and_joins_thread(mock_capture):
    camera = Camera(index=3, width=640, height=360)
    with patch("src.camera.threading.Thread") as create_thread:
        thread = create_thread.return_value
        thread.is_alive.return_value = True

        assert camera.start() is True
        assert camera.running is True
        mock_capture.assert_called_once_with(3)
        create_thread.assert_called_once_with(
            target=camera._update, daemon=True, name="camera-capture"
        )
        thread.start.assert_called_once_with()

        # A second start must not create another capture or worker.
        camera.start()
        mock_capture.assert_called_once()
        create_thread.assert_called_once()

        camera.stop()
        camera.stop()

    thread.join.assert_called_once_with(timeout=2.0)
    mock_capture.return_value.release.assert_called_once_with()
    assert camera.running is False
    assert camera.is_connected is False
    assert camera.cap is None
    assert camera._thread is None


def test_capture_overwrites_old_frame_with_latest_mirrored_frame(mock_capture):
    camera = Camera(index=0)
    first = np.array([[[1, 2, 3], [4, 5, 6]]], dtype=np.uint8)
    newest = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
    frames = iter([first, newest])

    def read_frame():
        frame = next(frames)
        if frame is newest:
            camera.running = False
        return True, frame

    mock_capture.return_value.read.side_effect = read_frame
    camera.running = True
    camera._update()

    assert mock_capture.return_value.read.call_count == 2
    assert camera.frame_queue.qsize() == 1
    frame, frame_id, captured_at = camera.read_with_timestamp()
    np.testing.assert_array_equal(frame, newest[:, ::-1])
    assert frame_id == 1
    assert isinstance(captured_at, float)
    assert camera.read_with_timestamp() == (None, -1, None)
