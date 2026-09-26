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

    def _release_capture(self) -> None:
        """Discard the handle even when a failing driver raises on release."""
        cap = self.cap
        self.cap = None
        if cap is not None:
            try:
                cap.release()
            except Exception as e:
                logger.warning(f"Camera {self.index}: release failed: {e}")

    def _open_capture(self) -> bool:
        """Open (or reopen) the VideoCapture. Returns True if opened."""
        self._release_capture()
        cap = None
        try:
            cap = cv2.VideoCapture(self.index)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            if cap.isOpened():
                self.cap = cap
                return True
        except Exception as e:
            logger.error(f"Camera._open_capture exception: {e}")
        if cap is not None:
            try:
                cap.release()
            except Exception as e:
                logger.warning(f"Camera {self.index}: failed open cleanup: {e}")
        return False

    def _update(self) -> None:
        """Background capture thread — handles retry on failure."""
        failed_reads = 0

        while self.running:
            # ── No cap / cap closed → retry ───────────────────────────────
            try:
                capture_open = self.cap is not None and self.cap.isOpened()
            except Exception as e:
                logger.warning(f"Camera {self.index}: open-state check failed: {e}")
                capture_open = False
            if not capture_open:
                self.is_connected = False
                if not self._open_capture():
                    logger.warning(f"Camera {self.index}: not available, retrying in 1 s…")
                    time.sleep(1.0)
                    continue
                logger.info(f"Camera {self.index}: opened successfully.")

            # ── Read frame ────────────────────────────────────────────────
            failure_reason = None
            try:
                ret, frame = self.cap.read()
            except Exception as e:
                ret, frame = False, None
                failure_reason = f"read exception: {e}"

            if ret and isinstance(frame, np.ndarray):
                if frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0 or frame.dtype != np.uint8:
                    failure_reason = f"invalid frame shape/type: {frame.shape}, {frame.dtype}"
                else:
                    try:
                        frame = cv2.flip(frame, 1)  # Mirror for intuitive control
                        if not isinstance(frame, np.ndarray) or frame.size == 0:
                            failure_reason = "mirror returned no frame"
                    except Exception as e:
                        failure_reason = f"mirror failed: {e}"
            elif failure_reason is None:
                failure_reason = "read returned no frame"

            if failure_reason is not None:
                self.is_connected = False
                failed_reads += 1
                if failed_reads == 1:
                    logger.warning(f"Camera {self.index}: {failure_reason}")
                if failed_reads > 30:
                    logger.error("Camera: too many failed reads — releasing and retrying.")
                    self._release_capture()
                    failed_reads = 0
                    time.sleep(1.0)
                continue

            # ── Good frame ────────────────────────────────────────────────
            self.is_connected = True
            failed_reads = 0

            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass

            captured_at = time.perf_counter()
            self.frame_queue.put((frame, self.frame_id, captured_at))
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
        frame, frame_id, _ = self.read_with_timestamp()
        return frame, frame_id

    def read_with_timestamp(self) -> tuple:
        """Return the newest frame, id, and monotonic capture time."""
        try:
            item = self.frame_queue.get_nowait()
        except queue.Empty:
            return None, -1, None

        # Accept legacy two-item entries from tests or downstream integrations.
        if len(item) == 2:
            frame, frame_id = item
            return frame, frame_id, time.perf_counter()
        return item

    def stop(self) -> None:
        """Stop capture thread and release resources. Idempotent."""
        if not self.running:
            return
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._release_capture()
        self.is_connected = False
        logger.info(f"Camera {self.index}: stopped.")
