import keyboard
import time
from src.models import ActionResult

class DesktopController:
    def __init__(self):
        self.last_action_time = 0.0
        
    def _action(self, key, cooldown=1.0) -> ActionResult:
        now = time.perf_counter()
        if now - self.last_action_time > cooldown:
            keyboard.send(key)
            self.last_action_time = now
            return ActionResult(True, key, f"Sent {key}", None, time.time())
        return ActionResult(False, key, "Cooldown active", None, time.time())
            
    def show_desktop(self) -> ActionResult:
        return self._action("windows+d")
        
    def task_view(self) -> ActionResult:
        return self._action("windows+tab")
        
    def switch_window(self) -> ActionResult:
        return self._action("alt+tab")
        
    def open_start(self) -> ActionResult:
        return self._action("windows")
        
    def take_screenshot(self) -> ActionResult:
        from src.paths import SCREENSHOTS_DIR
        from PIL import ImageGrab
        import os
        
        filename = SCREENSHOTS_DIR / f"screen_{int(time.time())}.png"
        try:
            img = ImageGrab.grab(all_screens=True)
            img.save(str(filename))
            if os.path.exists(str(filename)):
                return ActionResult(True, "screenshot", f"Saved {filename.name}", None, time.time())
            else:
                return ActionResult(False, "screenshot", "Failed to verify file", "File not found after save", time.time())
        except Exception as e:
            from .logger import logger
            logger.error(f"Screenshot failed: {e}")
            return ActionResult(False, "screenshot", "Screenshot failed", str(e), time.time())
