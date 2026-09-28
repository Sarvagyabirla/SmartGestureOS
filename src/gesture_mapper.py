"""
GestureMapper — maps stable gestures to desktop actions.

Central temporal reset: GestureMapper.reset_temporal_state()
resets timer, sleep_timer, and all continuous-action state.

Execute-action feedback follows result: speak only on success.

ActionExecutor integration (Stage 4):
    Slow discrete actions (screenshot, app launches, OS shortcuts) are routed
    through ActionExecutor so they run off the inference thread. This prevents
    ImageGrab.grab(), subprocess.Popen() and keyboard.send() from blocking the
    processing loop, which would cause the tracking watchdog to invalidate live
    tracking and the cursor to visibly freeze after every such action.

    Continuous actions (cursor, draw, scroll, drag) always run inline — they
    must not be delayed by a worker queue.
"""
import time
import threading
from config import SETTINGS
from .action_executor import ActionExecutor
from .mouse_controller import MouseController
from .keyboard_controller import KeyboardController
from .media_controller import MediaController
from .desktop_controller import DesktopController
from .shortcut_controller import ShortcutController
from .presentation_controller import PresentationController
from .volume_controller import VolumeController
from .brightness_controller import BrightnessController
from .feedback_controller import FeedbackController
from .drawing import DrawingCanvas
from .utils import get_distance
from .logger import logger

# Actions that are slow enough to block the inference thread if run inline.
# Must NOT include cursor, scroll, drag, draw — those require immediate response.
_ASYNC_ACTIONS = frozenset({
    "screenshot",
    "open_vscode",
    "open_chrome",
    "open_calculator",
    "open_explorer",
    "open_notepad",
    "lock_pc",
    "task_view",
    "show_desktop",
    "save_drawing",
})

# Action-specific policies (Section 20 & 21):
# Centralized action timing, dropout grace, and release gating policy table.
_ACTION_POLICY = {
    # Fast discrete (volume / right click): 200 ms
    "volume_up": {"hold_ms": 200, "dropout_grace_ms": 120, "require_release": False, "repeatable": True},
    "volume_down": {"hold_ms": 200, "dropout_grace_ms": 120, "require_release": False, "repeatable": True},
    "right_click": {"hold_ms": 200, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "play_pause": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "next_track": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "previous_track": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "mute_master": {"hold_ms": 200, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},

    # Normal discrete: 300 ms
    "undo": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "redo": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "cycle_color": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "toggle_eraser": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},

    # High impact discrete: 300 ms (Section 20)
    "screenshot": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "open_vscode": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "open_chrome": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "task_view": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "show_desktop": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "lock_pc": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "switch_mode": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "save_drawing": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "clear_canvas": {"hold_ms": 300, "dropout_grace_ms": 120, "require_release": True, "repeatable": False},
    "toggle_sleep": {"hold_ms": 3000, "dropout_grace_ms": 150, "require_release": True, "repeatable": False},
}

_DEFAULT_ACTION_POLICY = {
    "hold_ms": 300,
    "dropout_grace_ms": 120,
    "require_release": True,
    "repeatable": False,
}

def _get_action_policy(action_name: str) -> dict:
    return _ACTION_POLICY.get(action_name, _DEFAULT_ACTION_POLICY)


