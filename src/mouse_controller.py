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
        
    def process_landmarks(self, lms_list, gesture, frame_w, frame_h):
        if not lms_list or len(lms_list) < 21:
            return
            
        index_x, index_y = lms_list[8][1], lms_list[8][2]
        now = time.time()
        
        # Timeout handling
        if self.pinch_state == "PINCH_RELEASED":
            if now - self.last_pinch_time > 0.35:
                # Timed out waiting for second pinch -> single click
                self.mouse.click(button="left")
                self.pinch_state = "IDLE"

        # Determine if we are no longer pinching
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
            
        if gesture == "Pointing":
            self.mouse.move(index_x, index_y, frame_w, frame_h)
            
        elif gesture == "Pinch":
            self.mouse.move(index_x, index_y, frame_w, frame_h)
            if self.pinch_state == "IDLE":
                self.pinch_state = "PINCH_START"
                self.gesture_start_time = now
            elif self.pinch_state == "PINCH_START":
                if now - self.gesture_start_time > 0.3:
                    self.pinch_state = "DRAGGING"
                    self.mouse.drag(start=True)
            elif self.pinch_state == "PINCH_RELEASED":
                self.pinch_state = "SECOND_PINCH_START"
                self.gesture_start_time = now
            elif self.pinch_state == "SECOND_PINCH_START":
                if now - self.gesture_start_time > 0.3:
                    # Treat holding second pinch as drag just in case
                    self.pinch_state = "DRAGGING"
                    self.mouse.drag(start=True)
            
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
            
        elif gesture == "Three Fingers": # Right click
            self.mouse.drag(start=False)
            self.mouse.move(index_x, index_y, frame_w, frame_h)
            if self.last_gesture != "Three Fingers":
                self.mouse.click(button="right")
            
        else:
            self.mouse.drag(start=False)

        self.last_gesture = gesture
