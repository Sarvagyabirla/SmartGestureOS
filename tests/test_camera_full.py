"""
tests/test_camera_full.py
Full camera unit tests with mocked cv2.VideoCapture.
No physical webcam required.
"""
import sys
import time
import threading
import cv2
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _mock_cap(opened=True, read_ok=True):
    """Build a mock VideoCapture."""
    cap = MagicMock()
    cap.isOpened.return_value = opened
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cap.read.return_value = (read_ok, frame)
    cap.set = MagicMock()
    cap.release = MagicMock()
    return cap


def test_camera_initial_open_success():
    """Camera starts correctly when VideoCapture opens."""
    mock_cap = _mock_cap(opened=True)
    with patch("cv2.VideoCapture", return_value=mock_cap):
        from src.camera import Camera
        cam = Camera(index=0, width=640, height=480, fps=30)
        result = cam.start()
        time.sleep(0.05)
        cam.stop()
    assert result is True
    assert cam.running is False


def test_camera_initial_open_failure():
    """Camera.start() returns False when VideoCapture cannot open."""
    mock_cap = _mock_cap(opened=False)
    with patch("cv2.VideoCapture", return_value=mock_cap):
        from src.camera import Camera
        cam = Camera(index=0)
        result = cam.start()
        cam.stop()
    assert result is False


def test_camera_applies_resolution():
    """Camera applies width, height and fps via CAP_PROP_* constants."""
    mock_cap = _mock_cap(opened=True)
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, fake_frame)

    with patch("cv2.VideoCapture", return_value=mock_cap), \
         patch("cv2.flip", return_value=fake_frame):
        from src.camera import Camera
        cam = Camera(index=0, width=1280, height=720, fps=30)
        cam.start()
        time.sleep(0.05)
        cam.stop()

    set_call_ids = {call[0][0] for call in mock_cap.set.call_args_list}
    assert cv2.CAP_PROP_FRAME_WIDTH  in set_call_ids
    assert cv2.CAP_PROP_FRAME_HEIGHT in set_call_ids
    assert cv2.CAP_PROP_FPS          in set_call_ids


def test_camera_open_capture_helper_releases_old():
    """_open_capture releases an existing cap before creating a new one."""
    mock_cap1 = _mock_cap(opened=True)
    mock_cap2 = _mock_cap(opened=True)
    caps = iter([mock_cap1, mock_cap2])
    with patch("cv2.VideoCapture", side_effect=lambda *a, **k: next(caps)):
        from src.camera import Camera
        cam = Camera(index=0)
        cam.cap = mock_cap1  # pre-existing cap
        cam._open_capture()
        mock_cap1.release.assert_called_once()


def test_camera_stop_cleanup():
    """stop() sets running=False and releases cap."""
    mock_cap = _mock_cap(opened=True)
    with patch("cv2.VideoCapture", return_value=mock_cap):
        from src.camera import Camera
        cam = Camera(index=0)
        cam.start()
        time.sleep(0.05)
        cam.stop()
    assert cam.running is False
    mock_cap.release.assert_called()


def test_camera_is_connected_after_read():
    """is_connected becomes True after a successful read."""
    mock_cap = _mock_cap(opened=True, read_ok=True)
    with patch("cv2.VideoCapture", return_value=mock_cap), \
         patch("cv2.flip", return_value=MagicMock()):
        from src.camera import Camera
        cam = Camera(index=0)
        cam.start()
        time.sleep(0.1)
        connected = cam.is_connected
        cam.stop()
    assert connected is True


def test_read_with_timestamp_returns_monotonic_capture_timestamp():
    import numpy as np
    from src.camera import Camera

    cam = Camera(index=0)
    captured_at = time.perf_counter() - 0.01
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    cam.frame_queue.put((frame, 7, captured_at))

    read_frame, frame_id, read_captured_at = cam.read_with_timestamp()

    assert read_frame is frame
    assert frame_id == 7
    assert read_captured_at == captured_at


