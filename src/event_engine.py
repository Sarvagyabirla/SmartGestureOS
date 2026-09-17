import time
import enum

class EventState(enum.Enum):
    IDLE = 0
    HOVER = 1
    PINCH_DOWN = 2
    PINCH_RELEASE_WAIT = 3
    DRAGGING = 4
    SCROLLING = 5
    COOLDOWN = 6
    HAND_LOST = 7

class EventEngine:
    def __init__(self, mouse_controller):
        self.mouse = mouse_controller
        self.state = EventState.HOVER
        self.last_state_change = time.perf_counter()

        self.scroll_start_y = None
        self.scroll_accumulator = 0.0
        
        self.pinch_down_time = 0.0
        self.pinch_release_time = 0.0
        
        # Configuration
        self.pinch_click_max_ms = 250 / 1000.0
        self.double_click_window_ms = 400 / 1000.0
        self.drag_hold_ms = 350 / 1000.0
        self.cooldown_duration = 150 / 1000.0

    def _change_state(self, new_state):
        if self.state != new_state:
            self.state = new_state
            self.last_state_change = time.perf_counter()

    def on_hand_lost(self):
        """Mandatory failsafe"""
        self.mouse.mouse.drag(start=False)
        self.scroll_start_y = None
        self.scroll_accumulator = 0.0
        self._change_state(EventState.HAND_LOST)

    def process(self, stable_gesture, raw_gesture, index_x, index_y, frame_w, frame_h, lms_list=None, scale_factor=1.0):
        now = time.perf_counter()

        if self.state == EventState.HAND_LOST:
            if lms_list and len(lms_list) > 0 and stable_gesture != "None" and stable_gesture != "Unknown":
                self._change_state(EventState.HOVER)

        # Always update mouse position on movement gestures (if not lost)
        if raw_gesture in ["Pointing", "Pinch", "Three Fingers", "Victory", "Two Fingers", "Closed Fist"] and self.state != EventState.HAND_LOST:
            self.mouse.mouse.move(index_x, index_y, frame_w, frame_h)

        if self.state == EventState.HOVER:
            if stable_gesture == "Pinch":
                self.pinch_down_time = now
                self._change_state(EventState.PINCH_DOWN)
            elif stable_gesture == "Two Fingers":
                self.scroll_start_y = lms_list[8].y if lms_list else None
                self.scroll_accumulator = 0.0
                self._change_state(EventState.SCROLLING)
            elif stable_gesture == "Three Fingers":
                self.mouse.mouse.click(button="right")
                self._change_state(EventState.COOLDOWN)

        elif self.state == EventState.PINCH_DOWN:
            if stable_gesture != "Pinch":
                # Pinch was released
                hold_duration = now - self.pinch_down_time
                if hold_duration < self.drag_hold_ms:
                    # Quick release -> Go to wait state for possible double click
                    self.pinch_release_time = now
                    self._change_state(EventState.PINCH_RELEASE_WAIT)
                else:
                    # Was already dragging, but missed the state? Or just released after hold threshold.
                    self.mouse.mouse.drag(start=False)
                    self._change_state(EventState.COOLDOWN)
            else:
                hold_duration = now - self.pinch_down_time
                if hold_duration >= self.drag_hold_ms:
                    self.mouse.mouse.drag(start=True)
                    self._change_state(EventState.DRAGGING)

        elif self.state == EventState.PINCH_RELEASE_WAIT:
            if stable_gesture == "Pinch":
                # Second pinch within the window!
                self.mouse.mouse.double_click()
                self._change_state(EventState.COOLDOWN)
            else:
                if now - self.pinch_release_time > self.double_click_window_ms:
                    # Time elapsed, no second pinch. Perform single click.
                    self.mouse.mouse.click(button="left")
                    self._change_state(EventState.HOVER)

        elif self.state == EventState.DRAGGING:
            if stable_gesture != "Pinch":
                self.mouse.mouse.drag(start=False)
                self._change_state(EventState.COOLDOWN)

        elif self.state == EventState.SCROLLING:
            if stable_gesture != "Two Fingers":
                self.scroll_start_y = None
                self.scroll_accumulator = 0.0
                self._change_state(EventState.HOVER)
            elif lms_list and self.scroll_start_y is not None:
                current_y = lms_list[8].y
                dy = (current_y - self.scroll_start_y) * scale_factor
                
                # Accumulate the scroll delta
                self.scroll_accumulator += dy
                
                # Threshold to emit scroll tick
                scroll_threshold = 0.03
                while self.scroll_accumulator > scroll_threshold:
                    self.mouse.mouse.scroll(-1)
                    self.scroll_accumulator -= scroll_threshold
                while self.scroll_accumulator < -scroll_threshold:
                    self.mouse.mouse.scroll(1)
                    self.scroll_accumulator += scroll_threshold
                    
                self.scroll_start_y = current_y

        elif self.state == EventState.COOLDOWN:
            if now - self.last_state_change >= self.cooldown_duration:
                self._change_state(EventState.HOVER)
