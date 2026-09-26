import sys
import time
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import OneEuroFilter, PointSmoother
from src.gesture_mapper import GestureHoldTimer
from src.virtual_mouse import VirtualMouse

def test_one_euro_filter():
    t = time.time()
    smoother = PointSmoother(min_cutoff=0.1, beta=0.8)
    
    # Send some noisy points around 100, 100
    x, y = smoother.update(t, 100, 100)
    assert x == 100 and y == 100
    
    x, y = smoother.update(t + 0.016, 110, 90) # Noise spike
    # With min_cutoff=0.1, it should smooth this out to around 108
    assert abs(x - 100) < 10
    assert abs(y - 100) < 10
    
def test_gesture_hold_timer():
    timer = GestureHoldTimer(duration=0.4, repeat_cooldown=0.3)
    
    # Check returns False initially
    assert timer.check("Victory") == False
    
    # Wait 400ms
    time.sleep(0.4)
    # Should return True now
    assert timer.check("Victory", is_repeatable=False) == True
    
    # Check again immediately, should be False because it's not repeatable and already executed
    assert timer.check("Victory", is_repeatable=False) == False
    
    # Switch gesture, should reset
    assert timer.check("Open Palm") == False
    time.sleep(0.4)
    assert timer.check("Open Palm", is_repeatable=True) == True
    # Immediately after, should be False due to cooldown
    assert timer.check("Open Palm", is_repeatable=True) == False
    time.sleep(0.3)
    # Should be True after cooldown
    assert timer.check("Open Palm", is_repeatable=True) == True

def test_virtual_mouse_deadzone():
    vm = VirtualMouse(deadzone=5.0)
    # Retain the real mapping/smoother but never move the user's cursor.
    vm.user32 = MagicMock()
    vm.screen_x = vm.screen_y = 0
    vm.screen_w = 1920
    vm.screen_h = 1080
    
    # Initial move (cam size 1280x720)
    # Center is 640, 360
    vm.move(640, 360, 1280, 720)
    assert vm.last_pos is not None
    initial_pos = vm.last_pos
    
    # Move by just 1 pixel in camera space (should map to small screen movement)
    # If it falls within deadzone, last_pos won't change
    time.sleep(0.016)
    vm.move(641, 360, 1280, 720)
    assert vm.last_pos == initial_pos
    
    # Move far away
    time.sleep(0.016)
    vm.move(1000, 600, 1280, 720)
    # Need to pump a few times because OneEuroFilter smooths out sudden jumps
    for _ in range(5):
        time.sleep(0.016)
        vm.move(1000, 600, 1280, 720)
    assert vm.last_pos != initial_pos

def test_drawing_canvas():
    from src.drawing import DrawingCanvas
    import numpy as np
    
    canvas = DrawingCanvas(width=100, height=100)
    
    # Initially empty
    assert np.count_nonzero(canvas.canvas) == 0
    assert len(canvas.undo_stack) == 1
    
    # Draw something
    canvas.draw(50, 50, draw_mode=True)
    canvas.draw(60, 60, draw_mode=True)
    
    assert np.count_nonzero(canvas.canvas) > 0
    assert len(canvas.undo_stack) == 2 # State before drawing was saved
    
    # Undo
    canvas.draw(50, 50, draw_mode=False) # lift pen
    canvas.undo()
    assert np.count_nonzero(canvas.canvas) == 0
    assert len(canvas.redo_stack) == 1
    
    # Redo
    canvas.redo()
    assert np.count_nonzero(canvas.canvas) > 0
    
    # Clear
    canvas.clear()
    assert np.count_nonzero(canvas.canvas) == 0
    assert len(canvas.undo_stack) == 3
