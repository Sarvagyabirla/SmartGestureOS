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

import ctypes
import time
import enum
import math

# ── Gesture double-click window ─────────────────────────────────────────────
# Bounded window: long enough for deliberate two-pinch cycle,
# short enough so single-click latency feels crisp.
_GESTURE_WINDOW_SCALE = 1.2
_GESTURE_WINDOW_MIN_MS = 250.0
_GESTURE_WINDOW_MAX_MS = 380.0


def windows_double_click_time_ms(default: int = 500) -> int:
    """Windows' configured double-click interval, or a safe default."""
    try:
        value = int(ctypes.windll.user32.GetDoubleClickTime())
    except Exception:
        return default
    return value if 100 <= value <= 2000 else default


def gesture_double_click_window_ms() -> float:
    """Gesture-appropriate double-click window in milliseconds."""
    scaled = windows_double_click_time_ms() * _GESTURE_WINDOW_SCALE
    return min(_GESTURE_WINDOW_MAX_MS, max(_GESTURE_WINDOW_MIN_MS, scaled))



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
        # Scroll intent hysteresis. A single dropped classifier frame used to
        # end SCROLLING and zero the accumulator, so one noisy "Two Fingers"
        # read permanently truncated a real scroll. Bounded grace tolerates
        # classifier uncertainty only; a genuinely conflicting pose still
        # stops scrolling on the same frame.
        self._scroll_last_confirmed_at = 0.0
        self.scroll_exit_grace_s = 0.12

        self.pinch_down_time = 0.0
        self.pinch_release_time = 0.0
        self._pinch_consumed = False
        self._second_pinch_pending = False

        # F-06 FIX: track whether right-click gesture was released before re-arming
        self._right_click_armed = True  # True = ready to fire right-click

        # Configuration (updated by settings callback in MouseController)
        # Double-click window is derived from the Windows mouse interval rather
        # than hardcoded; see gesture_double_click_window_ms().
        self.double_click_window_ms = gesture_double_click_window_ms() / 1000.0
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
        self._second_pinch_pending = False
        self.scroll_start_y = None
        self.scroll_accumulator = 0.0
        self._scroll_last_confirmed_at = 0.0
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
        # A transient raw pose must agree with the stable classifier before it
        # can begin a click or scroll. Raw release still ends an active action
        # immediately, even while the stable label catches up.
        can_start_action = (stable_gesture == raw_gesture
                            and stable_gesture not in (None, "None", "Unknown"))
        if not is_pinching:
            self._pinch_consumed = False

        # ── Re-acquire from HAND_LOST ──────────────────────────────────────────
        if self.state == EventState.HAND_LOST:
            if lms_list and len(lms_list) >= 21:
                self._change_state(EventState.HOVER)
            else:
                return  # Still lost; do nothing

        # ── Drag cursor ───────────────────────────────────────────────────────
        # Cursor *navigation* is no longer this engine's job: it lived in
        # MouseController.process_pointer so a transient raw pose could not
        # freeze the cursor, and so a slow discrete action could not stall it.
        # A held drag is different — the left button is down, so the target
        # must follow the fingertip and must be dropped on release.
        if self.state == EventState.DRAGGING and is_pinching:
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
                # Stamp the entry frame, otherwise the first uncertain frame
                # would compare against a stale zero and end the scroll.
                self._scroll_last_confirmed_at = now
                self._change_state(EventState.SCROLLING)

            elif stable_gesture == raw_gesture == "Three Fingers" and self._right_click_armed:
                # F-06 FIX: fire once, then require release before re-arming
                self.mouse.mouse.click(button="right")
                self._right_click_armed = False
                self._change_state(EventState.COOLDOWN)

        elif self.state == EventState.PINCH_DOWN:
            hold_duration = now - self.pinch_down_time
            if not is_pinching:
                if self._second_pinch_pending and hold_duration < self.drag_hold_ms:
                    # The second pinch began in the window and stayed short.
                    self.mouse.mouse.double_click()
                    self._second_pinch_pending = False
                    self._pinch_consumed = True
                    self._change_state(EventState.COOLDOWN)
                else:
                    if self._second_pinch_pending:
                        # The second pinch lasted too long for a double click,
                        # but no held sample began a drag before this release.
                        self.mouse.mouse.click(button="left")
                        self._second_pinch_pending = False
                    # No button was pressed while still in PINCH_DOWN. A release
                    # first observed after the hold deadline must not swallow
                    # the click; only a held sample can start an actual drag.
                    self.pinch_release_time = now
                    self._change_state(EventState.PINCH_RELEASE_WAIT)
            else:
                if hold_duration >= self.drag_hold_ms:
                    if self._second_pinch_pending:
                        # The second pinch started in the double-click window,
                        # then became a hold. Complete the first click before
                        # beginning the drag.
                        self.mouse.mouse.click(button="left")
                        self._second_pinch_pending = False
                    self.mouse.mouse.drag(start=True)
                    self._change_state(EventState.DRAGGING)
                    self.mouse.mouse.move(index_x, index_y, frame_w, frame_h)

        elif self.state == EventState.PINCH_RELEASE_WAIT:
            if is_pinching:
                if now - self.pinch_release_time <= self.double_click_window_ms:
                    # Wait for the second release to distinguish a short pinch
                    # from a hold that should become a drag.
                    self._second_pinch_pending = True
                    self.pinch_down_time = now
                    self._change_state(EventState.PINCH_DOWN)
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
            if is_scrolling:
                self._scroll_last_confirmed_at = now
            if not is_scrolling:
                uncertain = raw_gesture in ("Unknown", "None")
                within_grace = (
                    uncertain
                    and (now - self._scroll_last_confirmed_at) <= self.scroll_exit_grace_s
                )
                if within_grace:
                    # Discard the gap. Re-anchoring to the current hand
                    # position means resuming cannot replay the unobserved
                    # motion as a wheel jump. Nothing accumulates or emits
                    # while the pose is uncertain.
                    if lms_list:
                        grace_y = lms_list[8].y
                        self.scroll_start_y = (
                            grace_y if math.isfinite(grace_y) and 0.0 <= grace_y <= 1.0
                            else None
                        )
                    return
                self.scroll_start_y = None
                self.scroll_accumulator = 0.0
                self._scroll_last_confirmed_at = 0.0
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
