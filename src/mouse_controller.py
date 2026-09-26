import math
from .virtual_mouse import VirtualMouse
from .utils import get_distance
from .logger import logger

class MouseController:
    def __init__(self):
        from config import SETTINGS
        gestures = SETTINGS.get("gestures", {})
        sensitivity = float(gestures.get("sensitivity", 0.7))
        smoothing = max(1, min(20, int(gestures.get("smoothing", 2))))
        beta = max(0.01, sensitivity * 0.5)
        min_cutoff = self._smoothing_cutoff(smoothing)

        self.mouse = VirtualMouse(min_cutoff=min_cutoff, beta=beta, deadzone=1.0)
        from .event_engine import EventEngine
        self.engine = EventEngine(self)

        from src.settings_manager import settings_manager
        settings_manager.register_callback(self.on_settings_changed)
        self.on_settings_changed()

    @staticmethod
    def _smoothing_cutoff(smoothing: int) -> float:
        """Map the UI slider (1 = responsive, 20 = smooth) to One Euro cutoff."""
        smoothing = max(1, min(20, int(smoothing)))
        return 4.0 - ((smoothing - 1) / 19.0) * 2.8

    def on_settings_changed(self):
        from config import SETTINGS
        sensitivity = SETTINGS.get("gestures", {}).get("sensitivity", 0.7)
        smoothing = SETTINGS.get("gestures", {}).get("smoothing", 2)
        beta = max(0.01, sensitivity * 0.5)
        min_cutoff = self._smoothing_cutoff(smoothing)
        self.mouse.smoother.min_cutoff = min_cutoff
        self.mouse.smoother.beta = beta
        self.mouse.deadzone = max(0.1, (1.0 - sensitivity) * 2.0)

        # Update already-created One Euro filters as well as future filters.
        for axis_filter in (self.mouse.smoother.filter_x, self.mouse.smoother.filter_y):
            if axis_filter is not None:
                axis_filter.min_cutoff = min_cutoff
                axis_filter.beta = beta

    def process_landmarks(self, lms_list, stable_gesture, raw_gesture, frame_w, frame_h):
        if not lms_list or len(lms_list) < 21:
            self.release_all()
            return

        index_x, index_y = lms_list[8].pixel_x, lms_list[8].pixel_y

        # Calculate geometric scale factor based on bounding box / hand size
        from config import SETTINGS
        import numpy as np
        wrist = np.array([lms_list[0].x, lms_list[0].y, lms_list[0].z])
        middle_mcp = np.array([lms_list[9].x, lms_list[9].y, lms_list[9].z])
        current_hand_size = float(np.linalg.norm(wrist - middle_mcp))
        if not math.isfinite(current_hand_size):
            self.release_all()
            return
        current_hand_size = max(0.01, current_hand_size)
        base_hand_size = SETTINGS.get("gestures", {}).get("base_hand_size", current_hand_size)
        try:
            base_hand_size = float(base_hand_size)
        except (TypeError, ValueError):
            base_hand_size = current_hand_size
        # Legacy profiles use 1.0 as the uncalibrated placeholder. A measured
        # wrist-to-knuckle distance uses normalized coordinates and is < 1.
        if not math.isfinite(base_hand_size) or not 0.0 < base_hand_size < 1.0:
            base_hand_size = current_hand_size
        scale_factor = min(4.0, max(0.25, base_hand_size / current_hand_size))

        # Delegate to robust state machine event engine
        self.engine.process(
            stable_gesture=stable_gesture,
            raw_gesture=raw_gesture,
            index_x=index_x,
            index_y=index_y,
            frame_w=frame_w,
            frame_h=frame_h,
            lms_list=lms_list,
            scale_factor=scale_factor
        )

    def release_all(self):
        """Release all actions and reset engine state."""
        self.mouse.release_all()
        if hasattr(self, "engine"):
            self.engine.reset()
