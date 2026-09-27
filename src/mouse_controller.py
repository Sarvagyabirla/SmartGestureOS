"""
MouseController — owns the pointer and the discrete input state machine.

Two logically separate paths live here, and the separation is the whole point
of the P0 cursor-fluency fix:

    LANDMARKS
       |-- FAST POINTER PATH  (process_pointer)
       |     index fingertip -> mapping -> One Euro -> cursor
       |     runs on EVERY fresh valid inference result while pointer intent
       |     is active. No classifier history, no hold timer, no screenshot,
       |     no TTS and no app launch can stall it.
       |
       +-- GESTURE / ACTION PATH  (process_landmarks -> EventEngine)
             classifier -> stabilization -> hold/cooldown -> click/system action

The EventEngine deliberately no longer moves the cursor for navigation. It
still owns the cursor while DRAGGING, because a held left button *is* the
click state and releasing it is a safety concern, not a pointer concern.
"""

import math
import time
from .virtual_mouse import VirtualMouse
from .utils import get_distance
from .logger import logger
from .pointer_path import PointerIntent, PointerMetrics

_DEFAULT_SENSITIVITY = 0.85
_DEFAULT_SMOOTHING = 1

# Pointer tuning, derived from the measured ~30 FPS detector cadence.
#
# At a 30 Hz sample interval the One Euro smoothing factor is
#     a = 2*pi*cutoff*dt / (1 + 2*pi*cutoff*dt)
# and the group delay of the resulting first-order low pass is ~1/(2*pi*cutoff):
#
#   cutoff  0.55 Hz -> a = 0.10 -> 0.29 s delay  (deliberate, "smooth" end)
#   cutoff  1.92 Hz -> a = 0.29 -> 0.08 s delay  (default smoothing = 2)
#   cutoff 12.0  Hz -> a = 0.71 -> 0.013 s delay  (feels immediate)
#
# ``beta`` couples cutoff to fingertip speed in SCREEN PIXELS PER SECOND, so a
# single coefficient spans the useful range: with beta = 0.079 the cutoff
# crosses 12 Hz at ~125 px/s, which means anything faster than a slow drift is
# effectively unfiltered (fast motion gets less smoothing) while a nearly
# still hand sits at the low cutoff (jitter gets heavy suppression).
#
# The previous production values were min_cutoff 3.85 Hz / beta 0.35. That
# cutoff was high enough to pass jitter straight through, while the beta was
# far too small to raise it during motion — so the cursor was laggy and
# jittery at the same time.
_CUTOFF_RESPONSIVE = 2.0
_CUTOFF_SMOOTHEST = 0.55
_BETA_BASE = 0.015
_BETA_SPAN = 0.075

