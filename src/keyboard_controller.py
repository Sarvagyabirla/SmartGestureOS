from .virtual_keyboard import VirtualKeyboard
from .logger import logger

class KeyboardController:
    def __init__(self):
        self.keyboard = VirtualKeyboard()
        self.last_gesture = None
        
    def process_gesture(self, gesture):
        if gesture == self.last_gesture:
            return
            
        try:
            if gesture == "Pinch":
                self.keyboard.press_key("enter")
                logger.info("Keyboard: Pressed Enter")
            elif gesture == "Peace":
                self.keyboard.hotkey("ctrl", "c")
                logger.info("Keyboard: Copied")
            elif gesture == "Three Fingers":
                self.keyboard.hotkey("ctrl", "v")
                logger.info("Keyboard: Pasted")
            elif gesture == "Open Palm":
                self.keyboard.press_key("space")
                logger.info("Keyboard: Pressed Space")
        except Exception as e:
            logger.error(f"KeyboardController error: {e}")
            
        self.last_gesture = gesture
