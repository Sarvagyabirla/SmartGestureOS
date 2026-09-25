"""
MediaController — media key dispatch.

Every public method returns ActionResult so GestureMapper can
give accurate success/failure feedback and avoid speaking before
knowing whether the action worked.

Cooldown uses time.perf_counter() for monotonic rate-limiting.
"""
import time
import keyboard
from .models import ActionResult
from .logger import logger


class MediaController:
    def __init__(self):
        # perf_counter for monotonic rate-limiting (§24 fix)
        self._last_action_time: float = 0.0
        self._cooldown: float = 1.0  # seconds between media key sends

    def _action(self, key: str, cooldown: float = 1.0) -> ActionResult:
        now = time.perf_counter()
        if now - self._last_action_time < cooldown:
            return ActionResult(False, key, "Cooldown active", None, now)
        try:
            keyboard.send(key)
            self._last_action_time = now
            return ActionResult(True, key, f"Sent media key: {key}", None, now)
        except Exception as e:
            logger.error(f"MediaController: keyboard.send('{key}') failed: {e}")
            return ActionResult(False, key, "keyboard.send failed", str(e), now)

    # ── Public API ─────────────────────────────────────────────────────────────

    def play_pause(self) -> ActionResult:
        return self._action("play/pause media")

    def next_track(self) -> ActionResult:
        return self._action("next track")

    def prev_track(self) -> ActionResult:
        return self._action("previous track")

    def mute(self) -> ActionResult:
        return self._action("volume mute")
