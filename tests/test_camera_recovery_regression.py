"""Capture failures must leave the app disconnected and allow a later frame."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.camera import Camera


@pytest.mark.parametrize(
    "bad_frame",
    [np.empty((0, 0, 3), dtype=np.uint8), np.zeros((4, 4), dtype=np.uint8)],
)
def test_successful_read_with_invalid_frame_is_not_connected(bad_frame):
    camera = Camera()
    capture = MagicMock()
    capture.isOpened.return_value = True

    def read_once():
        camera.running = False
        return True, bad_frame

    capture.read.side_effect = read_once
    camera.cap = capture
    camera.running = True

    camera._update()

    assert camera.is_connected is False
    assert camera.frame_queue.empty()
    assert camera.frame_id == 0


def test_flip_failure_does_not_kill_capture_loop():
    camera = Camera()
    frame = np.ones((4, 4, 3), dtype=np.uint8)
    capture = MagicMock()
    capture.isOpened.return_value = True
    reads = 0

    def read_frame():
        nonlocal reads
        reads += 1
        if reads == 2:
            camera.running = False
        return True, frame

    capture.read.side_effect = read_frame
    camera.cap = capture
    camera.running = True

    with patch("src.camera.cv2.flip", side_effect=[RuntimeError("driver frame error"), frame]):
        camera._update()

    assert reads == 2
    assert camera.is_connected is True
    assert camera.read()[1] == 0


def test_is_opened_exception_reopens_capture():
    camera = Camera()
    old_capture = MagicMock()
    old_capture.isOpened.side_effect = RuntimeError("driver disconnected")
    new_capture = MagicMock()
    new_capture.isOpened.return_value = True

    def read_once():
        camera.running = False
        return True, np.ones((4, 4, 3), dtype=np.uint8)

    new_capture.read.side_effect = read_once
    camera.cap = old_capture
    camera.running = True

    with patch("src.camera.cv2.VideoCapture", return_value=new_capture):
        camera._update()

    old_capture.release.assert_called_once_with()
    assert camera.cap is new_capture
    assert camera.read()[1] == 0


def test_release_exception_does_not_prevent_reopen():
    camera = Camera()
    old_capture = MagicMock()
    old_capture.release.side_effect = RuntimeError("driver release error")
    new_capture = MagicMock()
    new_capture.isOpened.return_value = True
    camera.cap = old_capture

    with patch("src.camera.cv2.VideoCapture", return_value=new_capture):
        assert camera._open_capture() is True

    assert camera.cap is new_capture
