import time
from .virtual_mouse import VirtualMouse
from .utils import get_distance
from .logger import logger

class MouseController:
    def __init__(self):
        from config import SETTINGS
        # Calculate derived OneEuro filter params based on a 0-1 sensitivity slider
        sensitivity = SETTINGS.get("gestures", {}).get("sensitivity", 0.7)
        beta = max(0.01, sensitivity * 0.5) # higher sensitivity = more responsive
        min_cutoff = max(0.1, (1.0 - sensitivity) * 1.5) # lower sensitivity = more smoothing
        
        self.mouse = VirtualMouse(min_cutoff=min_cutoff, beta=beta, deadzone=1.0)
        from .event_engine import EventEngine
        self.engine = EventEngine(self)
        
        from src.settings_manager import settings_manager
        settings_manager.register_callback(self.on_settings_changed)
        
    def on_settings_changed(self):
        from config import SETTINGS
        sensitivity = SETTINGS.get("gestures", {}).get("sensitivity", 0.7)
        beta = max(0.01, sensitivity * 0.5)
        min_cutoff = max(0.1, (1.0 - sensitivity) * 1.5)
        self.mouse.smoother.min_cutoff = min_cutoff
        self.mouse.smoother.beta = beta
        self.mouse.deadzone = max(0.1, (1.0 - sensitivity) * 2.0)
        
    def process_landmarks(self, lms_list, stable_gesture, raw_gesture, frame_w, frame_h):
        if not lms_list or len(lms_list) < 21:
            return
            
        index_x, index_y = lms_list[8].pixel_x, lms_list[8].pixel_y
        
        # Calculate geometric scale factor based on bounding box / hand size
        from config import SETTINGS
        import numpy as np
        wrist = np.array([lms_list[0].x, lms_list[0].y, lms_list[0].z])
        middle_mcp = np.array([lms_list[9].x, lms_list[9].y, lms_list[9].z])
        current_hand_size = max(0.01, np.linalg.norm(wrist - middle_mcp))
        base_hand_size = SETTINGS.get("gestures", {}).get("base_hand_size", current_hand_size)
        scale_factor = base_hand_size / current_hand_size
        
        # Delegate to robust state machine event engine
        self.engine.process(
            stable_gesture=stable_gesture,
            raw_gesture=raw_gesture,
            index_x=index_x,
            index_y=index_y,
            frame_w=frame_w,
            frame_h=frame_h,
            lms_list=lms_list,
            scale_factor=scale_factor
        )
