import numpy as np
import time
from collections import deque
from .utils import get_angle
from .gesture_trainer import gesture_trainer
from config import SETTINGS

class GestureClassifier:
    def __init__(self, confidence_threshold=70, hold_time_ms=300):
        self.tip_ids = [4, 8, 12, 16, 20]
        self.pip_ids = [3, 6, 10, 14, 18]
        self.mcp_ids = [2, 5, 9, 13, 17]
        self.confidence_ema = 0.0
        self.confidence_threshold = confidence_threshold
        
        self.hold_time = hold_time_ms / 1000.0
        self.current_candidate = "None"
        self.candidate_start_time = 0
        self.last_stable_gesture = "None"
        
    def get_3d_point(self, lm):
        return np.array([lm[3], lm[4], lm[5]])

    def fingers_up(self, lms_list):
        if not lms_list or len(lms_list) < 21:
            return []
            
        fingers = []
        wrist = self.get_3d_point(lms_list[0])
        middle_mcp = self.get_3d_point(lms_list[9])
        hand_size = np.linalg.norm(wrist - middle_mcp)
        
        # Thumb: compare distance from tip to pinky mcp vs ip to pinky mcp
        thumb_tip = self.get_3d_point(lms_list[4])
        thumb_ip = self.get_3d_point(lms_list[3])
        pinky_mcp = self.get_3d_point(lms_list[17])
        
        d_tip_pinky = np.linalg.norm(thumb_tip - pinky_mcp)
        d_ip_pinky = np.linalg.norm(thumb_ip - pinky_mcp)
        thumb_up = 1 if (d_tip_pinky > d_ip_pinky) and (np.linalg.norm(thumb_tip - thumb_ip) > hand_size * 0.2) else 0
        fingers.append(thumb_up)
        
        # Other fingers: use distance ratio and angles
        for id in range(1, 5):
            tip = self.get_3d_point(lms_list[self.tip_ids[id]])
            pip = self.get_3d_point(lms_list[self.pip_ids[id]])
            mcp = self.get_3d_point(lms_list[self.mcp_ids[id]])
            
            d_tip_wrist = np.linalg.norm(tip - wrist)
            d_pip_wrist = np.linalg.norm(pip - wrist)
            d_tip_mcp = np.linalg.norm(tip - mcp)
            
            # Must be further from wrist than PIP, and fairly extended from MCP
            is_extended = 1 if (d_tip_wrist > d_pip_wrist) and (d_tip_mcp > hand_size * 0.4) else 0
            fingers.append(is_extended)
            
        return fingers

    def raw_classify(self, hands_data):
        if not hands_data:
            return "None", 0.0
            
        h1 = hands_data[0]
        lms_list = h1['landmarks']
        
        # Check Custom Gestures first
        custom_name, custom_dist = gesture_trainer.classify(lms_list, threshold=0.35)
        if custom_name:
            # Confidence is inverted distance (0 distance = 100% conf, 0.35 dist = 0%)
            raw_score = max(0.0, 1.0 - (custom_dist / 0.35))
            return custom_name, raw_score

        # Single hand gestures
        h1 = hands_data[0]
        lms_list = h1['landmarks']
        base_score = h1['score']
        fingers = self.fingers_up(lms_list)
        
        if not fingers:
            return "None", base_score
            
        thumb_tip = self.get_3d_point(lms_list[4])
        index_tip = self.get_3d_point(lms_list[8])
        middle_tip = self.get_3d_point(lms_list[12])
        wrist = self.get_3d_point(lms_list[0])
        middle_mcp = self.get_3d_point(lms_list[9])
        
        hand_size = np.linalg.norm(wrist - middle_mcp)
        d_pinch = np.linalg.norm(thumb_tip - index_tip)
        
        # True Pinch requires index and thumb close, AND distance from palm to be significant
        is_pinch = (d_pinch < hand_size * 0.45)
        d_pinch_to_palm = np.linalg.norm(index_tip - middle_mcp)
        true_pinch = is_pinch and (d_pinch_to_palm > hand_size * 0.5)
        
        # Check palm orientation for thumb up/down using relative y position
        thumb_is_higher_than_mcp = thumb_tip[1] < middle_mcp[1]

        if fingers == [1, 1, 1, 1, 1]: 
            return "Open Palm", base_score
        elif true_pinch: 
            return "Pinch", base_score
        elif fingers == [0, 0, 0, 0, 0]: 
            return "Closed Fist", base_score
        elif fingers == [1, 0, 0, 0, 0]: 
            if thumb_is_higher_than_mcp: return "Thumb Up", base_score
            else: return "Thumb Down", base_score
        elif fingers[1:] == [0, 0, 0, 0]: 
            return "Closed Fist", base_score
        elif fingers[1:] == [0, 1, 0, 0]: 
            return "Middle Finger", base_score
        elif fingers[1:] == [1, 0, 0, 0]: 
            return "Pointing", base_score
        elif fingers[1:3] == [1, 1] and fingers[3:] == [0, 0]:
            d_index_middle = np.linalg.norm(index_tip - middle_tip)
            
            # Check for Crossed Fingers (Index tip crosses Middle tip horizontally relative to their MCPs)
            index_mcp_x = lms_list[5][3]  # x_norm
            middle_mcp_x = lms_list[9][3] # x_norm
            index_tip_x = index_tip[0]
            middle_tip_x = middle_tip[0]
            
            is_crossed = (index_mcp_x < middle_mcp_x and index_tip_x > middle_tip_x) or (index_mcp_x > middle_mcp_x and index_tip_x < middle_tip_x)
            
            if is_crossed and d_index_middle < hand_size * 0.2:
                return "Crossed Fingers", base_score
            elif d_index_middle > hand_size * 0.35: # Spread apart
                return "Victory", base_score
            else:
                return "Two Fingers", base_score
        elif fingers[1:] == [1, 1, 1, 0]: 
            return "Three Fingers", base_score
        elif fingers[1:] == [1, 1, 1, 1]: 
            return "Four Fingers", base_score
        elif fingers[1:] == [1, 0, 0, 1]: 
            return "Rock On", base_score
        elif fingers[1:] == [0, 0, 0, 1]: 
            return "Call Me", base_score
            
        return "Unknown", base_score

    def classify(self, hands_data):
        gesture, raw_score = self.raw_classify(hands_data)
        
        self.confidence_ema = (0.6 * self.confidence_ema) + (0.4 * raw_score * 100)
        
        now = time.time()
        
        if gesture != self.current_candidate:
            self.current_candidate = gesture
            self.candidate_start_time = now
            
        # Gesture must remain stable for hold_time
        if now - self.candidate_start_time >= self.hold_time:
            self.last_stable_gesture = self.current_candidate
            
        if self.confidence_ema < self.confidence_threshold:
            return "Unknown", int(self.confidence_ema)
            
        return self.last_stable_gesture, int(self.confidence_ema)
