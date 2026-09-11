import pyttsx3
import threading
import queue
from .logger import logger

class FeedbackController:
    def __init__(self):
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.thread.start()
        
    def _tts_worker(self):
        try:
            # Initialize SAPI5 engine once in the dedicated thread
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
        except Exception as e:
            logger.error(f"Failed to init pyttsx3: {e}")
            return
            
        while True:
            text = self.queue.get()
            if text is None:
                break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                logger.error(f"TTS error: {e}")
            self.queue.task_done()

    def speak(self, text):
        self.queue.put(text)
        
    def stop(self):
        self.queue.put(None)
        self.thread.join(timeout=1.0)
