"""
tests/test_camera_full.py
Full camera unit tests with mocked cv2.VideoCapture.
No physical webcam required.
"""
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _mock_cap(opened=True, read_ok=True):
    """Build a mock VideoCapture."""
    import numpy as np
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
    assert cam.running is False  # stopped after stop()


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
    import cv2
    import numpy as np
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

    # set_calls is a set of (prop_id, value) tuples
    set_call_ids = {call[0][0] for call in mock_cap.set.call_args_list}
    assert cv2.CAP_PROP_FRAME_WIDTH in set_call_ids
    assert cv2.CAP_PROP_FRAME_HEIGHT in set_call_ids
    assert cv2.CAP_PROP_FPS in set_call_ids



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


def test_camera_reconnect_reapplies_settings():
    """When isOpened() returns False in _update, _open_capture is called."""
    import cv2
    call_count = [0]
    real_cap = _mock_cap(opened=True)

    original_open = None  # Not used but ensures patch is clean

    with patch("cv2.VideoCapture", return_value=real_cap):
        from src.camera import Camera
        cam = Camera(index=0, width=1280, height=720, fps=30)

        # Simulate isOpened returning False once then True
        real_cap.isOpened.side_effect = [True, False, True, True, True]
        import numpy as np
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        real_cap.read.return_value = (True, fake_frame)

        with patch.object(cam, "_open_capture", wraps=cam._open_capture) as mock_reopen:
            cam.start()
            time.sleep(0.2)
            cam.stop()
            # _open_capture should have been called at least once during reconnect
            assert mock_reopen.call_count >= 1
