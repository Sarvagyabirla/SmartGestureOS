import cv2
import mediapipe as mp
import time
import threading
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from .logger import logger

class GestureDetector:
    def __init__(self, max_hands=2, detection_con=0.8, tracking_con=0.8):
        self.results = None
        self.last_valid_results = None
        self.last_valid_time = 0
        self.lock = threading.Lock()
        
        try:
            base_options = python.BaseOptions(model_asset_path='models/hand_landmarker.task')
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
            logger.info("HandLandmarker initialized successfully in LIVE_STREAM mode.")
        except Exception as e:
            logger.error(f"Failed to initialize HandLandmarker: {e}")
            self.detector = None
            
    def _result_callback(self, result: vision.HandLandmarkerResult, output_image: mp.Image, timestamp_ms: int):
        with self.lock:
            self.results = result
            if result and result.hand_landmarks:
                self.last_valid_results = result
                self.last_valid_time = time.time()
            
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
            
    def get_latest_results(self):
        with self.lock:
            now = time.time()
            # Landmark loss recovery (allow up to 150ms of missing data to reuse old data)
            if self.results and self.results.hand_landmarks:
                return self.results
            elif self.last_valid_results and (now - self.last_valid_time < 0.15):
                return self.last_valid_results
            return None
            
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

    def get_all_hands_data(self, img_shape):
        hands_data = []
        results = self.get_latest_results()
        
        if results and results.hand_landmarks:
            h, w, _ = img_shape
            for i, hand_lms in enumerate(results.hand_landmarks):
                lms_list = []
                for id, lm in enumerate(hand_lms):
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    lms_list.append([id, cx, cy, lm.x, lm.y, lm.z])
                
                score = 0
                if results.handedness and i < len(results.handedness):
                    score = results.handedness[i][0].score * 100
                    
                hands_data.append({
                    "landmarks": lms_list,
                    "score": int(score)
                })
        return hands_data
