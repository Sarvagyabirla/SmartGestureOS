"""
pointer_path — primitives for the FAST POINTER PATH.

Why this module exists
----------------------
The cursor is a *continuous* control. It must not depend on the temporal
confirmation machinery used by *discrete* actions (classifier history, hold
timers, screenshots, TTS, app launches). The previous pipeline was:

    Camera -> MediaPipe -> classifier -> GestureMapper -> MouseController
           -> EventEngine -> VirtualMouse

so a single transient classification change stopped cursor updates
entirely. This module supplies the two pieces the fast path needs.

PointerIntent
    Pointer-intent hysteresis.
    * ENTER   — raw Pointing seen on a very small number of consecutive
                samples, or a stable Pointing already active.
    * KEEP    — one noisy frame that degrades the raw label to "Unknown"
                (or "None" when MediaPipe briefly reports no hand) keeps
                the pointer alive for a bounded grace interval, but only
                while no conflicting gesture is present.
    * EXIT    — immediately on any conflicting gesture, mode change,
                automation pause, real hand loss, camera loss or a
                tracking reset.

    Stale landmarks are never used beyond the grace interval: the caller
    supplies the geometry and PointerIntent only answers "should the
    cursor still be under gesture control right now?".

RateMeter / LatencyMeter
    Measured cadence. The camera is ~30 FPS, so every fresh valid detector
    result is a pointer opportunity. These meters report the *real* rates
    instead of a fabricated 60 FPS.

Deliberately absent: a moving-average buffer. A window of past samples adds
latency proportional to its length, which is exactly the defect the fast
path is built to remove. Jitter suppression is the One Euro filter's job.
"""

import time
from collections import deque

#: The only raw label that carries pointer intent.
POINTING = "Pointing"

#: Raw labels with no pointer intent and no conflict. A single noisy
#: MediaPipe frame lands here; neither label may stop the cursor.
NEUTRAL_RAW = frozenset({"", "None", "Unknown", "none", "unknown"})

#: Gestures that must end pointer control on the frame they appear.
#: Any label that is neither POINTING nor neutral is treated as conflicting,
#: so custom/trained gestures are covered by default; this set exists for
#: diagnostics and for the stable-gesture cross-check during a grace window.
CONFLICTING_RAW = frozenset({
    "Pinch",
    "Two Fingers", "Victory", "Crossed Fingers",
    "Three Fingers", "Four Fingers", "Middle Finger",
    "Open Palm", "Closed Fist",
    "Rock On", "Call Me",
    "Thumb Up", "Thumb Down",
})

#: Bounds for the grace interval. 80-120 ms covers one dropped inference at
#: ~30 FPS without ever holding a stale pointer through a real hand loss.
GRACE_MS_MIN = 80.0
GRACE_MS_MAX = 120.0


class PointerIntent:
    """Bounded pointer-intent hysteresis for the GENERAL-mode cursor.

    This object owns no geometry and no timing beyond the grace interval; it
    is a pure "is pointer control active?" oracle, so it can be unit-tested
    and reasoned about in isolation from the classifier.
    """

    def __init__(self, enter_samples: int = 2, grace_ms: float = 100.0,
                 clock=time.perf_counter):
        self._clock = clock
        self._enter_samples = max(1, int(enter_samples))
        self._grace_ms = min(GRACE_MS_MAX, max(GRACE_MS_MIN, float(grace_ms)))
        self._grace_s = self._grace_ms / 1000.0
        self._active = False
        self._pointing_samples = 0
        self._last_pointing_at = 0.0
        self._state = "inactive"

    # ── configuration ──────────────────────────────────────────────────────

    @property
    def enter_samples(self) -> int:
        return self._enter_samples

    @property
    def grace_ms(self) -> float:
        return self._grace_ms

    def apply_settings(self, enter_samples=None, grace_ms=None) -> None:
        """Re-tune hysteresis. Applied live by the settings callback."""
        if enter_samples is not None:
            self._enter_samples = max(1, int(enter_samples))
        if grace_ms is not None:
            self._grace_ms = min(GRACE_MS_MAX, max(GRACE_MS_MIN, float(grace_ms)))
            self._grace_s = self._grace_ms / 1000.0

    # ── state ──────────────────────────────────────────────────────────────

    @property
    def active(self) -> bool:
        return self._active

    @property
    def state(self) -> str:
        """One of: inactive, entering, active, grace (diagnostics overlay)."""
        return self._state

    def reset(self) -> None:
        """Full reset — hand loss, camera loss, pause, mode change."""
        self._active = False
        self._pointing_samples = 0
        self._last_pointing_at = 0.0
        self._state = "inactive"

    # ── the oracle ─────────────────────────────────────────────────────────

    def update(self, raw_gesture, stable_gesture=None, now=None) -> bool:
        """Feed one classifier result. True when the cursor should move.

        ``raw_gesture`` drives exit decisions immediately; ``stable_gesture``
        only shortens the *entry* wait, so a settled Pointing is honoured
        immediately without letting the slower history gate the cursor.
        """
        now = self._clock() if now is None else float(now)
        raw = raw_gesture or "None"
        stable = stable_gesture or "None"

        if raw == POINTING:
            self._pointing_samples += 1
            self._last_pointing_at = now
            if not self._active and (stable == POINTING
                                     or self._pointing_samples >= self._enter_samples):
                self._active = True
            if self._active:
                self._state = "active"
                return True
            self._state = "entering"
            return False

        if raw in NEUTRAL_RAW:
            within_grace = (
                self._active
                and (now - self._last_pointing_at) <= self._grace_s
            )
            if within_grace and stable not in CONFLICTING_RAW:
                self._state = "grace"
                return True
            self._active = False
            self._pointing_samples = 0
            self._state = "inactive"
            return False

        # Any other label is a conflicting gesture: exit immediately.
        self._active = False
        self._pointing_samples = 0
        self._state = "inactive"
        return False


