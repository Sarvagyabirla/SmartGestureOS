import cv2
import threading
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
        
        self.frame = None
        self.frame_id = 0
        self.lock = threading.Lock()
        
    def start(self):
        if self.running:
            return True
            
        self.cap = cv2.VideoCapture(self.index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        
        if not self.cap.isOpened():
            logger.error(f"Failed to open camera index {self.index}")
            return False
            
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        logger.info("Camera started successfully.")
        return True
        
    def _update(self):
        import time
        failed_reads = 0
        while self.running:
            if not self.cap.isOpened():
                time.sleep(1)
                self.cap = cv2.VideoCapture(self.index)
                continue
                
            ret, frame = self.cap.read()
            if not ret:
                failed_reads += 1
                logger.warning(f"Failed to grab frame (count: {failed_reads})")
                if failed_reads > 30:
                    logger.error("Camera connection lost. Attempting recovery...")
                    self.cap.release()
                    time.sleep(1)
                    failed_reads = 0
                continue
                
            failed_reads = 0
            frame = cv2.flip(frame, 1) # Mirror image for intuitive control
            
            with self.lock:
                self.frame = frame
                self.frame_id += 1
                
    def read(self):
        with self.lock:
            if self.frame is not None:
                return self.frame.copy(), self.frame_id
        return None, 0
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
        logger.info("Camera stopped.")
