import keyboard
import time

class PresentationController:
    def __init__(self):
        self.last_action_time = 0
        
    def _action(self, key, cooldown=1.5) -> "ActionResult":
        from src.models import ActionResult
        if time.time() - self.last_action_time > cooldown:
            keyboard.send(key)
            self.last_action_time = time.time()
            return ActionResult(True, key, f"Sent {key}", None, time.perf_counter())
        return ActionResult(False, key, "Cooldown", None, time.perf_counter())
            
    def next_slide(self):
        self._action("right")
        
    def prev_slide(self):
        self._action("left")
