import cv2
import mediapipe as mp
import time
import threading
import queue
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from dataclasses import dataclass
from .logger import logger

from .models import Landmark


class GestureDetector:
    def __init__(self, max_hands=1, detection_con=0.8, tracking_con=0.8):
        self.results_queue = queue.Queue(maxsize=2)
        self.lock = threading.Lock()
        
        try:
            from src.paths import RESOURCE_DIR
            model_path = str(RESOURCE_DIR / 'models' / 'hand_landmarker.task')
            base_options = python.BaseOptions(model_asset_path=model_path)
            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.LIVE_STREAM,
                result_callback=self._result_callback,
                num_hands=max_hands,
                min_hand_detection_confidence=detection_con,
                min_hand_presence_confidence=tracking_con,
                min_tracking_confidence=tracking_con
            )
            self.detector = vision.HandLandmarker.create_from_options(options)
            self.available: bool = True
            self.error: str | None = None
            logger.info("HandLandmarker initialized successfully in LIVE_STREAM mode.")
        except Exception as e:
            logger.error(f"Failed to initialize HandLandmarker: {e}")
            self.detector = None
            self.available: bool = False
            self.error: str = str(e)

    def clear_results(self) -> None:
        """Drain all queued results to invalidate pre-reset callbacks (§9)."""
        drained = 0
        while not self.results_queue.empty():
            try:
                self.results_queue.get_nowait()
                drained += 1
            except queue.Empty:
                break
        if drained:
            logger.debug(f"GestureDetector: cleared {drained} stale result(s).")

    def _result_callback(self, result: vision.HandLandmarkerResult, output_image: mp.Image, timestamp_ms: int):
        try:
            if self.results_queue.full():
                try:
                    self.results_queue.get_nowait()
                except queue.Empty:
                    pass
            self.results_queue.put_nowait((timestamp_ms, result))
        except Exception as e:
            logger.error(f"Error in result callback: {e}")
            
    def detect_async(self, img, timestamp_ms):
        if not self.detector:
            return
        
        # Mediapipe requires RGB image
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_img)
        
        try:
            self.detector.detect_async(mp_image, timestamp_ms)
        except Exception as e:
            logger.error(f"Error in async detection: {e}")
            
    # get_latest_results is removed as results are now fetched from the queue
            
    def draw_landmarks(self, img, landmarks):
        h, w, _ = img.shape
        
        connections = [
            (0,1), (1,2), (2,3), (3,4),
            (0,5), (5,6), (6,7), (7,8),
            (5,9), (9,10), (10,11), (11,12),
            (9,13), (13,14), (14,15), (15,16),
            (13,17), (0,17), (17,18), (18,19), (19,20)
        ]
        
        # Draw connections with a neon-like glowing effect
        for start_idx, end_idx in connections:
            if start_idx < len(landmarks) and end_idx < len(landmarks):
                x1, y1 = int(landmarks[start_idx].x * w), int(landmarks[start_idx].y * h)
                x2, y2 = int(landmarks[end_idx].x * w), int(landmarks[end_idx].y * h)
                cv2.line(img, (x1, y1), (x2, y2), (200, 100, 255), 4) # Pinkish outer
                cv2.line(img, (x1, y1), (x2, y2), (255, 200, 255), 1) # Bright inner
                
        # Draw joints
        for i, lm in enumerate(landmarks):
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(img, (cx, cy), 5, (255, 255, 50), -1)  # Cyan outer ring (BGR)
            cv2.circle(img, (cx, cy), 2, (255, 255, 255), -1) # White center

    def get_all_hands_data(self, results, img_shape):
        hands_data = []
        
        if results and results.hand_landmarks:
            h, w, _ = img_shape
            # Assuming hand_world_landmarks are available in results
            world_lms = results.hand_world_landmarks if hasattr(results, 'hand_world_landmarks') else None
            
            for i, hand_lms in enumerate(results.hand_landmarks):
                lms_list = []
                current_world_lms = world_lms[i] if (world_lms and i < len(world_lms)) else None
                
                for id, lm in enumerate(hand_lms):
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    w_lm = current_world_lms[id] if current_world_lms else None
                    wx = w_lm.x if w_lm else 0.0
                    wy = w_lm.y if w_lm else 0.0
                    wz = w_lm.z if w_lm else 0.0
                    
                    lms_list.append(Landmark(
                        id=id, pixel_x=cx, pixel_y=cy,
                        x=lm.x, y=lm.y, z=lm.z,
                        world_x=wx, world_y=wy, world_z=wz
                    ))
                
                score = 0
                if results.handedness and i < len(results.handedness):
                    score = results.handedness[i][0].score * 100
                    
                hands_data.append({
                    "landmarks": lms_list,
                    "score": int(score)
                })
        return hands_data
        
    def close(self):
        if self.detector:
            try:
                self.detector.close()
            except Exception as e:
                logger.error(f"Error closing detector: {e}")
