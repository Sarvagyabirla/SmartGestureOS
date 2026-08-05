import keyboard
import time

class VirtualKeyboard:
    def __init__(self):
        self.last_key_time = 0
        
    def type_string(self, text):
        keyboard.write(text, delay=0.05)
        
    def press_key(self, key):
        current_time = time.time()
        if current_time - self.last_key_time > 0.3:
            keyboard.send(key)
            self.last_key_time = current_time
            
    def hotkey(self, *keys):
        current_time = time.time()
        if current_time - self.last_key_time > 0.5:
            keyboard.send('+'.join(keys))
            self.last_key_time = current_time
