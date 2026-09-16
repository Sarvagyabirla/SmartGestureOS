import pytest
import numpy as np
from src.mouse_controller import MouseController

def create_mock_hand(scale=1.0, dy_offset=0.0):
    # Base hand: wrist at (0.5, 0.5), middle_mcp at (0.5, 0.4)
    # Hand size = 0.1
    from src.models import Landmark
    
    def s(val, base=0.5):
        return base + (val - base) * scale
        
    return [
        Landmark(id=0, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0), # wrist 0
        Landmark(id=1, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=2, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=3, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=4, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=5, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=6, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=7, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=8, pixel_x=500, pixel_y=500, x=s(0.5), y=s(0.3) + dy_offset, z=0.0), # index tip 8
        Landmark(id=9, pixel_x=500, pixel_y=500, x=s(0.5), y=s(0.4), z=0.0), # middle mcp 9
        Landmark(id=10, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=11, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=12, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=13, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=14, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=15, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=16, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=17, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=18, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=19, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
        Landmark(id=20, pixel_x=500, pixel_y=500, x=0.5, y=0.5, z=0.0),
    ]

def test_distance_scaling():
    mc = MouseController()
    from src.event_engine import EventState
    from config import SETTINGS
    if "gestures" not in SETTINGS:
        SETTINGS["gestures"] = {}
    SETTINGS["gestures"]["base_hand_size"] = 0.1
    
    # 1. Normal hand
    h_normal_start = create_mock_hand(scale=1.0, dy_offset=0.0)
    mc.process_landmarks(h_normal_start, "Two Fingers", "Two Fingers", 1920, 1080)
    assert mc.engine.state == EventState.SCROLLING
    assert pytest.approx(mc.engine.scroll_start_y) == 0.3
    
    # move by 0.06 -> triggers scroll
    h_normal_move = create_mock_hand(scale=1.0, dy_offset=0.06)
    mc.process_landmarks(h_normal_move, "Two Fingers", "Two Fingers", 1920, 1080)
    assert pytest.approx(mc.engine.scroll_start_y) == 0.36
    
    mc.engine.state = EventState.HOVER
    
    # 2. Far hand (half size)
    h_far_start = create_mock_hand(scale=0.5, dy_offset=0.0)
    mc.process_landmarks(h_far_start, "Two Fingers", "Two Fingers", 1920, 1080)
    assert pytest.approx(mc.engine.scroll_start_y) == 0.4
    
    # move by 0.03 physical -> scales to 0.06 -> triggers scroll!
    h_far_move = create_mock_hand(scale=0.5, dy_offset=0.03)
    mc.process_landmarks(h_far_move, "Two Fingers", "Two Fingers", 1920, 1080)
    assert pytest.approx(mc.engine.scroll_start_y) == 0.43
