"""Stopping a camera must invalidate queued and in-flight observations."""

from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.camera import Camera


def test_stop_discards_frame_captured_before_shutdown():
    camera = Camera()
    camera.running = True
    camera.is_connected = True
    camera.frame_queue.put((np.zeros((2, 2, 3), dtype=np.uint8), 1, 1.0))

    camera.stop()

    assert camera.read_with_timestamp()[0] is None
    assert not camera.is_connected


def test_delayed_read_cannot_reconnect_after_stop_or_race_a_restart():
    camera = Camera()
    read_started = Event()
    return_frame = Event()
    read_finished = Event()
    capture = MagicMock()
    capture.isOpened.return_value = True

    def delayed_read():
        read_started.set()
        assert return_frame.wait(timeout=5.0)
        read_finished.set()
        return True, np.ones((2, 2, 3), dtype=np.uint8)

    capture.read.side_effect = delayed_read
    with patch("src.camera.cv2.VideoCapture", return_value=capture) as create:
        camera.start()
        worker = camera._thread
        try:
            assert read_started.wait(timeout=1.0)
            # Reproduce a native read exceeding stop's bounded join without
            # making the test spend two seconds waiting for the driver.
            with patch.object(worker, "join"):
                camera.stop()
            assert not camera.is_connected
            # Native release must not overlap a capture call still in progress.
            capture.release.assert_not_called()
            assert camera.start() is False
            assert create.call_count == 1
        finally:
            return_frame.set()
            worker.join(timeout=2.0)
            camera.stop()

    assert read_finished.is_set()
    assert not worker.is_alive()
    assert not camera.is_connected
    assert camera.read_with_timestamp() == (None, -1, None)
    capture.release.assert_called_once_with()


@pytest.mark.parametrize("disconnect", [False, True])
def test_capture_rate_measures_frames_and_resets_on_loss(monkeypatch, disconnect):
    camera = Camera(fps=30)
    clock = SimpleNamespace(now=10.0)
    monkeypatch.setattr("src.camera.time.perf_counter", lambda: clock.now)
    capture = MagicMock()
    capture.isOpened.return_value = True
    frame = np.ones((2, 2, 3), dtype=np.uint8)
    readings = 0

    def read():
        nonlocal readings
        readings += 1
        clock.now = 10.0 + readings * 0.05
        if readings == 3:
            camera.running = False
        if disconnect and readings == 3:
            return False, None
        return True, frame

    capture.read.side_effect = read
    camera.cap = capture
    camera.running = True
    camera._update()

    assert camera.measured_fps == pytest.approx(0.0 if disconnect else 20.0)
    clock.now += 1.1
    assert camera.measured_fps == 0.0
    camera.stop()
    assert camera.measured_fps == 0.0