def test_camera_reconnect_reapplies_settings():
    """
    Verify that when isOpened() returns False the _update thread calls
    _open_capture again (reconnect), which reapplies width/height/fps.

    Synchronization design (deterministic, no StopIteration):
    ──────────────────────────────────────────────────────────
    A finite side_effect list is UNSAFE here because the background capture
    thread calls isOpened() in a tight loop — it exhausts the list and raises
    StopIteration, producing PytestUnhandledThreadExceptionWarning.

    Instead we use a stateful callable (closure over a list-cell):

        phase 0 → isOpened() → True   (thread runs normally)
        phase 1 → isOpened() → False, then atomically advances to phase 2
        phase 2 → isOpened() → True forever

    The phase-1→2 advance is done *inside* the callable, so only one False
    is ever returned.  Two threading.Events gate progress:

        first_frame_event  — set when the thread reads its first good frame
                             (proves the capture loop is live before we inject
                              the disconnect)
        reconnect_event    — set when _open_capture is called a second time
                             (proves reconnect logic fired)
    """
    # ── Shared state ──────────────────────────────────────────────────────────
    phase = [0]               # list-cell so closures can mutate it
    first_frame_event = threading.Event()
    reconnect_event   = threading.Event()
    open_capture_calls = [0]

    # ── Build the mock cap ────────────────────────────────────────────────────
    real_cap = _mock_cap(opened=True)

    # isOpened: stateful callable — never raises StopIteration
    def _is_opened():
        if phase[0] == 0:
            return True
        if phase[0] == 1:
            # Return False exactly once; advance phase so the very next call
            # (from _open_capture itself) sees True and reconnect succeeds.
            phase[0] = 2
            return False
        return True   # phase 2+: stable True forever

    real_cap.isOpened.side_effect = _is_opened

    # read: signals first_frame_event on first successful call
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    _read_calls = [0]

    def _read():
        _read_calls[0] += 1
        if _read_calls[0] == 1:
            first_frame_event.set()
        return (True, fake_frame)

    real_cap.read.side_effect = _read

    # ── Run ───────────────────────────────────────────────────────────────────
    with patch("cv2.VideoCapture", return_value=real_cap), \
         patch("cv2.flip", return_value=fake_frame):
        from src.camera import Camera
        cam = Camera(index=0, width=1280, height=720, fps=30)

        # Wrap _open_capture to count calls and signal reconnect_event
        _orig_open = cam._open_capture

        def _tracked_open():
            open_capture_calls[0] += 1
            result = _orig_open()
            if open_capture_calls[0] >= 2:
                reconnect_event.set()
            return result

        cam._open_capture = _tracked_open

        # start() calls _open_capture #1 synchronously
        cam.start()

        # Gate 1: wait until the background thread has produced at least one
        # frame (proves the read loop is live).
        assert first_frame_event.wait(timeout=3.0), (
            "Thread never read a frame — camera start() appears broken"
        )

        # Inject disconnect: next isOpened() call returns False (phase 1→2)
        phase[0] = 1

        # Gate 2: wait for the thread to detect the False, call _open_capture
        # again, and signal reconnect_event.
        reconnect_happened = reconnect_event.wait(timeout=3.0)

        cam.stop()

    # ── Assertions ────────────────────────────────────────────────────────────
    assert reconnect_happened, (
        f"Reconnect not detected within timeout. "
        f"_open_capture calls: {open_capture_calls[0]}, phase: {phase[0]}"
    )
    assert open_capture_calls[0] >= 2, (
        f"Expected ≥ 2 _open_capture calls, got {open_capture_calls[0]}"
    )

    # cap.set() must have been called with width/height/fps on reconnect
    set_call_ids = {call[0][0] for call in real_cap.set.call_args_list}
    assert cv2.CAP_PROP_FRAME_WIDTH  in set_call_ids, "Width not reapplied on reconnect"
    assert cv2.CAP_PROP_FRAME_HEIGHT in set_call_ids, "Height not reapplied on reconnect"
    assert cv2.CAP_PROP_FPS          in set_call_ids, "FPS not reapplied on reconnect"

    assert cam.running is False, "Camera should be stopped after stop()"
