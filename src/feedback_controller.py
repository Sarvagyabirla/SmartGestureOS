import pyttsx3
import threading
from .logger import logger

class FeedbackController:
    def __init__(self):
        self.engine = None
        self._init_engine()
        self.thread_lock = threading.Lock()
        
    def _init_engine(self):
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 170)
        except Exception as e:
            logger.error(f"Failed to init pyttsx3: {e}")
            self.engine = None

    def _speak_thread(self, text):
        with self.thread_lock:
            try:
                # Need to re-init for macOS/Linux sometimes, but Windows SAPI5 handles it mostly fine
                # However, pyttsx3 is strictly single-threaded event loop. We can run it in a thread if instantiated there.
                engine = pyttsx3.init()
                engine.setProperty('rate', 170)
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                logger.error(f"TTS error: {e}")

    def speak(self, text):
        if not self.engine:
            return
        # Run in a daemon thread so it doesn't block the gesture loop
        threading.Thread(target=self._speak_thread, args=(text,), daemon=True).start()
