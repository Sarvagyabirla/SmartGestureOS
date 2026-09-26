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
import math


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
        self._pinch_consumed = False

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
        self._pinch_consumed = False
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
        # Raw Pinch already has geometric enter/release hysteresis in the
        # classifier. Its stable history can lag an actual release by frames.
        is_pinching = raw_gesture == "Pinch"
        is_scrolling = raw_gesture == "Two Fingers"
        can_start_action = stable_gesture not in (None, "None", "Unknown")
        if not is_pinching:
            self._pinch_consumed = False

        # ── Re-acquire from HAND_LOST ──────────────────────────────────────────
        if self.state == EventState.HAND_LOST:
            if lms_list and len(lms_list) >= 21:
                self._change_state(EventState.HOVER)
            else:
                return  # Still lost; do nothing

        # ── Continuous mouse movement (non-blocking) ───────────────────────────
        # Keep the click target fixed from pinch entry through dispatch. Move
        # a drag only while the pinch is held, then drop at its last position.
        navigating = (
            self.state in (EventState.HOVER, EventState.COOLDOWN)
            and raw_gesture in ("Pointing", "Three Fingers", "Victory", "Closed Fist")
        )
        if navigating or (self.state == EventState.DRAGGING and is_pinching):
            self.mouse.mouse.move(index_x, index_y, frame_w, frame_h)

        # ── F-06 FIX: right-click release gate ────────────────────────────────
        # Re-arm right-click only after Three Fingers gesture is released
        if stable_gesture != "Three Fingers" and raw_gesture != "Three Fingers":
            self._right_click_armed = True

        # ── State transitions ──────────────────────────────────────────────────
        if self.state == EventState.HOVER:
            if is_pinching and can_start_action and not self._pinch_consumed:
                self.pinch_down_time = now
                self._change_state(EventState.PINCH_DOWN)

            elif is_scrolling and can_start_action:
                y = lms_list[8].y if lms_list else float("nan")
                self.scroll_start_y = y if math.isfinite(y) and 0.0 <= y <= 1.0 else None
                self.scroll_accumulator = 0.0
                self._change_state(EventState.SCROLLING)

            elif stable_gesture == raw_gesture == "Three Fingers" and self._right_click_armed:
                # F-06 FIX: fire once, then require release before re-arming
                self.mouse.mouse.click(button="right")
                self._right_click_armed = False
                self._change_state(EventState.COOLDOWN)

        elif self.state == EventState.PINCH_DOWN:
            if not is_pinching:
                # No button was pressed while still in PINCH_DOWN. A release
                # first observed after the hold deadline must not swallow the
                # click; only a held sample can start an actual drag.
                self.pinch_release_time = now
                self._change_state(EventState.PINCH_RELEASE_WAIT)
            else:
                hold_duration = now - self.pinch_down_time
                if hold_duration >= self.drag_hold_ms:
                    self.mouse.mouse.drag(start=True)
                    self._change_state(EventState.DRAGGING)
                    self.mouse.mouse.move(index_x, index_y, frame_w, frame_h)

        elif self.state == EventState.PINCH_RELEASE_WAIT:
            if is_pinching and can_start_action:
                if now - self.pinch_release_time <= self.double_click_window_ms:
                    # Second pinch within double-click window
                    self.mouse.mouse.double_click()
                    self._pinch_consumed = True
                    self._change_state(EventState.COOLDOWN)
                else:
                    # The first click expired. Commit it and treat this as a
                    # fresh pinch so it can become its own click or drag.
                    self.mouse.mouse.click(button="left")
                    self.pinch_down_time = now
                    self._change_state(EventState.PINCH_DOWN)
            elif now - self.pinch_release_time > self.double_click_window_ms:
                # Window elapsed — perform single click
                self.mouse.mouse.click(button="left")
                self._change_state(EventState.HOVER)

        elif self.state == EventState.DRAGGING:
            if not is_pinching:
                self.mouse.mouse.drag(start=False)
                self._change_state(EventState.COOLDOWN)

        elif self.state == EventState.SCROLLING:
            if not is_scrolling:
                self.scroll_start_y = None
                self.scroll_accumulator = 0.0
                self._change_state(EventState.HOVER)
            elif lms_list:
                current_y = lms_list[8].y
                if not math.isfinite(current_y) or not 0.0 <= current_y <= 1.0:
                    self.scroll_start_y = None
                    self.scroll_accumulator = 0.0
                    return
                if self.scroll_start_y is not None:
                    scale = scale_factor if math.isfinite(scale_factor) and scale_factor > 0 else 1.0
                    scale = min(4.0, max(0.25, scale))
                    self.scroll_accumulator += (current_y - self.scroll_start_y) * scale
                    scroll_threshold = 0.03
                    ticks = math.trunc(self.scroll_accumulator / scroll_threshold)
                    if ticks:
                        # One bounded Windows event per frame. Discard excess
                        # whole ticks so an outlier cannot queue future scroll.
                        self.mouse.mouse.scroll(-max(-3, min(3, ticks)))
                        self.scroll_accumulator -= ticks * scroll_threshold
                self.scroll_start_y = current_y

        elif self.state == EventState.COOLDOWN:
            if now - self.last_state_change >= self.cooldown_duration:
                self._change_state(EventState.HOVER)
