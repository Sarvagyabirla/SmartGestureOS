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
from typing import Optional
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



def _extract_scroll_y(lms_list) -> float | None:
    """Extract normalized Y for vertical scroll tracking.
    
    Uses validated index tip (8) normalized Y coordinate.
    """
    if not lms_list or len(lms_list) < 9:
        return None
    y8 = getattr(lms_list[8], "y", None)
    if isinstance(y8, (int, float)) and math.isfinite(y8) and (0.0 <= y8 <= 1.0):
        return float(y8)
    return None


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
        self._scroll_anchor_y = None
        self._scroll_deadzone_cleared = False
        self.scroll_accumulator = 0.0
        self._scroll_last_confirmed_at = 0.0
        self.scroll_exit_grace_s = 0.12

        self.pinch_down_time = 0.0
        self.pinch_release_time = 0.0
        self._pinch_consumed = False
        self._second_pinch_pending = False
        self.click_anchor = None
        self.last_click_time = 0.0
        self.last_click_pos = None

        # F-06 FIX: right-click release gate and short deliberate confirmation
        self._right_click_armed = True  # True = ready to fire right-click
        self._three_fingers_start_time = 0.0

        # Configuration (updated by settings callback in MouseController)
        self.double_click_window_ms = gesture_double_click_window_ms() / 1000.0
        self.drag_hold_ms = 350 / 1000.0
        self.cooldown_duration = 100 / 1000.0

    def _change_state(self, new_state: EventState, now: Optional[float] = None) -> None:
        if self.state != new_state:
            self.state = new_state
            self.last_state_change = now if now is not None else time.perf_counter()

    def reset(self) -> None:
        """
        Failsafe reset of all temporal state, timers, scroll accumulator,
        and releases all active mouse events.
        """
        self.pinch_down_time = 0.0
        self.pinch_release_time = 0.0
        self._pinch_consumed = False
        self._second_pinch_pending = False
        self.click_anchor = None
        self.last_click_pos = None
        self._three_fingers_start_time = 0.0
        self._scroll_anchor_y = None
        self._scroll_deadzone_cleared = False
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
        confidence: float = 0.0,
        now: Optional[float] = None,
    ) -> None:
        if now is None:
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
                self._change_state(EventState.HOVER, now=now)
            else:
                return  # Still lost; do nothing

        # ── Drag cursor ───────────────────────────────────────────────────────
        if self.state == EventState.DRAGGING:
            if is_pinching:
                # Section 37: Use pinch midpoint for superior drag stability
                if lms_list and len(lms_list) >= 21 and hasattr(lms_list[4], "pixel_x") and hasattr(lms_list[8], "pixel_x"):
                    drag_x = int((lms_list[4].pixel_x + lms_list[8].pixel_x) / 2.0)
                    drag_y = int((lms_list[4].pixel_y + lms_list[8].pixel_y) / 2.0)
                else:
                    drag_x, drag_y = index_x, index_y
                self.mouse.mouse.move(drag_x, drag_y, frame_w, frame_h)
            else:
                self.mouse.mouse.drag(start=False)
                self._change_state(EventState.COOLDOWN, now=now)

        # ── F-06 FIX: right-click release gate ────────────────────────────────
        if stable_gesture != "Three Fingers" and raw_gesture != "Three Fingers":
            self._right_click_armed = True
            self._three_fingers_start_time = 0.0

        # ── State transitions ──────────────────────────────────────────────────
        if self.state == EventState.HOVER:
            if is_pinching and (can_start_action or confidence >= 50.0) and not self._pinch_consumed:
                # Section 28: Anchor cursor on pinch onset to eliminate click target drift
                self.click_anchor = self.mouse.mouse.get_cursor_pos()
                self.pinch_down_time = now
                self._change_state(EventState.PINCH_DOWN, now=now)

            elif is_scrolling and can_start_action:
                y = _extract_scroll_y(lms_list)
                self.scroll_start_y = y
                self._scroll_anchor_y = y
                self._scroll_deadzone_cleared = False
                self.scroll_accumulator = 0.0
                self._scroll_last_confirmed_at = now
                self._change_state(EventState.SCROLLING, now=now)

            elif stable_gesture == raw_gesture == "Three Fingers" and self._right_click_armed:
                # Section 38: Discrete right-click on stable Three Fingers
                self.mouse.mouse.click(button="right")
                self._right_click_armed = False
                self._change_state(EventState.COOLDOWN, now=now)

        elif self.state == EventState.PINCH_DOWN:
            hold_duration = now - self.pinch_down_time
            if not is_pinching:
                # Section 25 & 26: Immediate single click on pinch release!
                # Windows natively forms a double click if two clicks occur close in time.
                self.mouse.mouse.click(button="left")
                self.pinch_release_time = now
                self.last_click_time = now
                self.last_click_pos = self.click_anchor
                self._pinch_consumed = True
                if self._second_pinch_pending:
                    self._second_pinch_pending = False
                    self._change_state(EventState.COOLDOWN, now=now)
                else:
                    self._change_state(EventState.PINCH_RELEASE_WAIT, now=now)
            else:
                # Section 32: Adaptive drag intent (motion-based or hold-based)
                mapped = getattr(self.mouse.mouse, "map_coordinates", None)
                if callable(mapped):
                    try:
                        res = mapped(index_x, index_y, frame_w, frame_h)
                        screen_x, screen_y = res if isinstance(res, (tuple, list)) and len(res) == 2 else (index_x, index_y)
                    except Exception:
                        screen_x, screen_y = index_x, index_y
                else:
                    screen_x, screen_y = index_x, index_y

                anchor = self.click_anchor
                if isinstance(anchor, (tuple, list)) and len(anchor) == 2:
                    anchor_x, anchor_y = anchor
                else:
                    anchor_x, anchor_y = screen_x, screen_y
                displacement = math.hypot(screen_x - anchor_x, screen_y - anchor_y)

                is_drag_motion = (hold_duration >= 0.12 and displacement >= 16.0)
                is_drag_hold = (hold_duration >= self.drag_hold_ms)

                if is_drag_motion or is_drag_hold:
                    if self._second_pinch_pending:
                        self._second_pinch_pending = False
                    # Section 31: Seed smoother from click anchor for smooth drag start (no snap)
                    seed_func = getattr(self.mouse.mouse, "seed_smoother", None)
                    if callable(seed_func):
                        try:
                            seed_func(anchor_x, anchor_y)
                        except Exception:
                            pass
                    self.mouse.mouse.drag(start=True)
                    self._change_state(EventState.DRAGGING, now=now)
                    # Section 37: Drag coordinate source
                    if lms_list and len(lms_list) >= 21 and hasattr(lms_list[4], "pixel_x") and hasattr(lms_list[8], "pixel_x"):
                        init_drag_x = int((lms_list[4].pixel_x + lms_list[8].pixel_x) / 2.0)
                        init_drag_y = int((lms_list[4].pixel_y + lms_list[8].pixel_y) / 2.0)
                    else:
                        init_drag_x, init_drag_y = index_x, index_y
                    self.mouse.mouse.move(init_drag_x, init_drag_y, frame_w, frame_h)

        elif self.state == EventState.PINCH_RELEASE_WAIT:
            if is_pinching:
                if now - self.pinch_release_time <= self.double_click_window_ms:
                    self._second_pinch_pending = True
                    self.click_anchor = self.mouse.mouse.get_cursor_pos()
                    self.pinch_down_time = now
                    self._change_state(EventState.PINCH_DOWN, now=now)
                else:
                    self.click_anchor = self.mouse.mouse.get_cursor_pos()
                    self.pinch_down_time = now
                    self._second_pinch_pending = False
                    self._change_state(EventState.PINCH_DOWN, now=now)
            elif now - self.pinch_release_time > self.double_click_window_ms:
                # Window expired; first click was already emitted immediately
                self._change_state(EventState.HOVER, now=now)

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
                    if lms_list:
                        self.scroll_start_y = _extract_scroll_y(lms_list)
                    return
                self.scroll_start_y = None
                self._scroll_anchor_y = None
                self._scroll_deadzone_cleared = False
                self.scroll_accumulator = 0.0
                self._scroll_last_confirmed_at = 0.0
                self._change_state(EventState.HOVER, now=now)
            elif lms_list:
                current_y = _extract_scroll_y(lms_list)
                if current_y is None:
                    self.scroll_start_y = None
                    self.scroll_accumulator = 0.0
                    return

                # Section 40: Initial deadzone around entry anchor to prevent start twitch
                if not self._scroll_deadzone_cleared:
                    if self._scroll_anchor_y is not None and abs(current_y - self._scroll_anchor_y) >= 0.015:
                        self._scroll_deadzone_cleared = True
                    else:
                        return

                if self.scroll_start_y is not None:
                    scale = scale_factor if math.isfinite(scale_factor) and scale_factor > 0 else 1.0
                    scale = min(4.0, max(0.25, scale))
                    dy = (current_y - self.scroll_start_y) * scale
                    self.scroll_accumulator += dy

                    # Section 42 & 43: Bounded velocity (-3 <= ticks <= 3)
                    scroll_threshold = 0.03
                    ticks = math.trunc(self.scroll_accumulator / scroll_threshold)
                    if ticks:
                        clamped_ticks = -max(-3, min(3, ticks))
                        self.mouse.mouse.scroll(clamped_ticks)
                        self.scroll_accumulator -= ticks * scroll_threshold
                self.scroll_start_y = current_y

        elif self.state == EventState.COOLDOWN:
            if now - self.last_state_change >= self.cooldown_duration:
                self._change_state(EventState.HOVER, now=now)
