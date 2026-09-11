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
        self.mapper = GestureMapper(SETTINGS["camera"]["width"], SETTINGS["camera"]["height"])
        self.fps_history = collections.deque(maxlen=30)

        self.ui = SmartGestureApp(close_callback=self.stop_system)

        self.running = False
        self.frame_queue = queue.Queue(maxsize=1)
        self.process_thread = None
        self.stats_thread = None

        self.cpu_usage = 0.0
        self.ram_usage = 0.0

        self.start_system()

    def start_system(self):
        if self.camera.start():
            self.running = True
            self.process_thread = threading.Thread(target=self.processing_loop, daemon=True)
            self.process_thread.start()

            self.stats_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
            self.stats_thread.start()

            self.update_ui_loop()
            return True
        return False

    def monitoring_loop(self):
        try:
            process = psutil.Process(os.getpid())
            process.cpu_percent() # initial call
        except psutil.NoSuchProcess:
            return

        while self.running:
            try:
                # Sleep in smaller increments to allow thread to exit quickly
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
                self.ram_usage = total_ram / (1024 * 1024) # MB
            except Exception as e:
                logger.error(f"Stats error: {e}")
                time.sleep(1)

    def stop_system(self):
        self.running = False
        self.camera.stop()
        if hasattr(self, 'mapper'):
            self.mapper.cleanup()
        if hasattr(self, 'detector'):
            self.detector.close()
        if self.process_thread:
            self.process_thread.join(timeout=1.0)
        if self.stats_thread:
            self.stats_thread.join(timeout=1.0)

    def draw_overlays(self, frame, hands_data, progress):
        if not hands_data:
            return frame

        h1 = hands_data[0]['landmarks']
        index_x, index_y = h1[8].pixel_x, h1[8].pixel_y

        # Virtual cursor
        cv2.circle(frame, (index_x, index_y), 12, (255, 255, 50), 2)
        cv2.circle(frame, (index_x, index_y), 3, (255, 255, 50), -1)

        # Gesture loading ring
        if progress > 0.0:
            center = (index_x, index_y)
            radius = 25
            angle = int(360 * progress)
            cv2.ellipse(frame, center, (radius, radius), -90, 0, angle, (0, 255, 0), 4)

        return frame

    def processing_loop(self):
        last_frame_id = -1
        last_inference_time = 0
        inference_interval = 1.0 / 30.0 # Max 30 FPS for ML inference
        pending_frames = {}

        while self.running:
            loop_start = time.time()
            try:
                frame, frame_id = self.camera.read()

                if not self.camera.is_connected:
                    import numpy as np
                    frame = np.zeros((self.camera.height, self.camera.width, 3), dtype=np.uint8)
                    cv2.putText(frame, "CAMERA DISCONNECTED - RECOVERING...", (50, self.camera.height//2), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    try:
                        if self.frame_queue.full():
                            self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait((frame, [], self.mapper.mode, "Unknown", 0, None, 0, self.cpu_usage, self.ram_usage, self.camera.is_connected, self.mapper.is_sleeping))
                    except queue.Empty:
                        pass
                    time.sleep(0.1)
                    continue

                if frame is not None and frame_id != last_frame_id:
                    last_frame_id = frame_id

                    current_time = time.time()
                    # Throttle to 5 FPS if sleeping to save massive CPU, otherwise max 30 FPS
                    inference_interval = 1.0 / 5.0 if self.mapper.is_sleeping else 1.0 / 30.0

                    if current_time - last_inference_time >= inference_interval:
                        timestamp_ms = int(current_time * 1000)
                        small_frame = cv2.resize(frame, (640, 360))
                        pending_frames[timestamp_ms] = frame.copy()
                        self.detector.detect_async(small_frame, timestamp_ms)
                        last_inference_time = current_time

                    result_ts, results = None, None

                    # Drain the queue to get the newest available result
                    while not self.detector.results_queue.empty():
                        result_ts, results = self.detector.results_queue.get_nowait()

                    if result_ts is not None and result_ts in pending_frames:
                        matched_frame = pending_frames.pop(result_ts)

                        # Clean up older pending frames to prevent memory leaks
                        old_keys = [k for k in pending_frames.keys() if k < result_ts]
                        for k in old_keys:
                            del pending_frames[k]

                        # Process matched_frame
                        hands_data = self.detector.get_all_hands_data(results, matched_frame.shape)

                        if results and results.hand_landmarks:
                            for hand_lms in results.hand_landmarks:
                                self.detector.draw_landmarks(matched_frame, hand_lms)

                        result_obj = self.classifier.classify(hands_data)
                        stable_gesture, raw_gesture, confidence = result_obj.gesture, result_obj.raw_gesture, int(result_obj.confidence)
                        matched_frame, action, progress = self.mapper.process(hands_data, stable_gesture, raw_gesture, matched_frame)
                        matched_frame = self.draw_overlays(matched_frame, hands_data, progress)

                        time_diff = time.time() - loop_start
                        current_fps = (1 / time_diff) if time_diff > 0 else 60
                        self.fps_history.append(current_fps)
                        fps = int(sum(self.fps_history) / len(self.fps_history))

                        # Update queue with latest frame and stats
                        if not self.frame_queue.full():
                            self.frame_queue.put((matched_frame, hands_data, self.mapper.mode, stable_gesture, confidence, action, fps, self.cpu_usage, self.ram_usage, self.camera.is_connected, self.mapper.is_sleeping))
                        else:
                            # Clear old frame to keep it real-time
                            try:
                                self.frame_queue.get_nowait()
                                self.frame_queue.put_nowait((matched_frame, hands_data, self.mapper.mode, stable_gesture, confidence, action, fps, self.cpu_usage, self.ram_usage, self.camera.is_connected, self.mapper.is_sleeping))
                            except queue.Empty:
                                pass

            except Exception as e:
                logger.error(f"Error in processing loop: {e}")

            # Pace loop to 60 FPS (16.6ms per frame)
            elapsed = time.time() - loop_start
            sleep_time = (1.0 / 60.0) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def update_ui_loop(self):
        if not self.running:
            return

        try:
            if not self.frame_queue.empty():
                frame, hands_data, mode, gesture, confidence, action, fps, cpu_usage, ram_usage, camera_on, is_sleeping = self.frame_queue.get_nowait()
                self.ui.current_hands_data = hands_data  # Store for trainer window
                self.ui.update_dashboard(mode, gesture, confidence, action, fps, cpu_usage, ram_usage, camera_on, is_sleeping)
                self.ui.update_frame(frame)
        except Exception as e:
            logger.error(f"Error in UI update loop: {e}")

        self.ui.after(15, self.update_ui_loop)

    def run(self):
        try:
            self.ui.mainloop()
        except Exception as e:
            logger.error(f"App crashed: {e}")
        finally:
            self.stop_system()

if __name__ == "__main__":
    app = MainApp()
    app.run()
