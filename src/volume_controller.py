"""
VolumeController — Windows audio volume control via pycaw.

Every public method returns ActionResult so GestureMapper can
give accurate success/failure feedback.

Rate-limiting uses time.perf_counter() for monotonic behavior.
"""
import time
import math
import threading
from .models import ActionResult
from .logger import logger


class VolumeController:
    def __init__(self):
        # perf_counter for monotonic rate-limiting
        self._last_action_time: float = 0.0
        self._rate_limit: float = 0.05  # 50 ms minimum between steps

        self.volume = None
        self.min_vol: float = -65.25
        self.max_vol: float = 0.0
        self._com_thread: int | None = None

    def initialize(self) -> bool:
        """Acquire the endpoint on the thread that will execute audio actions."""
        return self._try_reacquire()

    def close(self) -> None:
        """Release the endpoint before balancing this thread's COM initialization."""
        if self._com_thread == threading.get_ident():
            import comtypes
            self.volume = None
            self._com_thread = None
            comtypes.CoUninitialize()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _try_reacquire(self) -> bool:
        """Attempt to re-acquire audio endpoint after a failure."""
        try:
            import comtypes
            from pycaw.pycaw import AudioUtilities

            if self._com_thread is None:
                comtypes.CoInitialize()
                self._com_thread = threading.get_ident()
            elif self._com_thread != threading.get_ident():
                logger.error("VolumeController called from a different COM thread.")
                return False

            devices = AudioUtilities.GetSpeakers()
            self.volume = devices.EndpointVolume
            vol_range = self.volume.GetVolumeRange()
            self.min_vol = vol_range[0]
            self.max_vol = vol_range[1]
            logger.info("VolumeController: re-acquired audio endpoint.")
            return True
        except Exception as e:
            logger.error(f"VolumeController: re-acquire failed: {e}")
            self.volume = None
            return False

    def _unavailable(self, action: str) -> ActionResult:
        return ActionResult(
            False, action,
            "Volume control unavailable (no audio endpoint).",
            "self.volume is None",
            time.perf_counter(),
        )

    # ── Continuous control ─────────────────────────────────────────────────────

    def set_volume_by_distance(self, d_thumb_index: float,
                                min_dist: float = 30,
                                max_dist: float = 250) -> int:
        """Continuous gesture control — returns 0-100 int or 0 on failure."""
        if not all(math.isfinite(value) for value in (d_thumb_index, min_dist, max_dist)) or max_dist <= min_dist:
            return 0
        if not self.volume and not self._try_reacquire():
            return 0

        vol_perc = (d_thumb_index - min_dist) / (max_dist - min_dist)
        vol_perc = max(0.0, min(1.0, vol_perc))
        target_vol = self.min_vol + vol_perc * (self.max_vol - self.min_vol)

        if not hasattr(self, "_current_vol"):
            self._current_vol = target_vol
        self._current_vol = self._current_vol + (target_vol - self._current_vol) * 0.2

        try:
            self.volume.SetMasterVolumeLevel(self._current_vol, None)
        except Exception as e:
            logger.error(f"Failed to set volume by distance: {e}")
            if self._try_reacquire():
                try:
                    self.volume.SetMasterVolumeLevel(self._current_vol, None)
                except Exception:
                    return 0
            else:
                return 0
        return int(vol_perc * 100)

    # ── Discrete actions (each returns ActionResult) ───────────────────────────

    def volume_up(self) -> ActionResult:
        now = time.perf_counter()
        if now - self._last_action_time < self._rate_limit:
            return ActionResult(False, "volume_up", "Rate-limited", None, now)

        if not self.volume:
            result = self._unavailable("volume_up")
            # Try once to re-acquire
            if self._try_reacquire():
                return self.volume_up()
            return result

        try:
            vol = self.volume.GetMasterVolumeLevelScalar()
            self.volume.SetMasterVolumeLevelScalar(min(1.0, vol + 0.02), None)
            self._last_action_time = now
            return ActionResult(True, "volume_up", f"Volume: {int(min(1.0, vol + 0.02) * 100)}%", None, now)
        except Exception as e:
            logger.error(f"VolumeController.volume_up failed: {e}")
            self.volume = None  # force re-acquire next call
            return ActionResult(False, "volume_up", "API call failed", str(e), now)

    def volume_down(self) -> ActionResult:
        now = time.perf_counter()
        if now - self._last_action_time < self._rate_limit:
            return ActionResult(False, "volume_down", "Rate-limited", None, now)

        if not self.volume:
            result = self._unavailable("volume_down")
            if self._try_reacquire():
                return self.volume_down()
            return result

        try:
            vol = self.volume.GetMasterVolumeLevelScalar()
            self.volume.SetMasterVolumeLevelScalar(max(0.0, vol - 0.02), None)
            self._last_action_time = now
            return ActionResult(True, "volume_down", f"Volume: {int(max(0.0, vol - 0.02) * 100)}%", None, now)
        except Exception as e:
            logger.error(f"VolumeController.volume_down failed: {e}")
            self.volume = None
            return ActionResult(False, "volume_down", "API call failed", str(e), now)
