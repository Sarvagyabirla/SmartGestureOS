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
        self._last_action_time = float("-inf")

    def _action(self, key: str, cooldown: float = 1.0) -> ActionResult:
        now = time.perf_counter()
        if now - self._last_action_time > cooldown:
            try:
                keyboard.send(key)
            except Exception as error:
                logger.error(f"Desktop shortcut '{key}' failed: {error}")
                return ActionResult(False, key, f"Could not send {key}", str(error), now)
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
        Attaches worker thread to active input desktop so background/executor threads
        do not fail with Windows ERROR_ACCESS_DENIED (5).
        """
        import ctypes
        from PIL import ImageGrab, Image
        from src.paths import SCREENSHOTS_DIR

        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ts_ms = int(time.perf_counter() * 1000)
        suffix = uuid.uuid4().hex[:6]
        filename = SCREENSHOTS_DIR / f"screen_{ts_ms}_{suffix}.png"

        try:
            # Attach current thread to Windows interactive input desktop
            try:
                u32 = ctypes.windll.user32
                hdesk = u32.OpenInputDesktop(0, False, 0x01FF)
                if hdesk:
                    u32.SetThreadDesktop(hdesk)
                    u32.CloseDesktop(hdesk)
            except Exception as desk_err:
                logger.debug(f"Input desktop attachment note: {desk_err}")

            # Capture all screens, falling back to primary screen
            img = None
            try:
                img = ImageGrab.grab(all_screens=True)
            except Exception:
                img = ImageGrab.grab()

            if img is None:
                raise RuntimeError("Screen grab returned None")

            img.save(str(filename))

            if os.path.exists(str(filename)) and os.path.getsize(str(filename)) > 0:
                logger.info(f"Screenshot successfully saved: {filename.name} ({filename.stat().st_size} bytes)")
                return ActionResult(
                    True, "screenshot",
                    f"Saved {filename.name}",
                    None,
                    time.perf_counter(),
                )
            return ActionResult(
                False, "screenshot",
                "Screenshot saved but file not found or empty",
                "File not found or 0 bytes after save",
                time.perf_counter(),
            )
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ActionResult(
                False, "screenshot",
                f"Screenshot failed: {e}",
                str(e),
                time.perf_counter(),
            )
