"""
DesktopController — Windows desktop keyboard shortcuts and screenshot capture.

F-11 FIX: Screenshot filenames use millisecond timestamp + UUID suffix
to prevent collision when two screenshots are taken in the same second.
"""

import keyboard
import time
import uuid
import os
import threading
from src.models import ActionResult
from src.paths import SCREENSHOTS_DIR
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
            # Attempt 1: Direct grab (fast path; also handles patched mocks in unit tests)
            img = None
            try:
                img = ImageGrab.grab(all_screens=True)
            except Exception:
                try:
                    img = ImageGrab.grab()
                except Exception:
                    img = None

            # Attempt 2: Isolated thread with interactive desktop attachment
            # Necessary when caller thread has windows/hooks (Win32 ERROR_BUSY 170)
            # or runs in an unattached desktop context (Win32 ERROR_ACCESS_DENIED 5).
            if img is None:
                box = [None, None]
                def _isolated_grab():
                    try:
                        u32 = ctypes.windll.user32
                        hdesk = u32.OpenInputDesktop(0, False, 0x01FF)
                        if hdesk:
                            u32.SetThreadDesktop(hdesk)
                            u32.CloseDesktop(hdesk)
                    except Exception as desk_err:
                        logger.debug(f"Input desktop attachment note: {desk_err}")
                    try:
                        box[0] = ImageGrab.grab(all_screens=True)
                    except Exception:
                        try:
                            box[0] = ImageGrab.grab()
                        except Exception as grab_err:
                            box[1] = grab_err

                worker = threading.Thread(target=_isolated_grab, name="screenshot-grabber")
                worker.start()
                worker.join(timeout=3.0)
                if box[0] is not None:
                    img = box[0]
                elif box[1] is not None:
                    raise box[1]
                else:
                    raise RuntimeError("Screen grab timed out")

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
