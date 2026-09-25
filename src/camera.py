"""
Camera — threaded camera capture with automatic reconnect.

States:
    running=False, is_connected=False  →  stopped
    running=True,  is_connected=False  →  trying to connect / reconnecting
    running=True,  is_connected=True   →  active

Camera.start() always returns immediately. The capture thread handles
retry internally so the application pipeline can start regardless of
whether the physical camera is present at startup.

Camera.stop() is idempotent — safe to call multiple times.
"""

import cv2
import threading
import queue
import time
import numpy as np
from .logger import logger


class Camera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720, fps: int = 30):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps

        self.cap = None
        self.running = False
        self._thread: threading.Thread | None = None
        self.is_connected = False

        self.frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self.frame_id: int = 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _open_capture(self) -> bool:
        """Open (or reopen) the VideoCapture. Returns True if opened."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        try:
            cap = cv2.VideoCapture(self.index)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            if cap.isOpened():
                self.cap = cap
                return True
            cap.release()
            return False
        except Exception as e:
            logger.error(f"Camera._open_capture exception: {e}")
            return False

    def _update(self) -> None:
        """Background capture thread — handles retry on failure."""
        failed_reads = 0

        while self.running:
            # ── No cap / cap closed → retry ───────────────────────────────
            if self.cap is None or not self.cap.isOpened():
                self.is_connected = False
                if not self._open_capture():
                    logger.warning(f"Camera {self.index}: not available, retrying in 1 s…")
                    time.sleep(1.0)
                    continue
                logger.info(f"Camera {self.index}: opened successfully.")

            # ── Read frame ────────────────────────────────────────────────
            try:
                ret, frame = self.cap.read()
            except Exception as e:
                logger.error(f"Camera read exception: {e}")
                ret, frame = False, None

            if not ret or not isinstance(frame, np.ndarray):
                self.is_connected = False
                failed_reads += 1
                if failed_reads > 30:
                    logger.error("Camera: too many failed reads — releasing and retrying.")
                    if self.cap:
                        self.cap.release()
                        self.cap = None
                    failed_reads = 0
                    time.sleep(1.0)
                continue

            # ── Good frame ────────────────────────────────────────────────
            self.is_connected = True
            failed_reads = 0
            frame = cv2.flip(frame, 1)  # Mirror for intuitive control

            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass

            self.frame_queue.put((frame, self.frame_id))
            self.frame_id += 1

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """
        Start the camera capture thread.
        If already running, returns True immediately (idempotent).
        Returns True if the camera was immediately opened, False if it will
        be retried in the background thread.
        """
        if self.running:
            return self.is_connected

        self.running = True
        initial_ok = self._open_capture()
        if not initial_ok:
            logger.warning(
                f"Camera {self.index}: initial open failed — capture thread will retry."
            )

        self._thread = threading.Thread(target=self._update, daemon=True, name="camera-capture")
        self._thread.start()
        logger.info(f"Camera {self.index}: capture thread started (initial_ok={initial_ok}).")
        return initial_ok

    def read(self) -> tuple:
        """Non-blocking read. Returns (frame, frame_id) or (None, -1)."""
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None, -1

    def stop(self) -> None:
        """Stop capture thread and release resources. Idempotent."""
        if not self.running:
            return
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_connected = False
        logger.info(f"Camera {self.index}: stopped.")