class GestureIntentGate:
    """
    GestureIntentGate (also exposed as GestureHoldTimer for backwards compatibility).

    Tracks discrete gesture intent with:
      - Dropout grace (80-150ms) through transient Unknown / ambiguous raw frames
      - Immediate cancellation on explicit conflicting raw gesture
      - Intent release gating (requires neutral/release before re-triggering)
      - Action-specific hold policies from _ACTION_POLICY
    """
    def __init__(self, duration: float = 0.3, repeat_cooldown: float = 0.3, dropout_grace: float = 0.12):
        self.duration = duration
        self.repeat_cooldown = repeat_cooldown
        self.dropout_grace = dropout_grace
        self.target_gesture: str | None = None
        self.target_action: str | None = None
        self.start_time: float = 0.0
        self.last_confirmed: float = 0.0
        self.last_executed: float = 0.0
        self.executed_once: bool = False
        self.target_duration: float = duration

    def reset(self) -> None:
        self.target_gesture = None
        self.target_action = None
        self.start_time = 0.0
        self.last_confirmed = 0.0
        self.last_executed = 0.0
        self.executed_once = False
        self.target_duration = self.duration

    def cancel(self) -> None:
        self.reset()

    def get_progress(self, now: float | None = None) -> float:
        if (
            not self.target_gesture
            or self.target_gesture in ("None", "Unknown")
            or self.executed_once
            or self.start_time <= 0
        ):
            return 0.0
        if now is None:
            now = time.perf_counter()
        elapsed = now - self.start_time
        if self.target_duration <= 0:
            return 1.0
        return max(0.0, min(1.0, elapsed / self.target_duration))

    def check(
        self,
        gesture: str | None,
        is_repeatable: bool = False,
        duration: float | None = None,
        *,
        raw_gesture: str | None = None,
        action_name: str | None = None,
        now: float | None = None,
        dropout_grace: float | None = None,
    ) -> bool:
        if now is None:
            now = time.perf_counter()
        effective_dur = self.duration if duration is None else float(duration)
        effective_grace = self.dropout_grace if dropout_grace is None else float(dropout_grace)

        # 1. Explicit conflicting raw gesture cancellation (§18)
        if (
            self.target_gesture is not None
            and raw_gesture is not None
            and raw_gesture not in (None, "None", "Unknown", "")
            and raw_gesture != self.target_gesture
        ):
            self.reset()
            return False

        # 2. Gesture is None or Unknown (dropout or release)
        if not gesture or gesture in ("None", "Unknown"):
            if self.executed_once:
                # Action already consumed. It remains latched until raw gesture actually releases!
                if raw_gesture == self.target_gesture:
                    return False
                # User has physically released the gesture
                self.reset()
                return False

            if (
                self.target_gesture is not None
                and not self.executed_once
                and self.last_confirmed > 0
                and (now - self.last_confirmed) <= effective_grace
                and (raw_gesture in (None, "None", "Unknown", "") or raw_gesture == self.target_gesture)
            ):
                # Within dropout grace period: preserve intent hold
                return False
            # Beyond grace or genuine release
            self.target_gesture = None
            self.executed_once = False
            return False

        # 3. Gesture is a new named gesture
        if gesture != self.target_gesture:
            self.target_gesture = gesture
            self.target_action = action_name
            self.target_duration = effective_dur
            self.start_time = now
            self.last_confirmed = now
            self.last_executed = 0.0
            self.executed_once = False
            return False

        # 4. Same target gesture: check raw confirmation vs dropout
        if raw_gesture is not None:
            if raw_gesture == gesture:
                self.last_confirmed = now
            elif raw_gesture in (None, "None", "Unknown", ""):
                if self.last_confirmed > 0 and (now - self.last_confirmed) > effective_grace:
                    self.reset()
                    return False
        else:
            self.last_confirmed = now

        # 5. Release gating: non-repeatable action cannot fire again until released
        if not is_repeatable and self.executed_once:
            return False

        # 6. Check hold duration / repeat cooldown
        if not self.executed_once:
            if now - self.start_time >= self.target_duration:
                self.last_executed = now
                self.executed_once = True
                return True
        else:
            if now - self.last_executed >= self.repeat_cooldown:
                self.last_executed = now
                return True

        return False


# Backward compatibility alias
GestureHoldTimer = GestureIntentGate