class MouseController:
    def __init__(self):
        from config import SETTINGS
        gestures = SETTINGS.get("gestures", {})
        sensitivity = float(gestures.get("sensitivity", _DEFAULT_SENSITIVITY))
        smoothing = int(gestures.get("smoothing", _DEFAULT_SMOOTHING))
        beta = self._sensitivity_beta(sensitivity)
        min_cutoff = self._smoothing_cutoff(smoothing)

        self._pointer_intent = PointerIntent(
            enter_samples=int(gestures.get("pointer_enter_samples", 2)),
            grace_ms=float(gestures.get("pointer_grace_ms", 100)),
        )
        self.metrics = PointerMetrics()
        self.mouse = VirtualMouse(min_cutoff=min_cutoff, beta=beta, deadzone=1.0)
        from .event_engine import EventEngine
        self.engine = EventEngine(self)

        from src.settings_manager import settings_manager
        settings_manager.register_callback(self.on_settings_changed)
        self.on_settings_changed()

    # ── pointer tuning ─────────────────────────────────────────────────────

    @staticmethod
    def _smoothing_cutoff(smoothing: int) -> float:
        """Map the UI slider (1 = responsive, 20 = smooth) to One Euro cutoff.

        The slider still reads as "1 = responsive, 20 = smooth" for users, but
        the whole range now sits in the responsive band instead of 4.0-1.2 Hz,
        which imposed a >= 40 ms group delay on every single update.
        """
        smoothing = max(1, min(20, int(smoothing)))
        span = _CUTOFF_RESPONSIVE - _CUTOFF_SMOOTHEST
        return _CUTOFF_RESPONSIVE - ((smoothing - 1) / 19.0) * span

    @staticmethod
    def _sensitivity_beta(sensitivity: float) -> float:
        """Map 0.1-1.0 sensitivity to the speed-coupling term, in screen px/s."""
        sensitivity = max(0.0, min(1.0, float(sensitivity)))
        return _BETA_BASE + _BETA_SPAN * sensitivity

    @staticmethod
    def _sensitivity_deadzone(sensitivity: float) -> float:
        """Small dead zone only. One Euro already removes jitter; this just
        stops redundant SetCursorPos calls for a perfectly still hand."""
        sensitivity = max(0.0, min(1.0, float(sensitivity)))
        return max(0.0, (1.0 - sensitivity) * 0.8)

    # ── lazily-created collaborators ───────────────────────────────────────
    # Partially constructed controllers (tests build these with __new__) must
    # stay usable, so both of these materialise on first use instead of
    # requiring __init__ to have run.

    @property
    def pointer_intent(self) -> PointerIntent:
        intent = self.__dict__.get("_pointer_intent")
        if intent is None:
            intent = PointerIntent()
            self.__dict__["_pointer_intent"] = intent
        return intent

    @property
    def pointer_metrics(self) -> PointerMetrics:
        metrics = self.__dict__.get("metrics")
        if metrics is None:
            metrics = PointerMetrics()
            self.__dict__["metrics"] = metrics
        return metrics

    def on_settings_changed(self):
        from config import SETTINGS
        gestures = SETTINGS.get("gestures", {})
        sensitivity = float(gestures.get("sensitivity", _DEFAULT_SENSITIVITY))
        smoothing = int(gestures.get("smoothing", _DEFAULT_SMOOTHING))
        beta = self._sensitivity_beta(sensitivity)
        min_cutoff = self._smoothing_cutoff(smoothing)
        # tune() reaches already-created One Euro filters as well as future ones.
        self.mouse.smoother.tune(min_cutoff, beta)
        self.mouse.deadzone = self._sensitivity_deadzone(sensitivity)
        self.pointer_intent.apply_settings(
            enter_samples=gestures.get("pointer_enter_samples"),
            grace_ms=gestures.get("pointer_grace_ms"),
        )
        self.effective_pointer_settings = {
            "sensitivity": sensitivity,
            "smoothing": smoothing,
            "min_cutoff_hz": min_cutoff,
            "beta": beta,
            "deadzone_px": self.mouse.deadzone,
            "enter_samples": self.pointer_intent.enter_samples,
            "grace_ms": self.pointer_intent.grace_ms,
            "profile": SETTINGS.get("profile_name", "?"),
        }
        logger.info(
            "Pointer tuning (profile=%s): sensitivity=%.2f smoothing=%d -> "
            "min_cutoff=%.3f Hz beta=%.4f deadzone=%.2f px enter_samples=%d grace=%.0f ms",
            self.effective_pointer_settings["profile"], sensitivity, smoothing,
            min_cutoff, beta, self.mouse.deadzone,
            self.pointer_intent.enter_samples, self.pointer_intent.grace_ms,
        )

    # ── scale factor ───────────────────────────────────────────────────────

    def _scale_factor(self, lms_list) -> float | None:
        """Wrist-to-knuckle distance ratio, or None when unusable."""
        import numpy as np
        wrist = np.array([lms_list[0].x, lms_list[0].y, lms_list[0].z])
        middle_mcp = np.array([lms_list[9].x, lms_list[9].y, lms_list[9].z])
        current_hand_size = float(np.linalg.norm(wrist - middle_mcp))
        if not math.isfinite(current_hand_size):
            return None
        current_hand_size = max(0.01, current_hand_size)
        from config import SETTINGS
        base_hand_size = SETTINGS.get("gestures", {}).get("base_hand_size", current_hand_size)
        try:
            base_hand_size = float(base_hand_size)
        except (TypeError, ValueError):
            base_hand_size = current_hand_size
        # Legacy profiles use 1.0 as the uncalibrated placeholder. A measured
        # wrist-to-knuckle distance uses normalized coordinates and is < 1.
        if not math.isfinite(base_hand_size) or not 0.0 < base_hand_size < 1.0:
            base_hand_size = current_hand_size
        return min(4.0, max(0.25, base_hand_size / current_hand_size))

    # ── FAST POINTER PATH ──────────────────────────────────────────────────

    def process_pointer(self, lms_list, raw_gesture, stable_gesture, frame_w,
                        frame_h, now=None, capture_at=None):
        """Move the cursor from fresh index-fingertip geometry. Returns moved.

        Call this on EVERY fresh valid inference result while pointer intent is
        active. It deliberately does not consult the stable-gesture history, a
        hold timer, the screenshot path, TTS or app-launch bookkeeping.
        """
        if not lms_list or len(lms_list) < 21:
            self.pointer_intent.reset()
            return False

        index_x = getattr(lms_list[8], "pixel_x", None)
        index_y = getattr(lms_list[8], "pixel_y", None)
        if not (isinstance(index_x, int) and isinstance(index_y, int)):
            self.pointer_intent.reset()
            return False

        if not self.pointer_intent.update(raw_gesture, stable_gesture, now=now):
            # A conflicting gesture ended pointer control cleanly. Drop the
            # filtered trail so the next session does not drag stale motion.
            self.mouse.reset_pointer_filter()
            return False

        moved = bool(self.mouse.move(index_x, index_y, frame_w, frame_h))
        if moved:
            self.pointer_metrics.record_update(capture_at)
        else:
            self.pointer_metrics.record_suppressed()
        return moved

    def release_pointer(self):
        """End pointer control without emitting any Windows mouse event."""
        self.pointer_intent.reset()
        self.mouse.reset_pointer_filter()

    # ── GESTURE / ACTION PATH ──────────────────────────────────────────────

    def process_landmarks(self, lms_list, stable_gesture, raw_gesture, frame_w, frame_h,
                          now=None, capture_at=None):
        if not lms_list or len(lms_list) < 21:
            self.release_all()
            return

        scale_factor = self._scale_factor(lms_list)
        if scale_factor is None:
            self.release_all()
            return

        # Pointer first and unconditionally: cursor responsiveness must not
        # depend on the discrete-action path completing.
        self.process_pointer(
            lms_list, raw_gesture, stable_gesture, frame_w, frame_h,
            now=now, capture_at=capture_at,
        )

        # Delegate discrete input (click/drag/scroll/right-click) to the
        # state machine. It no longer drives cursor navigation.
        self.engine.process(
            stable_gesture=stable_gesture,
            raw_gesture=raw_gesture,
            index_x=lms_list[8].pixel_x,
            index_y=lms_list[8].pixel_y,
            frame_w=frame_w,
            frame_h=frame_h,
            lms_list=lms_list,
            scale_factor=scale_factor
        )

    def release_all(self):
        """Release all actions and reset engine and pointer state."""
        self.pointer_intent.reset()
        self.mouse.release_all()
        if hasattr(self, "engine"):
            self.engine.reset()
