import pyttsx3
import threading
import queue
import time
from .logger import logger

class FeedbackController:
    """Asynchronous TTS with bounded queue, duplicate suppression, and backlog protection."""
    
    MAX_QUEUE_SIZE = 3
    MIN_REPEAT_INTERVAL = 1.5  # seconds before same phrase can repeat

    def __init__(self):
        self._queue = queue.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._last_spoken: str = ""
        self._last_spoken_time: float = 0.0
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._thread.start()

    def _tts_worker(self):
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
        except Exception as e:
            logger.error(f"Failed to init pyttsx3: {e}")
            # Drain the queue so stop() can join
            while True:
                try:
                    item = self._queue.get(timeout=1.0)
                    if item is None:
                        break
                    self._queue.task_done()
                except queue.Empty:
                    continue
            return

        while True:
            try:
                text = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if text is None:
                self._queue.task_done()
                break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                logger.error(f"TTS error: {e}")
            self._queue.task_done()

    def speak(self, text: str):
        """Enqueue speech with duplicate suppression and queue bounds."""
        if not text:
            return

        now = time.monotonic()
        with self._lock:
            is_duplicate = (
                text == self._last_spoken and
                (now - self._last_spoken_time) < self.MIN_REPEAT_INTERVAL
            )
            if is_duplicate:
                return
            self._last_spoken = text
            self._last_spoken_time = now

        try:
            self._queue.put_nowait(text)
        except queue.Full:
            # Queue is full — drop this low-priority speech item
            logger.debug(f"TTS queue full, dropping: {text!r}")

    def stop(self):
        """Signal worker to exit and wait briefly for clean shutdown."""
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            # Force the sentinel in by draining one item
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
        self._thread.join(timeout=2.0)
