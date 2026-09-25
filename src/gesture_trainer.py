"""
GestureTrainer — custom gesture training and classification.

F-37 FIX: Gesture names are sanitized before saving:
    - Allowed: letters, numbers, spaces, underscores, hyphens (1–32 chars)
    - Built-in gesture names cannot be overwritten
    - JSON loaded defensively with error recovery
"""

import json
import re
import numpy as np
from pathlib import Path
from src.paths import CUSTOM_GESTURES_DIR
from .logger import logger

# F-37: name validation
_GESTURE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _\-]{1,32}$")

# Built-in gesture names that custom gestures must NOT shadow
_BUILTIN_GESTURE_NAMES = frozenset({
    "Pinch", "Pointing", "Open Palm", "Closed Fist",
    "Two Fingers", "Three Fingers", "Four Fingers",
    "Victory", "Crossed Fingers", "Thumb Up", "Thumb Down",
    "Rock On", "Call Me", "Middle Finger", "Unknown", "None",
})

_MAX_SAMPLES_PER_GESTURE = 50


def validate_gesture_name(name: str) -> tuple[bool, str]:
    """Returns (is_valid, reason_if_invalid)."""
    if not name:
        return False, "Gesture name cannot be empty."
    if not _GESTURE_NAME_PATTERN.match(name):
        return False, (
            "Gesture name may only contain letters, numbers, spaces, "
            "underscores, and hyphens (max 32 characters)."
        )
    # Case-insensitive check: 'pinch' must not shadow 'Pinch' (§20)
    if name.lower() in {n.lower() for n in _BUILTIN_GESTURE_NAMES}:
        return False, f"'{name}' conflicts with a built-in gesture name and cannot be used."
    return True, ""


class GestureTrainer:
    def __init__(self):
        self.models_dir = CUSTOM_GESTURES_DIR
        # { "gesture_name": [normalized_vector_1, ...] }
        self.custom_gestures: dict[str, list] = {}
        self.load_models()

    # ── Normalization ─────────────────────────────────────────────────────────

    def _normalize_landmarks(self, landmarks) -> list | None:
        """
        Normalize 21 landmarks to a translation-, rotation-, and scale-invariant
        vector of 63 floats (21 × 3).
        """
        if not landmarks or len(landmarks) != 21:
            return None

        # Convert to numpy (x, y, z)
        if isinstance(landmarks[0], dict):
            coords = np.array([[lm["x"], lm["y"], lm.get("z", 0.0)] for lm in landmarks])
        elif hasattr(landmarks[0], "x"):
            coords = np.array([[lm.x, lm.y, getattr(lm, "z", 0.0)] for lm in landmarks])
        else:
            coords = np.array([[lm[1], lm[2], lm[3] if len(lm) > 3 else 0.0] for lm in landmarks])

        # 1. Translate wrist to origin
        wrist = coords[0].copy()
        coords -= wrist

        # 2. Rotational alignment: align wrist→middle_mcp to Y-axis
        y_axis = coords[9].copy()
        norm_y = np.linalg.norm(y_axis)
        y_axis = y_axis / norm_y if norm_y > 1e-6 else np.array([0.0, 1.0, 0.0])

        x_axis_approx = coords[17] - coords[5]
        z_axis = np.cross(x_axis_approx, y_axis)
        norm_z = np.linalg.norm(z_axis)
        z_axis = z_axis / norm_z if norm_z > 1e-6 else np.array([0.0, 0.0, 1.0])

        x_axis = np.cross(y_axis, z_axis)
        norm_x = np.linalg.norm(x_axis)
        x_axis = x_axis / (norm_x + 1e-6)

        R = np.vstack([x_axis, y_axis, z_axis])
        coords = coords @ R.T

        # 3. Scale normalization
        distances = np.linalg.norm(coords, axis=1)
        max_dist = np.max(distances)
        if max_dist > 0:
            coords /= max_dist

        return coords.flatten().tolist()

    # ── Training ──────────────────────────────────────────────────────────────

    def add_sample(self, gesture_name: str, landmarks) -> tuple[bool, str]:
        """
        Add a training sample. Returns (success, message).
        F-37: validates name, guards against built-in names, enforces sample limit.
        """
        valid, reason = validate_gesture_name(gesture_name)
        if not valid:
            return False, reason

        normalized = self._normalize_landmarks(landmarks)
        if normalized is None:
            return False, "Invalid landmark data (requires exactly 21 points)."

        if gesture_name not in self.custom_gestures:
            self.custom_gestures[gesture_name] = []

        if len(self.custom_gestures[gesture_name]) >= _MAX_SAMPLES_PER_GESTURE:
            return False, (
                f"Maximum of {_MAX_SAMPLES_PER_GESTURE} samples reached for '{gesture_name}'. "
                "Delete the gesture and retrain if needed."
            )

        self.custom_gestures[gesture_name].append(normalized)
        return True, f"Sample added ({len(self.custom_gestures[gesture_name])} total)."

    # ── Persistence ───────────────────────────────────────────────────────────

    def save_models(self) -> bool:
        """Atomic save to prevent corruption."""
        path = self.models_dir / "custom_gestures.json"
        tmp_path = path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.custom_gestures, f)
            tmp_path.replace(path)
            logger.info("Custom gestures saved.")
            return True
        except Exception as e:
            logger.error(f"Failed to save custom gestures: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

    def load_models(self) -> None:
        """Defensive JSON loading with recovery on corruption."""
        path = self.models_dir / "custom_gestures.json"
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Validate structure: must be dict of str → list of lists
            if not isinstance(data, dict):
                raise ValueError("custom_gestures.json must be a JSON object.")
            self.custom_gestures = {
                k: v for k, v in data.items()
                if isinstance(k, str) and isinstance(v, list)
            }
            logger.info(f"Loaded {len(self.custom_gestures)} custom gesture(s).")
        except Exception as e:
            logger.error(f"Failed to load custom gestures (resetting): {e}")
            self.custom_gestures = {}

    # ── Classification ────────────────────────────────────────────────────────

    def classify(self, landmarks, threshold: float = 0.35) -> tuple[str | None, float]:
        """
        Compare landmarks against stored custom gestures.
        Returns (gesture_name, distance) or (None, inf).
        """
        if not self.custom_gestures:
            return None, float("inf")

        target = self._normalize_landmarks(landmarks)
        if target is None:
            return None, float("inf")

        target_arr = np.array(target)
        best_match = None
        best_dist = float("inf")

        for name, samples in self.custom_gestures.items():
            if not samples:
                continue
            samples_arr = np.array(samples)
            distances = np.linalg.norm(samples_arr - target_arr, axis=1)
            min_dist = float(np.min(distances))
            if min_dist < best_dist:
                best_dist = min_dist
                best_match = name

        if best_dist < threshold:
            return best_match, best_dist
        return None, best_dist

    # ── Management ────────────────────────────────────────────────────────────

    def delete_gesture(self, gesture_name: str) -> bool:
        if gesture_name in self.custom_gestures:
            del self.custom_gestures[gesture_name]
            self.save_models()
            return True
        return False

    def get_gesture_info(self) -> dict:
        """Returns metadata about stored custom gestures."""
        return {
            name: {"sample_count": len(samples)}
            for name, samples in self.custom_gestures.items()
        }


# Global singleton
gesture_trainer = GestureTrainer()
