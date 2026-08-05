import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.camera import Camera

def test_camera_init():
    cam = Camera(index=-1) # Invalid index
    # Depending on OpenCV build, -1 might open default camera or fail
    if cam.cap and cam.cap.isOpened():
        cam.cap.release()
    assert cam.running == False
    
def test_camera_start_stop():
    cam = Camera(index=-1)
    cam.start()
    time.sleep(0.1)
    cam.stop()
    assert cam.running == False
