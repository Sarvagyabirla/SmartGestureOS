"""
tests/test_camera.py — hardware-gated camera smoke tests.

These tests require a physical webcam and are excluded from normal CI.
Run with: pytest -m hardware
"""
import sys
import time
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.mark.hardware
def test_camera_init_real():
    """Camera init with real default index. Requires a webcam."""
    from src.camera import Camera
    cam = Camera(index=0)
    assert cam.running is False


@pytest.mark.hardware
def test_camera_start_stop_real():
    """Camera start/stop with real default index. Requires a webcam."""
    from src.camera import Camera
    cam = Camera(index=0)
    cam.start()
    time.sleep(0.5)
    cam.stop()
    assert cam.running is False
