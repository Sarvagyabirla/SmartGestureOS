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
        self.pinch_count = 0
        self.last_pinch_time = 0
        
    def process_landmarks(self, lms_list, gesture, frame_w, frame_h):
        if not lms_list or len(lms_list) < 21:
            return
            
        index_x, index_y = lms_list[8][1], lms_list[8][2]
        now = time.time()
        
        # Determine if we are no longer pinching
        if gesture != "Pinch" and self.last_gesture == "Pinch":
            duration = now - self.gesture_start_time
            if duration <= 0.3:
                # Short pinch released -> register click candidate
                self.pinch_count += 1
                self.last_pinch_time = now
            # Always end drag if we were dragging
            self.mouse.drag(start=False)
            
        # Execute clicks after timeout if no second pinch arrives
        if self.pinch_count > 0 and now - self.last_pinch_time > 0.35:
            if self.pinch_count == 1:
                self.mouse.click(button="left")
            elif self.pinch_count >= 2:
                self.mouse.double_click()
            self.pinch_count = 0
        
        if gesture == "Pointing":
            self.mouse.move(index_x, index_y, frame_w, frame_h)
            self.last_gesture = gesture
            
        elif gesture == "Pinch":
            self.mouse.move(index_x, index_y, frame_w, frame_h)
            if self.last_gesture != "Pinch":
                self.gesture_start_time = now
            elif now - self.gesture_start_time > 0.3:
                # Long pinch -> Drag
                self.mouse.drag(start=True)
                self.pinch_count = 0 # invalidate clicks
            self.last_gesture = gesture
            
        elif gesture == "Two Fingers":
            self.mouse.drag(start=False)
            # Use y coordinate of index finger for scrolling
            current_y = lms_list[8][2]
            if self.last_gesture != "Two Fingers":
                self.scroll_start_y = current_y
            else:
                dy = current_y - self.scroll_start_y
                # If hand moves down, scroll down (negative wheel), if up, scroll up
                if dy > 0.05: # threshold based on normalized coordinates (usually 0-1)
                    self.mouse.scroll(-1)
                    self.scroll_start_y = current_y
                elif dy < -0.05:
                    self.mouse.scroll(1)
                    self.scroll_start_y = current_y
            self.last_gesture = gesture
            
        elif gesture == "Three Fingers": # Right click
            self.mouse.drag(start=False)
            self.mouse.move(index_x, index_y, frame_w, frame_h)
            if self.last_gesture != "Three Fingers":
                self.mouse.click(button="right")
            self.last_gesture = gesture
            
        else:
            self.mouse.drag(start=False)
            self.last_gesture = gesture
