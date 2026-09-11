import json
import numpy as np
from pathlib import Path
from src.paths import CUSTOM_GESTURES_DIR
from .logger import logger

class GestureTrainer:
    def __init__(self):
        self.models_dir = CUSTOM_GESTURES_DIR
        self.custom_gestures = {} # { "gesture_name": [normalized_vector_1, ...] }
        self.load_models()
        
    def _normalize_landmarks(self, landmarks):
        """
        Takes raw landmarks list [{'x': x, 'y': y, 'z': z}, ...].
        Returns a flattened numpy array of 63 floats (21 * 3) normalized by scale and translation.
        """
        if not landmarks or len(landmarks) != 21:
            return None
            
        # Convert to numpy array of just (x, y, z)
        if isinstance(landmarks[0], dict):
            coords = np.array([[lm['x'], lm['y'], lm.get('z', 0.0)] for lm in landmarks])
        elif hasattr(landmarks[0], 'x'):
            coords = np.array([[lm.x, lm.y, getattr(lm, 'z', 0.0)] for lm in landmarks])
        else:
            coords = np.array([[lm[1], lm[2], lm[3] if len(lm) > 3 else 0.0] for lm in landmarks])
        
        # 1. Translate wrist to origin
        wrist = coords[0]
        coords = coords - wrist
        
        # 2. Rotational Alignment
        # y-axis: wrist (0) to middle_mcp (9)
        y_axis = coords[9]
        norm_y = np.linalg.norm(y_axis)
        if norm_y > 1e-6:
            y_axis = y_axis / norm_y
        else:
            y_axis = np.array([0.0, 1.0, 0.0])
            
        # approximate x-axis from index_mcp (5) to pinky_mcp (17)
        x_axis_approx = coords[17] - coords[5]
        
        # z-axis: cross product of x_axis_approx and y_axis (palm normal)
        z_axis = np.cross(x_axis_approx, y_axis)
        norm_z = np.linalg.norm(z_axis)
        if norm_z > 1e-6:
            z_axis = z_axis / norm_z
        else:
            z_axis = np.array([0.0, 0.0, 1.0])
            
        # true x-axis: cross product of y_axis and z_axis
        x_axis = np.cross(y_axis, z_axis)
        x_axis = x_axis / (np.linalg.norm(x_axis) + 1e-6)
        
        # Rotation matrix to align to canonical frame
        R = np.vstack([x_axis, y_axis, z_axis])
        coords = coords @ R.T
        
        # 3. Scale normalization
        distances = np.linalg.norm(coords, axis=1)
        max_dist = np.max(distances)
        if max_dist > 0:
            coords = coords / max_dist
            
        return coords.flatten().tolist()
        
    def add_sample(self, gesture_name, landmarks):
        normalized = self._normalize_landmarks(landmarks)
        if not normalized:
            return False
            
        if gesture_name not in self.custom_gestures:
            self.custom_gestures[gesture_name] = []
            
        self.custom_gestures[gesture_name].append(normalized)
        return True
        
    def save_models(self):
        try:
            with open(self.models_dir / "custom_gestures.json", "w") as f:
                json.dump(self.custom_gestures, f)
            logger.info("Custom gestures saved successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to save custom gestures: {e}")
            return False
            
    def load_models(self):
        path = self.models_dir / "custom_gestures.json"
        if path.exists():
            try:
                with open(path, "r") as f:
                    self.custom_gestures = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load custom gestures: {e}")
                self.custom_gestures = {}
                
    def classify(self, landmarks, threshold=0.4):
        """
        Compares incoming landmarks against all stored custom gestures.
        Returns (gesture_name, distance) or (None, float('inf'))
        """
        if not self.custom_gestures:
            return None, float('inf')
            
        target = self._normalize_landmarks(landmarks)
        if not target:
            return None, float('inf')
            
        target = np.array(target)
        
        best_match = None
        best_dist = float('inf')
        
        for name, samples in self.custom_gestures.items():
            samples_arr = np.array(samples)
            # Calculate L2 distances to all samples of this gesture
            distances = np.linalg.norm(samples_arr - target, axis=1)
            min_dist = np.min(distances)
            
            if min_dist < best_dist:
                best_dist = min_dist
                best_match = name
                
        if best_dist < threshold:
            return best_match, best_dist
            
        return None, best_dist
        
    def delete_gesture(self, gesture_name):
        if gesture_name in self.custom_gestures:
            del self.custom_gestures[gesture_name]
            self.save_models()
            return True
        return False
        
gesture_trainer = GestureTrainer()
