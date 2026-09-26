import keyboard
import time

from .logger import logger
from .models import ActionResult


class PresentationController:
    def __init__(self):
        self.last_action_time = float("-inf")

    def _action(self, key: str, cooldown: float = 1.5) -> ActionResult:
        now = time.perf_counter()
        if now - self.last_action_time > cooldown:
            try:
                keyboard.send(key)
            except Exception as error:
                logger.error(f"Presentation shortcut '{key}' failed: {error}")
                return ActionResult(False, key, f"Could not send {key}", str(error), now)
            self.last_action_time = now
            return ActionResult(True, key, f"Sent {key}", None, now)
        return ActionResult(False, key, "Cooldown active", None, now)

    def next_slide(self) -> ActionResult:
        return self._action("right")

    def prev_slide(self) -> ActionResult:
        return self._action("left")
