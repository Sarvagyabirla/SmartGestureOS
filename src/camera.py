import cv2
import threading
import queue
from .logger import logger

class Camera:
    def __init__(self, index=0, width=1280, height=720, fps=30):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        
        self.cap = None
        self.running = False
        self.thread = None
        self.is_connected = False
        
        self.frame_queue = queue.Queue(maxsize=1)
        self.frame_id = 0
        
    def _open_capture(self):
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(self.index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        return self.cap.isOpened()
        
    def start(self):
        if self.running:
            return True
            
        ret = True
        if not self._open_capture():
            logger.error(f"Failed to open camera index {self.index}")
            ret = False
            
        # Always start thread, so it can retry connection
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        logger.info("Camera started (or attempting to start).")
        return ret
            
        if not self._open_capture():
            logger.error(f"Failed to open camera index {self.index}")
            
        # Always start thread, so it can retry connection
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        logger.info("Camera started (or attempting to start).")
        return True
        
    def _update(self):
        import time
        import numpy as np
        failed_reads = 0
        while self.running:
            if not self.cap.isOpened():
                self.is_connected = False
                time.sleep(1)
                self._open_capture()
                continue

            ret, frame = self.cap.read()
            if not ret or not isinstance(frame, np.ndarray):
                self.is_connected = False
                failed_reads += 1
                logger.warning(f"Failed to grab frame (count: {failed_reads})")
                if failed_reads > 30:
                    logger.error("Camera connection lost. Attempting recovery...")
                    self.cap.release()
                    time.sleep(1)
                    failed_reads = 0
                continue
                
            self.is_connected = True
            failed_reads = 0
            frame = cv2.flip(frame, 1) # Mirror image for intuitive control
            
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass
                    
            self.frame_queue.put((frame, self.frame_id))
            self.frame_id += 1
                
    def read(self):
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None, -1
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
        logger.info("Camera stopped.")
