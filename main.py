import time
import cv2
import math
import threading
import queue
import psutil
import os
import collections
from config import SETTINGS
from src.camera import Camera
from src.gesture_detector import GestureDetector
from src.gesture_classifier import GestureClassifier
from src.gesture_mapper import GestureMapper
from src.ui import SmartGestureApp
from src.logger import logger


class MainApp:
    def __init__(self):
        self.camera = Camera(
            index=SETTINGS["camera"]["index"],
            width=SETTINGS["camera"]["width"],
            height=SETTINGS["camera"]["height"],
            fps=SETTINGS["camera"]["fps"]
        )

        self.detector = GestureDetector()
        self.classifier = GestureClassifier()

        # Use SETTINGS dims as initial hint; actual dims propagated from first frame
        self.mapper = GestureMapper(
            SETTINGS["camera"]["width"],
            SETTINGS["camera"]["height"]
        )

        self.fps_history = collections.deque(maxlen=30)

        self.ui = SmartGestureApp(close_callback=self.stop_system)

        self.running = False
        self.frame_queue = queue.Queue(maxsize=1)
        self.process_thread = None
        self.stats_thread = None

        self.cpu_usage = 0.0
        self.ram_usage = 0.0

        # Track camera connected state to detect transitions
        self._was_camera_connected = False

        self.automation_enabled = True
        try:
            import keyboard
            keyboard.add_hotkey('ctrl+alt+g', self.toggle_automation)
        except Exception as e:
            logger.error(f"Failed to bind hotkey: {e}")

        self.start_system()

    def toggle_automation(self):
        self.automation_enabled = not self.automation_enabled
        if not self.automation_enabled:
            if hasattr(self, 'mapper'):
                self.mapper.mouse.release_all()
                if hasattr(self.mapper.mouse, 'engine'):
                    self.mapper.mouse.engine.on_hand_lost()
                if hasattr(self.mapper.timer, 'reset'):
                    self.mapper.timer.reset()
                if hasattr(self.mapper.sleep_timer, 'reset'):
                    self.mapper.sleep_timer.reset()
            if hasattr(self, 'classifier') and hasattr(self.classifier, 'reset'):
                self.classifier.reset()
            logger.info("Automation Paused")
        else:
            logger.info("Automation Resumed")

    def start_system(self):
        if self.camera.start():
            self.running = True
            self.process_thread = threading.Thread(
                target=self.processing_loop, daemon=True
            )
            self.process_thread.start()

            self.stats_thread = threading.Thread(
                target=self.monitoring_loop, daemon=True
            )
            self.stats_thread.start()

            self.update_ui_loop()
            return True
        else:
            # Show camera-unavailable state in UI
            logger.error("No camera available at startup.")
            self.update_ui_loop()  # Still start UI loop so "no camera" shows
            return False

    def monitoring_loop(self):
        try:
            process = psutil.Process(os.getpid())
            process.cpu_percent()  # initial call (discard)
        except psutil.NoSuchProcess:
            return

        while self.running:
            try:
                # Sleep in small increments so thread exits quickly on stop
                for _ in range(10):
                    if not self.running:
                        break
                    time.sleep(0.1)

                if not self.running:
                    break

                total_cpu = process.cpu_percent()
                total_ram = process.memory_info().rss

                for child in process.children(recursive=True):
                    try:
                        total_cpu += child.cpu_percent()
                        total_ram += child.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass

                self.cpu_usage = total_cpu
                self.ram_usage = total_ram / (1024 * 1024)  # MB
            except Exception:
                logger.exception("Stats monitoring error:")
                time.sleep(1)

    def stop_system(self):
        self.running = False

        # Unblock queues to prevent thread deadlock
        try:
            while not self.frame_queue.empty():
                self.frame_queue.get_nowait()
        except queue.Empty:
            pass

        # Safety: release all desktop automation before shutdown
        if hasattr(self, "mapper"):
            self.mapper.cleanup()

        self.camera.stop()

        if hasattr(self, "detector"):
            self.detector.close()

        if self.process_thread:
            self.process_thread.join(timeout=2.0)
        if self.stats_thread:
            self.stats_thread.join(timeout=1.0)

    def draw_overlays(self, frame, hands_data, progress):
        if not hands_data:
            return frame

        h1 = hands_data[0]["landmarks"]
        index_x, index_y = h1[8].pixel_x, h1[8].pixel_y

        # Virtual cursor indicator
        cv2.circle(frame, (index_x, index_y), 12, (255, 255, 50), 2)
        cv2.circle(frame, (index_x, index_y), 3, (255, 255, 50), -1)

        # Gesture-hold loading ring
        if progress > 0.0:
            center = (index_x, index_y)
            radius = 25
            angle = int(360 * progress)
            cv2.ellipse(
                frame, center, (radius, radius), -90, 0, angle, (0, 255, 0), 4
            )

        return frame

    def processing_loop(self):
        last_frame_id = -1
        last_inference_time = 0.0
        last_timestamp_ms = -1
        inference_interval = 1.0 / 30.0

        # Telemetry
        self.fps_history = collections.deque(maxlen=30)
        self.latency_history = collections.deque(maxlen=30)

        # Latest ML result state
        latest_hands_data = None
        latest_stable_gesture = "Unknown"
        latest_raw_gesture = "Unknown"
        latest_confidence = 0
        latest_action = None
        latest_progress = 0.0

        last_result_receive_time = time.perf_counter()

        while self.running:
            loop_start = time.perf_counter()
            try:
                frame, frame_id = self.camera.read()
                is_connected = self.camera.is_connected

                # ----------------------------------------------------------------
                # Camera disconnect branch
                # F-04 FIX: When camera transitions connected→disconnected, release
                # all desktop automation state (drag, click, scroll, etc.)
                # ----------------------------------------------------------------
                if not is_connected:
                    if self._was_camera_connected:
                        # Transition: was connected, now disconnected
                        logger.warning("Camera disconnected — releasing all automation state.")
                        self.mapper.mouse.release_all()
                        # Also reset classifier temporal state so stale gestures don't persist
                        self.classifier.classify([])
                        latest_hands_data = None
                        latest_stable_gesture = "Unknown"
                        latest_raw_gesture = "Unknown"
                        latest_confidence = 0
                        latest_action = None
                        latest_progress = 0.0
                    self._was_camera_connected = False

                    import numpy as np
                    err_frame = np.zeros(
                        (self.camera.height, self.camera.width, 3), dtype=np.uint8
                    )
                    cv2.putText(
                        err_frame,
                        "CAMERA DISCONNECTED - RECOVERING...",
                        (50, self.camera.height // 2),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        (0, 0, 255),
                        2,
                    )
                    try:
                        if self.frame_queue.full():
                            self.frame_queue.get_nowait()
                        mode = self.mapper.mode if hasattr(self, "mapper") else "GENERAL"
                        sleeping = self.mapper.is_sleeping if hasattr(self, "mapper") else False
                        self.frame_queue.put_nowait((
                            err_frame, [], mode, "Unknown", "Unknown", 0,
                            None, 0, self.cpu_usage, self.ram_usage, False, sleeping, 0, self.automation_enabled
                        ))
                    except (queue.Empty, queue.Full):
                        pass
                    time.sleep(0.1)
                    continue

                # Camera is connected
                self._was_camera_connected = True

                if frame is not None and frame_id != last_frame_id:
                    last_frame_id = frame_id
                    current_time = time.perf_counter()

                    # F-08/F-17 FIX: Use actual frame dimensions for mapper
                    actual_h, actual_w = frame.shape[:2]
                    if self.mapper.frame_w != actual_w or self.mapper.frame_h != actual_h:
                        logger.info(
                            f"Updating mapper dims from {self.mapper.frame_w}x{self.mapper.frame_h}"
                            f" → {actual_w}x{actual_h}"
                        )
                        self.mapper.frame_w = actual_w
                        self.mapper.frame_h = actual_h
                        self.mapper.canvas.width = actual_w
                        self.mapper.canvas.height = actual_h

                    inference_interval = (
                        1.0 / 5.0 if self.mapper.is_sleeping else 1.0 / 30.0
                    )

                    # 1. Send frame to async ML pipeline
                    if current_time - last_inference_time >= inference_interval:
                        timestamp_ms = int(current_time * 1000)
                        if timestamp_ms <= last_timestamp_ms:
                            timestamp_ms = last_timestamp_ms + 1
                        last_timestamp_ms = timestamp_ms

                        # Downscale for ML performance
                        small_frame = cv2.resize(frame, (640, 360))
                        self.detector.detect_async(small_frame, timestamp_ms)
                        last_inference_time = current_time

                    # 2. Consume latest ML result (drain to newest)
                    result_ts, results = None, None
                    while not self.detector.results_queue.empty():
                        result_ts, results = self.detector.results_queue.get_nowait()

                    if result_ts is not None:
                        last_result_receive_time = current_time
                        latency_ms = int(time.perf_counter() * 1000) - result_ts
                        self.latency_history.append(latency_ms)

                        # Landmarks computed from actual frame shape
                        latest_hands_data = self.detector.get_all_hands_data(
                            results, frame.shape
                        )

                        result_obj = self.classifier.classify(latest_hands_data)
                        latest_stable_gesture = result_obj.gesture
                        latest_raw_gesture = result_obj.raw_gesture
                        latest_confidence = int(result_obj.confidence)

                    elif current_time - last_result_receive_time > 0.25:
                        # F-04 / Stale ML TTL: clear landmarks and reset automation
                        if latest_hands_data is not None:
                            logger.warning("Stale MediaPipe result TTL expired — releasing automation state.")
                            self.mapper.mouse.release_all()
                        latest_hands_data = None
                        latest_stable_gesture = "Unknown"
                        latest_raw_gesture = "Unknown"
                        latest_confidence = 0
                        self.classifier.classify([])

                    # 3. Always apply mapper using current ML result
                    display_frame = frame.copy()

                    if not self.automation_enabled:
                        import cv2
                        cv2.putText(display_frame, "AUTOMATION PAUSED", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                        latest_action = "Paused"
                        latest_progress = 0.0
                    elif latest_hands_data:
                        # Draw landmark dots
                        for hand_data in latest_hands_data:
                            h1 = hand_data["landmarks"]
                            for i in range(21):
                                cv2.circle(
                                    display_frame,
                                    (h1[i].pixel_x, h1[i].pixel_y),
                                    2,
                                    (0, 0, 255),
                                    -1,
                                )

                        display_frame, latest_action, latest_progress = self.mapper.process(
                            latest_hands_data,
                            latest_stable_gesture,
                            latest_raw_gesture,
                            display_frame,
                        )
                        display_frame = self.draw_overlays(
                            display_frame, latest_hands_data, latest_progress
                        )
                    else:
                        # Hand lost path — mapper will call on_hand_lost internally
                        display_frame, latest_action, latest_progress = self.mapper.process(
                            [], "None", "None", display_frame
                        )

                    # Telemetry
                    time_diff = time.perf_counter() - loop_start
                    current_fps = (1.0 / time_diff) if time_diff > 0 else 60.0
                    self.fps_history.append(current_fps)
                    fps = int(sum(self.fps_history) / len(self.fps_history))
                    avg_latency = (
                        int(sum(self.latency_history) / len(self.latency_history))
                        if self.latency_history
                        else 0
                    )

                    try:
                        if self.frame_queue.full():
                            self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait((
                            display_frame, latest_hands_data,
                            self.mapper.mode, latest_stable_gesture,
                            latest_raw_gesture, latest_confidence,
                            latest_action, fps,
                            self.cpu_usage, self.ram_usage,
                            is_connected, self.mapper.is_sleeping,
                            avg_latency, self.automation_enabled
                        ))
                    except (queue.Empty, queue.Full):
                        pass

            except Exception:
                logger.exception("Error in processing loop:")

            elapsed = time.perf_counter() - loop_start
            sleep_time = (1.0 / 60.0) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def update_ui_loop(self):
        if not self.running and self.process_thread is None:
            # System never started (no camera) — still show UI
            pass

        try:
            if not self.frame_queue.empty():
                (
                    frame, hands_data, mode, stable_gesture, raw_gesture,
                    confidence, action, fps, cpu_usage, ram_usage,
                    camera_on, is_sleeping, avg_latency, automation_enabled
                ) = self.frame_queue.get_nowait()
                self.ui.current_hands_data = hands_data
                self.ui.update_dashboard(
                    mode, stable_gesture, raw_gesture, confidence,
                    action, fps, cpu_usage, ram_usage,
                    camera_on, is_sleeping, avg_latency, automation_enabled
                )
                self.ui.update_frame(frame)
        except Exception:
            logger.exception("Error in UI update loop:")

        self.ui.after(15, self.update_ui_loop)

    def run(self):
        try:
            self.ui.mainloop()
        except Exception:
            logger.exception("App crashed:")
        finally:
            self.stop_system()


if __name__ == "__main__":
    app = MainApp()
    app.run()
