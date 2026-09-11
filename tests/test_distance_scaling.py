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
        Landmark(0, 500, 500, 0.5, 0.5, 0.0), # wrist 0
        Landmark(1, 500, 500, 0.5, 0.5, 0.0),
        Landmark(2, 500, 500, 0.5, 0.5, 0.0),
        Landmark(3, 500, 500, 0.5, 0.5, 0.0),
        Landmark(4, 500, 500, 0.5, 0.5, 0.0),
        Landmark(5, 500, 500, 0.5, 0.5, 0.0),
        Landmark(6, 500, 500, 0.5, 0.5, 0.0),
        Landmark(7, 500, 500, 0.5, 0.5, 0.0),
        Landmark(8, 500, 500, s(0.5), s(0.3) + dy_offset, 0.0), # index tip 8
        Landmark(9, 500, 500, s(0.5), s(0.4), 0.0), # middle mcp 9
        Landmark(10, 500, 500, 0.5, 0.5, 0.0),
        Landmark(11, 500, 500, 0.5, 0.5, 0.0),
        Landmark(12, 500, 500, 0.5, 0.5, 0.0),
        Landmark(13, 500, 500, 0.5, 0.5, 0.0),
        Landmark(14, 500, 500, 0.5, 0.5, 0.0),
        Landmark(15, 500, 500, 0.5, 0.5, 0.0),
        Landmark(16, 500, 500, 0.5, 0.5, 0.0),
        Landmark(17, 500, 500, 0.5, 0.5, 0.0),
        Landmark(18, 500, 500, 0.5, 0.5, 0.0),
        Landmark(19, 500, 500, 0.5, 0.5, 0.0),
        Landmark(20, 500, 500, 0.5, 0.5, 0.0),
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
