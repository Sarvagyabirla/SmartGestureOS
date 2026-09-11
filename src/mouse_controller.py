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
        self.last_gesture = None
        self.gesture_start_time = 0
        self.scroll_start_y = 0
        self.pinch_state = "IDLE"
        self.last_pinch_time = 0
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
        now = time.time()
        
        # Calculate geometric scale factor based on bounding box / hand size
        from config import SETTINGS
        import numpy as np
        wrist = np.array([lms_list[0].x, lms_list[0].y, lms_list[0].z])
        middle_mcp = np.array([lms_list[9].x, lms_list[9].y, lms_list[9].z])
        current_hand_size = max(0.01, np.linalg.norm(wrist - middle_mcp))
        base_hand_size = SETTINGS.get("gestures", {}).get("base_hand_size", current_hand_size)
        scale_factor = base_hand_size / current_hand_size
        
        # Move cursor immediately based on raw_gesture to eliminate lag
        if raw_gesture in ["Pointing", "Pinch", "Three Fingers", "Victory", "Two Fingers", "Closed Fist"]:
            self.mouse.move(index_x, index_y, frame_w, frame_h)
        
        # Timeout handling for single click vs double click
        if self.pinch_state == "PINCH_RELEASED":
            if now - self.last_pinch_time > 0.25:
                # Timed out waiting for second pinch -> single click
                self.mouse.click(button="left")
                self.pinch_state = "IDLE"

        # Determine if we are no longer pinching using raw_gesture to eliminate lag
        gesture = raw_gesture
        if gesture != "Pinch" and self.last_gesture == "Pinch":
            if self.pinch_state == "PINCH_START":
                self.pinch_state = "PINCH_RELEASED"
                self.last_pinch_time = now
            elif self.pinch_state == "SECOND_PINCH_START":
                self.mouse.double_click()
                self.pinch_state = "IDLE"
            elif self.pinch_state == "DRAGGING":
                self.mouse.drag(start=False)
                self.pinch_state = "IDLE"
            
        if gesture == "Pinch":
            if self.pinch_state == "IDLE":
                self.pinch_state = "PINCH_START"
                self.gesture_start_time = now
            elif self.pinch_state == "PINCH_START":
                if now - self.gesture_start_time > 0.15: # Reduced from 0.3 to eliminate lag
                    self.pinch_state = "DRAGGING"
                    self.mouse.drag(start=True)
            elif self.pinch_state == "PINCH_RELEASED":
                self.pinch_state = "SECOND_PINCH_START"
                self.gesture_start_time = now
            elif self.pinch_state == "SECOND_PINCH_START":
                if now - self.gesture_start_time > 0.15:
                    # Treat holding second pinch as drag just in case
                    self.pinch_state = "DRAGGING"
                    self.mouse.drag(start=True)
            
        elif gesture == "Two Fingers":
            self.mouse.drag(start=False)
            # Use normalized y coordinate for scrolling
            current_y = lms_list[8].y
            if self.last_gesture != "Two Fingers":
                self.scroll_start_y = current_y
            else:
                dy = (current_y - self.scroll_start_y) * scale_factor
                # If hand moves down, scroll down (negative wheel), if up, scroll up
                if dy > 0.05: 
                    self.mouse.scroll(-1)
                    self.scroll_start_y = current_y
                elif dy < -0.05:
                    self.mouse.scroll(1)
                    self.scroll_start_y = current_y
            
        elif gesture == "Three Fingers": # Right click
            self.mouse.drag(start=False)
            if self.last_gesture != "Three Fingers":
                self.mouse.click(button="right")
            
        else:
            self.mouse.drag(start=False)

        self.last_gesture = gesture
