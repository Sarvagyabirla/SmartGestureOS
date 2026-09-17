import numpy as np
import time
from collections import deque, Counter
from .utils import get_angle
from .gesture_trainer import gesture_trainer
from config import SETTINGS
from .models import Landmark, GestureResult

class GestureClassifier:
    def __init__(self, confidence_threshold=70, hold_time_ms=300):
        self.tip_ids = [4, 8, 12, 16, 20]
        self.pip_ids = [3, 6, 10, 14, 18]
        self.mcp_ids = [2, 5, 9, 13, 17]
        self.confidence_ema = 0.0
        self.confidence_threshold = confidence_threshold
        
        self.hold_time = hold_time_ms / 1000.0
        self.history = deque(maxlen=5) # Mode filter for jitter
        self.last_stable_gesture = "None"
        
        from src.settings_manager import settings_manager
        settings_manager.register_callback(self.on_settings_changed)
        
    def on_settings_changed(self):
        from config import SETTINGS
        hold_time_ms = SETTINGS.get("gestures", {}).get("hold_time_ms", 300)
        self.hold_time = hold_time_ms / 1000.0
        
        calib = SETTINGS.get("calibration", {})
        self.pinch_enter_threshold = calib.get("pinch_enter_threshold", 0.45)
        self.pinch_release_threshold = calib.get("pinch_release_threshold", 0.6)
        self.two_finger_max_spacing = calib.get("two_finger_max_spacing", 0.2)
        self.victory_min_spacing = calib.get("victory_min_spacing", 0.35)
        
    def get_3d_point(self, lm: Landmark):
        return np.array([lm.x, lm.y, lm.z])

    def fingers_up(self, lms_list):
        if not lms_list or len(lms_list) < 21:
            return [], []
            
        fingers = []
        scores = []
        
        wrist = self.get_3d_point(lms_list[0])
        middle_mcp = self.get_3d_point(lms_list[9])
        hand_size = max(0.01, np.linalg.norm(wrist - middle_mcp))
        margin = hand_size * 0.15 # 15% of hand size margin to prevent noise jitter
        
        # Thumb: compare distance of tip to pinky mcp vs thumb mcp to pinky mcp
        thumb_tip = self.get_3d_point(lms_list[4])
        thumb_mcp = self.get_3d_point(lms_list[2])
        pinky_mcp = self.get_3d_point(lms_list[17])
        
        d_tip_pinky = np.linalg.norm(thumb_tip - pinky_mcp)
        d_mcp_pinky = np.linalg.norm(thumb_mcp - pinky_mcp)
        
        diff_thumb = d_tip_pinky - d_mcp_pinky
        is_thumb_up = 1 if diff_thumb > margin else 0
        fingers.append(is_thumb_up)
        
        s_thumb = min(100.0, max(0.0, (diff_thumb / (margin * 2)) * 100.0))
        if is_thumb_up == 0:
            s_thumb = min(100.0, max(0.0, (-diff_thumb / (margin * 2)) * 100.0))
        scores.append(s_thumb)
        
        # Other fingers: Check if tip is further from mcp than pip
        for id in range(1, 5):
            tip = self.get_3d_point(lms_list[self.tip_ids[id]])
            pip = self.get_3d_point(lms_list[self.pip_ids[id]])
            mcp = self.get_3d_point(lms_list[self.mcp_ids[id]])
            
            d_tip_mcp = np.linalg.norm(tip - mcp)
            d_pip_mcp = np.linalg.norm(pip - mcp)
            
            diff = d_tip_mcp - d_pip_mcp
            is_finger_up = 1 if diff > margin else 0
            fingers.append(is_finger_up)
            
            s = min(100.0, max(0.0, (diff / (margin * 2)) * 100.0))
            if is_finger_up == 0:
                s = min(100.0, max(0.0, (-diff / (margin * 2)) * 100.0))
            scores.append(s)
            
        return fingers, scores

    def raw_classify(self, hands_data):
        if not hands_data:
            return "None", 0.0
            
        # Single hand gestures
        h1 = hands_data[0]
        lms_list = h1['landmarks']
        hand_score = h1['score']
        fingers, scores = self.fingers_up(lms_list)
        
        if not fingers:
            return "None", 0.0
            
        def calc_shape_score():
            # Average the continuous scores for all 5 fingers
            return sum(scores) / 5.0
            
        shape_score = calc_shape_score()
            
        thumb_tip = self.get_3d_point(lms_list[4])
        index_tip = self.get_3d_point(lms_list[8])
        middle_tip = self.get_3d_point(lms_list[12])
        wrist = self.get_3d_point(lms_list[0])
        index_mcp = self.get_3d_point(lms_list[5])
        middle_mcp = self.get_3d_point(lms_list[9])
        
        hand_size = np.linalg.norm(wrist - middle_mcp)
        d_pinch = np.linalg.norm(thumb_tip - index_tip)
        
        if not hasattr(self, 'is_pinching'):
            self.is_pinching = False
            
        enter_thresh = getattr(self, 'pinch_enter_threshold', 0.45)
        release_thresh = getattr(self, 'pinch_release_threshold', 0.6)
        
        pinch_ratio = d_pinch / hand_size
        if not self.is_pinching:
            if pinch_ratio < enter_thresh:
                self.is_pinching = True
        else:
            if pinch_ratio > release_thresh:
                self.is_pinching = False
                
        d_pinch_to_palm = np.linalg.norm(index_tip - middle_mcp)
        true_pinch = self.is_pinching and (d_pinch_to_palm > hand_size * 0.5)
        
        # Check palm orientation for thumb up/down using relative y position
        thumb_is_higher_than_mcp = thumb_tip[1] <= middle_mcp[1]

        if fingers == [1, 1, 1, 1, 1]: 
            return "Open Palm", shape_score
        elif true_pinch: 
            # Linear map of pinch confidence within thresholds
            pinch_score = max(0.0, min(100.0, 100.0 - ((pinch_ratio - 0.2) / max(0.01, (release_thresh - 0.2))) * 100.0))
            return "Pinch", pinch_score
        elif fingers == [0, 0, 0, 0, 0]: 
            return "Closed Fist", shape_score
        elif fingers == [1, 0, 0, 0, 0]: 
            if thumb_is_higher_than_mcp: return "Thumb Up", shape_score
            else: return "Thumb Down", shape_score
        elif fingers[1:] == [0, 0, 0, 0]: 
            return "Closed Fist", shape_score
        elif fingers[1:] == [0, 1, 0, 0]: 
            return "Middle Finger", shape_score
        elif fingers[1:] == [1, 0, 0, 0]: 
            return "Pointing", shape_score
        elif fingers[1:3] == [1, 1] and fingers[3:] == [0, 0]:
            d_index_middle = np.linalg.norm(index_tip - middle_tip)
            d_mcp = np.linalg.norm(index_mcp - middle_mcp)
            
            # Calculate divergence angle
            v_index = index_tip - index_mcp
            v_middle = middle_tip - middle_mcp
            norm_index = np.linalg.norm(v_index)
            norm_middle = np.linalg.norm(v_middle)
            
            angle_deg = 0.0
            if norm_index > 0 and norm_middle > 0:
                cos_angle = np.dot(v_index, v_middle) / (norm_index * norm_middle)
                angle_deg = np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
                
            divergence_ratio = d_index_middle / max(0.01, d_mcp)
            
            # Check for Crossed Fingers using 3D vector dot product
            v_mcp = middle_mcp - index_mcp
            v_tip = middle_tip - index_tip
            is_crossed = np.dot(v_mcp, v_tip) < 0
            
            # Thresholds from settings or defaults
            max_two_finger = getattr(self, 'two_finger_max_spacing', 0.2)
            min_victory = getattr(self, 'victory_min_spacing', 0.35)
            
            if is_crossed and d_index_middle < hand_size * (max_two_finger * 1.5):
                return "Crossed Fingers", shape_score
                
            is_victory = (d_index_middle > hand_size * min_victory) and (angle_deg > 15.0) and (divergence_ratio > 1.5)
            is_two_fingers = (d_index_middle <= hand_size * max_two_finger) or (angle_deg < 10.0 and divergence_ratio < 1.3)
            
            if is_victory:
                return "Victory", shape_score
            elif is_two_fingers:
                return "Two Fingers", shape_score
            else:
                return "Unknown", 0.0 # Ambiguity band
        elif fingers[1:] == [1, 1, 1, 0]: 
            return "Three Fingers", shape_score
        elif fingers[1:] == [1, 1, 1, 1]: 
            return "Four Fingers", shape_score
        elif fingers == [1, 1, 0, 0, 1]: 
            return "Rock On", shape_score
        elif fingers == [1, 0, 0, 0, 1]: 
            return "Call Me", shape_score
            
        # Check Custom Gestures last
        custom_name, custom_dist = gesture_trainer.classify(lms_list, threshold=0.35)
        if custom_name:
            raw_score = max(0.0, 1.0 - (custom_dist / 0.35)) * 100.0
            return custom_name, raw_score
            
        return "Unknown", 0.0

    def classify(self, hands_data) -> GestureResult:
        if not hands_data:
            self.is_pinching = False
            
        raw_gesture, raw_score = self.raw_classify(hands_data)
        
        if not hasattr(self, 'last_raw_gesture'):
            self.last_raw_gesture = "None"
            
        if raw_gesture != self.last_raw_gesture:
            self.confidence_ema = raw_score
            self.last_raw_gesture = raw_gesture
        else:
            self.confidence_ema = (0.6 * self.confidence_ema) + (0.4 * raw_score)
        
        self.history.append(raw_gesture)
        
        stability = 0.0
        # Use mode of last N frames for stability (jitter filter)
        if len(self.history) > 0:
            counts = Counter(self.history)
            most_common = counts.most_common(1)[0][0]
            count = counts[most_common]
            stability = (count / len(self.history)) * 100.0
            
            req_count = max(1, len(self.history) // 2 + 1)
            
            # Stronger stability required for switching between geometrically similar poses
            similar_poses = [{"Two Fingers", "Victory", "Crossed Fingers"}, {"Open Palm", "Four Fingers"}]
            if most_common != self.last_stable_gesture:
                for pose_group in similar_poses:
                    if most_common in pose_group and self.last_stable_gesture in pose_group:
                        req_count = max(req_count, len(self.history) - 1) # Require e.g. 4/5 agreement to switch between them
                        break
            
            if count >= req_count:
                self.last_stable_gesture = most_common
                
        if self.confidence_ema < self.confidence_threshold:
            return GestureResult("Unknown", raw_gesture, float(self.confidence_ema), float(stability), "Low confidence")
            
        return GestureResult(self.last_stable_gesture, raw_gesture, float(self.confidence_ema), float(stability))