class GestureMapper:
    def __init__(self, frame_w: int, frame_h: int):
        self.frame_w = frame_w
        self.frame_h = frame_h

        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self.media = MediaController()
        self.desktop = DesktopController()
        self.shortcut = ShortcutController()
        self.presentation = PresentationController()
        self.volume = VolumeController()
        self.brightness = BrightnessController()
        self.feedback = FeedbackController()
        self.canvas = DrawingCanvas(frame_w, frame_h)

        self.mode = "GENERAL"
        self.modes = ["GENERAL", "MEDIA", "DRAW"]
        self.timer = GestureHoldTimer(duration=0.4, repeat_cooldown=0.3)
        self.sleep_timer = GestureHoldTimer(duration=3.0, repeat_cooldown=3.0)
        self.last_pinch_time: float = 0.0
        self.last_brightness_y: float | None = None
        self.brightness_gesture_active: bool = False
        self.is_sleeping: bool = False
        self._mode_switch_gesture: str | None = None

        # Async worker for slow discrete actions (Stage 4).
        # Started here; stopped in cleanup(). Generation is bumped by cancel()
        # so queued actions are silently discarded after pause/mode-switch/shutdown.
        self._action_executor = ActionExecutor(on_result=self._on_async_action_result)
        self._action_executor.start()

        self.action_registry = {
            "open_vscode":      {"func": self.shortcut.open_vscode,      "repeatable": False},
            "open_chrome":      {"func": self.shortcut.open_chrome,      "repeatable": False},
            "open_calculator":  {"func": self.shortcut.open_calculator,  "repeatable": False},
            "open_explorer":    {"func": self.shortcut.open_explorer,    "repeatable": False},
            "open_notepad":     {"func": self.shortcut.open_notepad,     "repeatable": False},
            "lock_pc":          {"func": self.shortcut.lock_pc,          "repeatable": False},
            "screenshot":       {"func": self.desktop.take_screenshot,   "repeatable": False},
            "task_view":        {"func": self.desktop.task_view,         "repeatable": False},
            "show_desktop":     {"func": self.desktop.show_desktop,      "repeatable": False},
            "snap_left":        {"func": self.shortcut.snap_left,        "repeatable": False},
            "snap_right":       {"func": self.shortcut.snap_right,       "repeatable": False},
            "maximize":         {"func": self.shortcut.maximize,         "repeatable": False},
            "minimize":         {"func": self.shortcut.minimize,         "repeatable": False},
            "play_pause":       {"func": self.media.play_pause,          "repeatable": False},
            "next_track":       {"func": self.media.next_track,          "repeatable": False},
            "prev_track":       {"func": self.media.prev_track,          "repeatable": False},
            "mute":             {"func": self.media.mute,                "repeatable": False},
            "volume_up":        {"func": self.volume.volume_up,          "repeatable": True},
            "volume_down":      {"func": self.volume.volume_down,        "repeatable": True},
            "switch_mode":      {"func": self.cycle_mode,                "repeatable": False},
            "switch_to_draw":   {"func": lambda: self.set_mode("DRAW"), "repeatable": False},
            "undo":             {"func": self.canvas.undo,               "repeatable": True},
            "redo":             {"func": self.canvas.redo,               "repeatable": True},
            "save_drawing":     {"func": self.canvas.save_image,         "repeatable": False},
            "cycle_color":      {"func": self.canvas.cycle_color,        "repeatable": False},
            "toggle_eraser":    {"func": self.canvas.toggle_eraser,      "repeatable": False},
            "clear_canvas":     {"func": self.canvas.clear,             "repeatable": False},
            "toggle_sleep":     {"func": lambda: None,                   "repeatable": False},
        }

        from src.settings_manager import settings_manager
        settings_manager.register_callback(self.on_settings_changed)
        self.on_settings_changed()

    # ── Settings ───────────────────────────────────────────────────────────────

    def on_settings_changed(self) -> None:
        from config import SETTINGS
        hold_time_ms = SETTINGS.get("gestures", {}).get("hold_time_ms", 300)
        cooldown_ms  = SETTINGS.get("gestures", {}).get("cooldown_ms", 500)
        self.timer.duration = hold_time_ms / 1000.0
        self.timer.repeat_cooldown = cooldown_ms / 1000.0

    def get_hold_time(self, action_name: str) -> float:
        """Return the effective hold confirmation duration for an action."""
        if action_name in _ACTION_POLICY:
            return _ACTION_POLICY[action_name]["hold_ms"] / 1000.0
        return self.timer.duration

    # ── Temporal reset (§8) ────────────────────────────────────────────────────

    def reset_temporal_state(self) -> None:
        """
        Central reset — call on hand loss, camera loss, stale ML TTL,
        camera switch, pause, resume/re-arm, mode switch, detector restart,
        shutdown.
        """
        self.timer.reset()
        self.sleep_timer.reset()
        self.last_pinch_time = 0.0
        self.brightness_gesture_active = False
        self.last_brightness_y = None
        self._mode_switch_gesture = None
        self.canvas.end_stroke()
        if hasattr(self.mouse, "engine"):
            self.mouse.engine.reset()

    # ── Actions ────────────────────────────────────────────────────────────────

    def _on_async_action_result(self, name: str, result, elapsed: float) -> None:
        """Worker callback for slow actions — runs on the action-executor thread.

        Only log; do NOT touch Tk, the mouse, or any lock-protected state here.
        TTS feedback is intentionally deferred to the worker thread because it
        is itself slow (pyttsx3 calls COM) and must not block the inference path.
        """
        if result is None:
            return
        if hasattr(result, "success"):
            if result.success:
                self.feedback.speak(name.replace("_", " "))
                logger.info("Async action '%s' completed in %.0f ms.", name, elapsed * 1000)
            else:
                msg = getattr(result, "message", "") or ""
                err = getattr(result, "error", "") or ""
                logger.warning(
                    "Async action '%s' failed: %s%s", name, msg,
                    f" ({err})" if err else "",
                )
        else:
            self.feedback.speak(name.replace("_", " "))
            logger.info("Async action '%s' completed in %.0f ms.", name, elapsed * 1000)

    def execute_action(self, action_name: str) -> str | None:
        """
        Execute a registered action.  Feedback (TTS) fires only on success (§23).

        Slow discrete actions are routed through ActionExecutor (off-thread).
        Fast/continuous actions (cursor, scroll, draw, media keys) run inline.
        Returns a user-visible result string or None.
        """
        if action_name not in self.action_registry:
            return None

        # Safety: release mouse before a lock-screen action to avoid stuck button.
        if action_name == "lock_pc":
            self.mouse.release_all()

        if action_name in _ASYNC_ACTIONS:
            # Route slow actions off the inference thread.  The executor stamps
            # the current generation; a cancel() (pause/mode-switch/shutdown)
            # before the worker picks it up silently discards the job.
            func = self.action_registry[action_name]["func"]
            submitted = self._action_executor.submit(
                action_name, func,
                is_valid=lambda: not self._action_executor.stopping,
            )
            if submitted:
                logger.debug("Queued async action: %s", action_name)
                return f"Queued: {action_name}"
            logger.warning("Async action '%s' could not be queued (executor stopping).", action_name)
            return None

        # Inline path for fast/media/draw/volume actions.
        try:
            res = self.action_registry[action_name]["func"]()

            # ActionResult: check before speaking
            if hasattr(res, "success"):
                if res.success:
                    self.feedback.speak(action_name.replace("_", " "))
                    return f"Executed: {action_name}"
                else:
                    logger.warning(
                        f"Action '{action_name}' returned failure: {res.message}"
                        + (f" ({res.error})" if res.error else "")
                    )
                    return f"Failed: {action_name} — {res.message}" if res.message else f"Failed: {action_name}"
            else:
                # Legacy: callable returned None / no result object
                self.feedback.speak(action_name.replace("_", " "))
                return f"Executed: {action_name}"
        except Exception as e:
            logger.error(f"Action '{action_name}' raised exception: {e}")
            return f"Failed: {action_name}"

    # ── Mode ───────────────────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        if mode in self.modes:
            self.mouse.release_all()
            self.reset_temporal_state()
            # Cancel any queued slow action for the old mode so it cannot fire
            # after the mode has changed (e.g. a queued screenshot after switching
            # to DRAW).
            self._action_executor.cancel(f"mode switch to {mode}")
            self.mode = mode
            logger.info(f"Switched Mode: {self.mode}")

    def cycle_mode(self) -> None:
        idx = self.modes.index(self.mode)
        self.set_mode(self.modes[(idx + 1) % len(self.modes)])

    # ── Sleep gesture ──────────────────────────────────────────────────────────

    def get_sleep_gesture(self, mappings: dict) -> str | None:
        for g, action_name in mappings.items():
            if action_name == "toggle_sleep":
                return g
        return None

    # ── Canvas resize (§10) ────────────────────────────────────────────────────

    def update_frame_dimensions(self, new_w: int, new_h: int) -> None:
        """
        Called when actual camera frame dimensions differ from current mapper dims.
        Uses DrawingCanvas.resize() so NumPy data is correctly resized.
        Resets drawing smoothers and last_point to prevent coordinate mismatch.
        """
        if new_w == self.frame_w and new_h == self.frame_h:
            return
        logger.info(
            f"Mapper dims {self.frame_w}x{self.frame_h} -> {new_w}x{new_h}: resizing canvas."
        )
        result = self.canvas.resize(new_w, new_h)
        if not result.success:
            logger.error(f"Canvas resize failed: {result.message} — {result.error}")
            return
        self.frame_w = new_w
        self.frame_h = new_h

    # ── Main process loop ──────────────────────────────────────────────────────

    def process(
        self,
        hands_data: list,
        stable_gesture: str,
        raw_gesture: str,
        frame,
        *,
        render_canvas: bool = True,
        capture_at: float | None = None,
        confidence: float = 0.0,
    ) -> tuple:
        import cv2
        action = None
        progress = self.timer.get_progress()
        gesture = stable_gesture

        if not hands_data:
            self.reset_temporal_state()
            return frame, action, 0.0

        h1 = hands_data[0]["landmarks"]
        index_x, index_y = h1[8].pixel_x, h1[8].pixel_y

        mappings = SETTINGS.get("mappings", {}).get(self.mode, {})
        sleep_gesture = self.get_sleep_gesture(mappings)
        if raw_gesture != self._mode_switch_gesture:
            self._mode_switch_gesture = None
        mode_switch_held = self._mode_switch_gesture is not None
        target = self.timer.target_gesture
        known_stable = gesture not in (None, "None", "Unknown", "")
        raw_is_explicit = raw_gesture not in (None, "None", "Unknown", "")

        conflicting_raw = False
        if raw_is_explicit:
            if known_stable and raw_gesture != gesture:
                conflicting_raw = True
            elif not known_stable and target is not None and raw_gesture != target:
                conflicting_raw = True

        gesture_confirmed = known_stable and not mode_switch_held and not conflicting_raw


        # ── Sleep / wake ──────────────────────────────────────────────────────
        gesture = stable_gesture
        if sleep_gesture and gesture == sleep_gesture and gesture_confirmed:
            if self.sleep_timer.check(sleep_gesture):
                self.is_sleeping = not self.is_sleeping
                self.feedback.speak("Sleeping" if self.is_sleeping else "Waking up")
                self.mouse.release_all()
                return frame, ("System Sleeping" if self.is_sleeping else "System Woke Up"), 1.0
        else:
            if raw_gesture != self.sleep_timer.target_gesture or not self.sleep_timer.executed_once:
                self.sleep_timer.check(None)

        if self.is_sleeping:
            msg = (
                f"Zzz... (Hold {sleep_gesture} to Wake)"
                if sleep_gesture
                else "Zzz... (No Wake Gesture Mapped)"
            )
            cv2.putText(frame, msg, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            sleep_prog = (
                self.sleep_timer.get_progress()
                if (sleep_gesture and gesture == sleep_gesture)
                else 0.0
            )
            return frame, "Sleeping", sleep_prog

        mapped_action     = mappings.get(gesture)

        # ── Mode-specific continuous actions ──────────────────────────────────
        if self.mode == "GENERAL":
            self.mouse.process_landmarks(
                h1, stable_gesture, raw_gesture, self.frame_w, self.frame_h,
                capture_at=capture_at, confidence=confidence,
            )

            if gesture == "Middle Finger" and gesture_confirmed:
                result = self.brightness.set_brightness_from_y(h1[12].y)
                action = (
                    result.message if result.success or result.error is None
                    else f"Brightness unavailable: {result.message}"
                )

            if gesture != "Middle Finger":
                self.brightness_gesture_active = False

        elif self.mode == "DRAW":
            # Start from fresh geometry without waiting for the history mode;
            # stop as soon as Pointing releases or confidence is insufficient.
            draw_mode = raw_gesture == "Pointing" and gesture not in (None, "None", "Unknown")
            sx, sy = self.canvas.draw(index_x, index_y, draw_mode=draw_mode)

            if not draw_mode:
                cv2.circle(frame, (sx, sy), 8, self.canvas.color, 2)

            if render_canvas:
                frame = self.canvas.get_overlay(frame)

        # ── Discrete actions ──────────────────────────────────────────────────
        if not gesture_confirmed:
            if conflicting_raw:
                # Explicit conflicting gesture cancels immediately (§18)
                self.timer.reset()
                progress = 0.0
            else:
                # Confidence loss / dropout: check with timer for grace or latching
                self.timer.check(None, raw_gesture=raw_gesture)
                progress = self.timer.get_progress()
        elif mapped_action == "toggle_sleep":
            self.timer.reset()
            if self.sleep_timer.check(sleep_gesture, raw_gesture=raw_gesture):
                self.is_sleeping = not self.is_sleeping
                self.feedback.speak("Sleeping" if self.is_sleeping else "Waking up")
                self.mouse.release_all()
                return frame, ("System Sleeping" if self.is_sleeping else "System Woke Up"), 1.0
            progress = self.sleep_timer.get_progress()
        elif mapped_action:
            policy = _get_action_policy(mapped_action)
            action_info = self.action_registry.get(mapped_action, {})
            is_repeatable = policy.get("repeatable", action_info.get("repeatable", False))
            hold_dur = policy["hold_ms"] / 1000.0
            dropout_grace = policy["dropout_grace_ms"] / 1000.0

            if self.timer.check(
                gesture,
                raw_gesture=raw_gesture,
                is_repeatable=is_repeatable,
                duration=hold_dur,
                dropout_grace=dropout_grace,
                action_name=mapped_action,
            ):
                previous_mode = self.mode
                action = self.execute_action(mapped_action)
                if self.mode != previous_mode:
                    # set_mode resets every timer, but this held gesture has
                    # already switched modes and must release before rearming.
                    self._mode_switch_gesture = gesture
                if action:
                    return frame, action, 1.0
            progress = self.timer.get_progress()
        else:
            self.timer.reset()
            progress = 0.0

        return frame, action, progress

    # ── Shutdown ───────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        if hasattr(self, "mouse"):
            self.mouse.release_all()
        if hasattr(self, "_action_executor"):
            # stop() refuses new work, drains the queue and joins the worker.
            # This guarantees no slow action fires after shutdown.
            self._action_executor.stop(timeout=2.0)
        if hasattr(self, "feedback"):
            self.feedback.stop()
