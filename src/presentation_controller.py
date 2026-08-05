import keyboard
import time

class PresentationController:
    def __init__(self):
        self.last_action_time = 0
        
    def _action(self, key, cooldown=1.5):
        if time.time() - self.last_action_time > cooldown:
            keyboard.send(key)
            self.last_action_time = time.time()
            
    def next_slide(self):
        self._action("right")
        
    def prev_slide(self):
        self._action("left")
