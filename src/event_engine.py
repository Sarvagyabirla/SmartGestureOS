import time
import enum

class EventState(enum.Enum):
    HOVER = 1
    DRAGGING = 2
    SCROLLING = 3
    PINCH_WAIT = 4

class EventEngine:
    def __init__(self, mouse_controller):
        self.mouse = mouse_controller
        self.state = EventState.HOVER
        self.last_state_change = time.time()

        self.scroll_start_y = None
        self.pinch_start_time = 0
        self.last_pinch_release_time = 0

        self.debounce_ms = 150 # minimum time in a state before changing

    def _change_state(self, new_state):
        if self.state != new_state:
            self.state = new_state
            self.last_state_change = time.time()

    def process(self, stable_gesture, raw_gesture, index_x, index_y, frame_w, frame_h, lms_list=None, scale_factor=1.0):
        now = time.time()

        # Always update mouse position on movement gestures
        if raw_gesture in ["Pointing", "Pinch", "Three Fingers", "Victory", "Two Fingers", "Closed Fist"]:
            self.mouse.mouse.move(index_x, index_y, frame_w, frame_h)

        # State machine for mouse actions
        if self.state == EventState.HOVER:
            if stable_gesture == "Pinch":
                self.pinch_start_time = now
                self._change_state(EventState.DRAGGING)
                self.mouse.mouse.drag(start=True)
            elif stable_gesture == "Two Fingers":
                self.scroll_start_y = lms_list[8].y if lms_list else None
                self._change_state(EventState.SCROLLING)
            elif stable_gesture == "Three Fingers":
                self.mouse.mouse.click(button="right")
                self._change_state(EventState.HOVER) # stay in hover but trigger action

        elif self.state == EventState.DRAGGING:
            if stable_gesture != "Pinch":
                self.mouse.mouse.drag(start=False)
                drag_duration = now - self.pinch_start_time
                if drag_duration < 0.25:
                    # It was a quick pinch -> treat as click
                    self.last_pinch_release_time = now
                    self._change_state(EventState.PINCH_WAIT)
                else:
                    self._change_state(EventState.HOVER)

        elif self.state == EventState.PINCH_WAIT:
            # Wait for double click or fallback to single click
            if stable_gesture == "Pinch":
                # Second pinch arrived -> double click!
                self.mouse.mouse.double_click()
                self._change_state(EventState.HOVER)
            elif now - self.last_pinch_release_time > 0.3:
                # Timeout -> single click!
                self.mouse.mouse.click(button="left")
                self._change_state(EventState.HOVER)

        elif self.state == EventState.SCROLLING:
            if stable_gesture != "Two Fingers":
                self._change_state(EventState.HOVER)
                self.scroll_start_y = None
            elif lms_list and self.scroll_start_y is not None:
                current_y = lms_list[8].y
                dy = (current_y - self.scroll_start_y) * scale_factor
                if dy > 0.05:
                    self.mouse.mouse.scroll(-1)
                    self.scroll_start_y = current_y
                elif dy < -0.05:
                    self.mouse.mouse.scroll(1)
                    self.scroll_start_y = current_y
