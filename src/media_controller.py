import keyboard
import time

class MediaController:
    def __init__(self):
        self.last_action_time = 0
        
    def _action(self, key, cooldown=1.0) -> "ActionResult":
        from src.models import ActionResult
        if time.time() - self.last_action_time > cooldown:
            keyboard.send(key)
            self.last_action_time = time.time()
            return ActionResult(True, key, f"Sent media {key}", None, time.perf_counter())
        return ActionResult(False, key, "Cooldown", None, time.perf_counter())
            
    def play_pause(self):
        self._action("play/pause media")
        
    def next_track(self):
        self._action("next track")
        
    def prev_track(self):
        self._action("previous track")
        
    def mute(self):
        self._action("volume mute")
