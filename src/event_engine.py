"""
EventEngine — deterministic Windows input state machine.

States:
    IDLE        (unused, reserved)
    HOVER       — hand visible, no gesture active
    PINCH_DOWN  — pinch gesture entered, timing for click vs drag
    PINCH_RELEASE_WAIT — short pinch released, waiting for double-click window
    DRAGGING    — pinch held past drag threshold; left button held
    SCROLLING   — two-finger scroll active
    COOLDOWN    — brief post-action delay before accepting new input
    HAND_LOST   — hand or camera not detected; all automation paused

Safety contract:
    on_hand_lost() MUST be called whenever:
        - hand landmarks disappear
        - camera disconnects
        - MediaPipe result TTL expires
        - application shuts down
        - mode changes (via GestureMapper.set_mode → MouseController.release_all)
    This guarantees left-button is never left pressed.
"""

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

        # F-06 FIX: track whether right-click gesture was released before re-arming
        self._right_click_armed = True  # True = ready to fire right-click

        # Configuration (updated by settings callback in MouseController)
        self.double_click_window_ms = 220 / 1000.0  # Crisp double-click window
        self.drag_hold_ms = 350 / 1000.0
        self.cooldown_duration = 150 / 1000.0

    def _change_state(self, new_state: EventState) -> None:
        if self.state != new_state:
            self.state = new_state
            self.last_state_change = time.perf_counter()

    def reset(self) -> None:
        """
        Failsafe reset of all temporal state, timers, scroll accumulator,
        and releases all active mouse events.
        """
        self.pinch_down_time = 0.0
        self.pinch_release_time = 0.0
        self.scroll_start_y = None
        self.scroll_accumulator = 0.0
        self._right_click_armed = True
        self.mouse.mouse.release_all()
        self._change_state(EventState.HAND_LOST)

    def on_hand_lost(self) -> None:
        """
        Mandatory safety failsafe.
        Call this whenever hand tracking, camera, or ML pipeline is unavailable.
        Releases all held mouse buttons and resets automation state.
        """
        self.reset()

    def process(
        self,
        stable_gesture: str,
        raw_gesture: str,
        index_x: int,
        index_y: int,
        frame_w: int,
        frame_h: int,
        lms_list=None,
        scale_factor: float = 1.0,
    ) -> None:
        now = time.perf_counter()

        # ── Re-acquire from HAND_LOST ──────────────────────────────────────────
        if self.state == EventState.HAND_LOST:
            if lms_list and len(lms_list) >= 21:
                self._change_state(EventState.HOVER)
            else:
                return  # Still lost; do nothing

        # ── Continuous mouse movement (non-blocking) ───────────────────────────
        # Move cursor for navigation gestures whenever not actively scrolling
        if self.state != EventState.SCROLLING:
            if raw_gesture in (
                "Pointing", "Pinch", "Three Fingers",
                "Victory", "Two Fingers", "Closed Fist",
            ) or stable_gesture in (
                "Pointing", "Pinch", "Three Fingers",
                "Victory", "Two Fingers", "Closed Fist",
            ):
                self.mouse.mouse.move(index_x, index_y, frame_w, frame_h)

        # ── F-06 FIX: right-click release gate ────────────────────────────────
        # Re-arm right-click only after Three Fingers gesture is released
        if stable_gesture != "Three Fingers" and raw_gesture != "Three Fingers":
            self._right_click_armed = True

        # ── State transitions ──────────────────────────────────────────────────
        if self.state == EventState.HOVER:
            if stable_gesture == "Pinch" or raw_gesture == "Pinch":
                self.pinch_down_time = now
                self._change_state(EventState.PINCH_DOWN)

            elif stable_gesture == "Two Fingers" or raw_gesture == "Two Fingers":
                self.scroll_start_y = lms_list[8].y if lms_list else None
                self.scroll_accumulator = 0.0
                self._change_state(EventState.SCROLLING)

            elif (stable_gesture == "Three Fingers" or raw_gesture == "Three Fingers") and self._right_click_armed:
                # F-06 FIX: fire once, then require release before re-arming
                self.mouse.mouse.click(button="right")
                self._right_click_armed = False
                self._change_state(EventState.COOLDOWN)

        elif self.state == EventState.PINCH_DOWN:
            is_pinching = (stable_gesture == "Pinch" or raw_gesture == "Pinch")
            if not is_pinching:
                # Pinch released
                hold_duration = now - self.pinch_down_time
                if hold_duration < self.drag_hold_ms:
                    # Quick release → wait for possible double-click
                    self.pinch_release_time = now
                    self._change_state(EventState.PINCH_RELEASE_WAIT)
                else:
                    # Was dragging (or hold elapsed) — release
                    self.mouse.mouse.drag(start=False)
                    self._change_state(EventState.COOLDOWN)
            else:
                hold_duration = now - self.pinch_down_time
                if hold_duration >= self.drag_hold_ms:
                    self.mouse.mouse.drag(start=True)
                    self._change_state(EventState.DRAGGING)

        elif self.state == EventState.PINCH_RELEASE_WAIT:
            is_pinching = (stable_gesture == "Pinch" or raw_gesture == "Pinch")
            if is_pinching:
                # Second pinch within double-click window
                self.mouse.mouse.double_click()
                self._change_state(EventState.COOLDOWN)
            elif now - self.pinch_release_time > self.double_click_window_ms:
                # Window elapsed — perform single click
                self.mouse.mouse.click(button="left")
                self._change_state(EventState.HOVER)

        elif self.state == EventState.DRAGGING:
            is_pinching = (stable_gesture == "Pinch" or raw_gesture == "Pinch")
            if not is_pinching:
                self.mouse.mouse.drag(start=False)
                self._change_state(EventState.COOLDOWN)

        elif self.state == EventState.SCROLLING:
            is_scrolling = (stable_gesture == "Two Fingers" or raw_gesture == "Two Fingers")
            if not is_scrolling:
                self.scroll_start_y = None
                self.scroll_accumulator = 0.0
                self._change_state(EventState.HOVER)
            elif lms_list and self.scroll_start_y is not None:
                current_y = lms_list[8].y
                dy = (current_y - self.scroll_start_y) * scale_factor

                self.scroll_accumulator += dy
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
