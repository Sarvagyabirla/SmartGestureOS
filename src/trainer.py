import json
import os
from .logger import logger

class GestureTrainer:
    def __init__(self, save_path="models/custom_gestures.json"):
        self.save_path = save_path
        self.gestures = self._load()
        
    def _load(self):
        if os.path.exists(self.save_path):
            with open(self.save_path, 'r') as f:
                return json.load(f)
        return {}
        
    def save(self):
        os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
        with open(self.save_path, 'w') as f:
            json.dump(self.gestures, f, indent=4)
            
    def record_gesture(self, name, lms_list):
        if not lms_list or len(lms_list) < 21:
            return False
            
        # Normalize relative to wrist
        wrist = lms_list[0]
        normalized = []
        for lm in lms_list:
            normalized.append({
                "id": lm[0],
                "x": lm[3] - wrist[3],
                "y": lm[4] - wrist[4],
                "z": lm[5] - wrist[5]
            })
            
        if name not in self.gestures:
            self.gestures[name] = []
            
        self.gestures[name].append(normalized)
        self.save()
        logger.info(f"Recorded sample for custom gesture: {name}")
        return True
