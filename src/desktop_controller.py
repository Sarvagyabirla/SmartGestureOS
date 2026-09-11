import keyboard
import time

class DesktopController:
    def __init__(self):
        self.last_action_time = 0
        
    def _action(self, key, cooldown=1.0):
        if time.time() - self.last_action_time > cooldown:
            keyboard.send(key)
            self.last_action_time = time.time()
            
    def show_desktop(self):
        self._action("windows+d")
        
    def task_view(self):
        self._action("windows+tab")
        
    def switch_window(self):
        self._action("alt+tab")
        
    def open_start(self):
        self._action("windows")
        
    def take_screenshot(self):
        import os
        from PIL import ImageGrab
        
        if not os.path.exists("screenshots"):
            os.makedirs("screenshots")
            
        filename = f"screenshots/screen_{int(time.time())}.png"
        try:
            img = ImageGrab.grab(all_screens=True)
            img.save(filename)
        except Exception as e:
            from .logger import logger
            logger.error(f"Screenshot failed: {e}")
