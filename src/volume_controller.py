import math
import time
import keyboard
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from .utils import get_distance
from .logger import logger


class VolumeController:
    def __init__(self):
        # F-18 FIX: use perf_counter for monotonic rate-limiting
        self._last_action_time = 0.0
        self._rate_limit = 0.05  # 50 ms minimum between steps
        try:
            devices = AudioUtilities.GetSpeakers()
            self.volume = devices.EndpointVolume

            vol_range = self.volume.GetVolumeRange()
            self.min_vol = vol_range[0]
            self.max_vol = vol_range[1]
            logger.info("VolumeController initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize volume controller: {e}. Volume control disabled.")
            self.volume = None
            self.min_vol = -65.25
            self.max_vol = 0.0

    def set_volume_by_distance(self, d_thumb_index, min_dist=30, max_dist=250):
        if not self.volume:
            return 0

        vol_perc = (d_thumb_index - min_dist) / (max_dist - min_dist)
        vol_perc = max(0.0, min(1.0, vol_perc))

        target_vol = self.min_vol + vol_perc * (self.max_vol - self.min_vol)

        # Exponential moving average for smooth lerping
        if not hasattr(self, "_current_vol"):
            self._current_vol = target_vol
        self._current_vol = self._current_vol + (target_vol - self._current_vol) * 0.2

        try:
            self.volume.SetMasterVolumeLevel(self._current_vol, None)
        except Exception as e:
            logger.error(f"Failed to set volume by distance: {e}")
        return int(vol_perc * 100)

    def volume_up(self):
        now = time.perf_counter()  # F-18 FIX
        if now - self._last_action_time < self._rate_limit:
            return
        if self.volume:
            try:
                vol = self.volume.GetMasterVolumeLevelScalar()
                self.volume.SetMasterVolumeLevelScalar(min(1.0, vol + 0.02), None)
            except Exception as e:
                logger.error(f"Failed to increase volume: {e}")
        self._last_action_time = now

    def volume_down(self):
        now = time.perf_counter()  # F-18 FIX
        if now - self._last_action_time < self._rate_limit:
            return
        if self.volume:
            try:
                vol = self.volume.GetMasterVolumeLevelScalar()
                self.volume.SetMasterVolumeLevelScalar(max(0.0, vol - 0.02), None)
            except Exception as e:
                logger.error(f"Failed to decrease volume: {e}")
        self._last_action_time = now