class RateMeter:
    """Measured events-per-second over a bounded trailing window.

    Every sample is a real occurrence (a captured frame, a completed
    inference, an issued pointer update). Nothing here extrapolates or
    invents a target frame rate.
    """

    def __init__(self, window: int = 60, clock=time.perf_counter):
        self._clock = clock
        self._samples: deque = deque(maxlen=max(2, int(window)))
        self.total: int = 0

    def add(self, at=None) -> None:
        self._samples.append(self._clock() if at is None else float(at))
        self.total += 1

    def reset(self) -> None:
        self._samples.clear()
        self.total = 0

    @property
    def fps(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        span = self._samples[-1] - self._samples[0]
        if span <= 0.0:
            return 0.0
        return (len(self._samples) - 1) / span

    @property
    def age(self) -> float:
        """Seconds since the most recent sample; ``inf`` when never used."""
        if not self._samples:
            return float("inf")
        return self._clock() - self._samples[-1]


class LatencyMeter:
    """Rolling median/mean latency in milliseconds for diagnostics."""

    def __init__(self, window: int = 90):
        self._samples: deque = deque(maxlen=max(2, int(window)))

    def add_seconds(self, seconds: float) -> None:
        self._samples.append(float(seconds) * 1000.0)

    def add_ms(self, milliseconds: float) -> None:
        self._samples.append(float(milliseconds))

    def reset(self) -> None:
        self._samples.clear()

    @property
    def count(self) -> int:
        return len(self._samples)

    @property
    def mean_ms(self) -> float:
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples)

    @property
    def median_ms(self) -> float:
        if not self._samples:
            return 0.0
        ordered = sorted(self._samples)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2.0


class PointerMetrics:
    """Cadence and latency counters for the pointer path.

    ``pointer_fps`` is measured from real issued cursor updates; the camera
    is ~30 FPS, so the expected ceiling is the detector rate, not 60.
    ``capture_to_pointer_ms`` is the full user-visible delay: camera capture
    timestamp -> cursor update issued.
    """

    def __init__(self, window: int = 60, clock=time.perf_counter):
        self._clock = clock
        self.updates = RateMeter(window=window, clock=clock)
        self.suppressed = 0
        self.samples = 0
        self.capture_to_pointer = LatencyMeter(window=window)
        self.inference = LatencyMeter(window=window)

    def record_update(self, capture_at=None) -> None:
        """One pointer update actually issued to Windows."""
        now = self._clock()
        self.samples += 1
        self.updates.add(now)
        if capture_at is not None:
            self.capture_to_pointer.add_seconds(max(0.0, now - capture_at))

    def record_suppressed(self) -> None:
        """A live pointer sample the dead zone swallowed (still-hand noise)."""
        self.suppressed += 1

    def reset(self) -> None:
        self.updates.reset()
        self.capture_to_pointer.reset()
        self.samples = 0
        self.suppressed = 0

    @property
    def pointer_fps(self) -> float:
        return self.updates.fps

    def as_dict(self) -> dict:
        return {
            "pointer_fps": self.pointer_fps,
            "pointer_samples": self.samples,
            "pointer_suppressed": self.suppressed,
            "capture_to_pointer_ms": self.capture_to_pointer.median_ms,
            "inference_median_ms": self.inference.median_ms,
            "inference_mean_ms": self.inference.mean_ms,
        }
