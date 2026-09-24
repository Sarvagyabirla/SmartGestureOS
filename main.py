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
                logger.exception("Stats error:")
                time.sleep(1)

    def stop_system(self):
        self.running = False
        
        # Unblock queues to prevent thread lock
        try:
            while not self.frame_queue.empty():
                self.frame_queue.get_nowait()
        except queue.Empty:
            pass
            
        self.camera.stop()
        if hasattr(self, 'mapper'):
            self.mapper.cleanup()
        if hasattr(self, 'detector'):
            self.detector.close()
        if self.process_thread:
            self.process_thread.join(timeout=2.0)
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
        last_timestamp_ms = -1
        inference_interval = 1.0 / 30.0
        
        # Telemetry
        self.fps_history = collections.deque(maxlen=30)
        self.latency_history = collections.deque(maxlen=30)
        
        # Latest results state
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

                if not self.camera.is_connected:
                    import numpy as np
                    frame = np.zeros((self.camera.height, self.camera.width, 3), dtype=np.uint8)
                    cv2.putText(frame, "CAMERA DISCONNECTED - RECOVERING...", (50, self.camera.height//2), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    try:
                        if self.frame_queue.full():
                            self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait((frame, [], self.mapper.mode, "Unknown", "Unknown", 0, None, 0, self.cpu_usage, self.ram_usage, self.camera.is_connected, self.mapper.is_sleeping, 0))
                    except (queue.Empty, queue.Full):
                        pass
                    time.sleep(0.1)
                    continue

                if frame is not None and frame_id != last_frame_id:
                    last_frame_id = frame_id
                    current_time = time.perf_counter()
                    
                    inference_interval = 1.0 / 5.0 if self.mapper.is_sleeping else 1.0 / 30.0

                    # 1. Send frame to async ML if ready
                    if current_time - last_inference_time >= inference_interval:
                        timestamp_ms = int(current_time * 1000)
                        if timestamp_ms <= last_timestamp_ms:
                            timestamp_ms = last_timestamp_ms + 1
                        last_timestamp_ms = timestamp_ms
                        
                        small_frame = cv2.resize(frame, (640, 360))
                        self.detector.detect_async(small_frame, timestamp_ms)
                        last_inference_time = current_time

                    # 2. Check for new ML results
                    result_ts, results = None, None
                    while not self.detector.results_queue.empty():
                        result_ts, results = self.detector.results_queue.get_nowait()

                    if result_ts is not None:
                        last_result_receive_time = current_time
                        latency_ms = int(time.perf_counter() * 1000) - result_ts
                        self.latency_history.append(latency_ms)
                        
                        latest_hands_data = self.detector.get_all_hands_data(results, frame.shape)
                        
                        # Process logic with the new results
                        result_obj = self.classifier.classify(latest_hands_data)
                        latest_stable_gesture = result_obj.gesture
                        latest_raw_gesture = result_obj.raw_gesture
                        latest_confidence = int(result_obj.confidence)
                    elif current_time - last_result_receive_time > 0.25:
                        if latest_hands_data is not None:
                            logger.warning("Stale MediaPipe result timeout, clearing hands.")
                        latest_hands_data = None
                        latest_stable_gesture = "Unknown"
                        latest_raw_gesture = "Unknown"
                        latest_confidence = 0
                        # Also tell the classifier that hands are lost so its state resets
                        self.classifier.classify([])
                        
                    # 3. Always apply mapper (for continuous tracking like mouse move) and draw on CURRENT frame
                    display_frame = frame.copy() # One copy for display safety if drawing
                    
                    if latest_hands_data:
                        # Draw landmarks
                        for hand_data in latest_hands_data:
                            # Reconstruct mediapipe landmarks for drawing if needed, or just use our data
                            # Since we just want the visual, we can rely on our parsed data
                            h1 = hand_data['landmarks']
                            for i in range(21):
                                cv2.circle(display_frame, (h1[i].pixel_x, h1[i].pixel_y), 2, (0, 0, 255), -1)
                        
                        # Process Mapper
                        display_frame, latest_action, latest_progress = self.mapper.process(
                            latest_hands_data, latest_stable_gesture, latest_raw_gesture, display_frame
                        )
                        display_frame = self.draw_overlays(display_frame, latest_hands_data, latest_progress)
                    else:
                        # Process empty data to trigger HAND_LOST
                        display_frame, latest_action, latest_progress = self.mapper.process(
                            [], "None", "None", display_frame
                        )

                    # Telemetry calculation
                    time_diff = time.perf_counter() - loop_start
                    current_fps = (1 / time_diff) if time_diff > 0 else 60
                    self.fps_history.append(current_fps)
                    fps = int(sum(self.fps_history) / len(self.fps_history))
                    avg_latency = int(sum(self.latency_history) / len(self.latency_history)) if self.latency_history else 0

                    try:
                        if self.frame_queue.full():
                            self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait((display_frame, latest_hands_data, self.mapper.mode, latest_stable_gesture, latest_raw_gesture, latest_confidence, latest_action, fps, self.cpu_usage, self.ram_usage, self.camera.is_connected, self.mapper.is_sleeping, avg_latency))
                    except (queue.Empty, queue.Full):
                        pass

            except Exception as e:
                logger.exception("Error in processing loop:")

            elapsed = time.perf_counter() - loop_start
            sleep_time = (1.0 / 60.0) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def update_ui_loop(self):
        if not self.running:
            return

        try:
            if not self.frame_queue.empty():
                frame, hands_data, mode, stable_gesture, raw_gesture, confidence, action, fps, cpu_usage, ram_usage, camera_on, is_sleeping, avg_latency = self.frame_queue.get_nowait()
                self.ui.current_hands_data = hands_data  # Store for trainer window
                self.ui.update_dashboard(mode, stable_gesture, raw_gesture, confidence, action, fps, cpu_usage, ram_usage, camera_on, is_sleeping, avg_latency)
                self.ui.update_frame(frame)
        except Exception as e:
            logger.exception("Error in UI update loop:")

        self.ui.after(15, self.update_ui_loop)

    def run(self):
        try:
            self.ui.mainloop()
        except Exception as e:
            logger.exception("App crashed:")
        finally:
            self.stop_system()

if __name__ == "__main__":
    app = MainApp()
    app.run()
