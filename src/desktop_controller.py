"""
DesktopController — Windows desktop keyboard shortcuts and screenshot capture.

F-11 FIX: Screenshot filenames use millisecond timestamp + UUID suffix
to prevent collision when two screenshots are taken in the same second.
"""

import keyboard
import time
import uuid
import os
from src.models import ActionResult
from .logger import logger


class DesktopController:
    def __init__(self):
        self._last_action_time = 0.0

    def _action(self, key: str, cooldown: float = 1.0) -> ActionResult:
        now = time.perf_counter()
        if now - self._last_action_time > cooldown:
            keyboard.send(key)
            self._last_action_time = now
            return ActionResult(True, key, f"Sent {key}", None, now)
        return ActionResult(False, key, "Cooldown active", None, now)

    def show_desktop(self) -> ActionResult:
        return self._action("windows+d")

    def task_view(self) -> ActionResult:
        return self._action("windows+tab")

    def switch_window(self) -> ActionResult:
        return self._action("alt+tab")

    def open_start(self) -> ActionResult:
        return self._action("windows")

    def take_screenshot(self) -> ActionResult:
        """
        Capture and save a screenshot.
        F-11 FIX: filename uses ms precision + UUID suffix to prevent collisions.
        """
        from src.paths import SCREENSHOTS_DIR
        from PIL import ImageGrab

        ts_ms = int(time.perf_counter() * 1000)
        suffix = uuid.uuid4().hex[:6]
        filename = SCREENSHOTS_DIR / f"screen_{ts_ms}_{suffix}.png"

        try:
            img = ImageGrab.grab(all_screens=True)
            img.save(str(filename))
            if os.path.exists(str(filename)):
                return ActionResult(
                    True, "screenshot",
                    f"Saved {filename.name}",
                    None,
                    time.perf_counter(),
                )
            return ActionResult(
                False, "screenshot",
                "Screenshot saved but file not found",
                "File not found after save",
                time.perf_counter(),
            )
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ActionResult(
                False, "screenshot",
                "Screenshot failed",
                str(e),
                time.perf_counter(),
            )
