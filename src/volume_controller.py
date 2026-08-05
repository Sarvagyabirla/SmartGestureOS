import math
import keyboard
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from .utils import get_distance
import time

class VolumeController:
    def __init__(self):
        self.last_action_time = 0
        try:
            devices = AudioUtilities.GetSpeakers()
            self.volume = devices.EndpointVolume
            
            vol_range = self.volume.GetVolumeRange()
            self.min_vol = vol_range[0]
            self.max_vol = vol_range[1]
        except Exception as e:
            from .logger import logger
            logger.warning(f"Could not initialize volume controller: {e}")
            self.volume = None
            self.min_vol = -65.25
            self.max_vol = 0.0
        
    def set_volume_by_distance(self, d_thumb_index, min_dist=30, max_dist=250):
        if not self.volume:
            return 0
            
        vol_perc = (d_thumb_index - min_dist) / (max_dist - min_dist)
        vol_perc = max(0.0, min(1.0, vol_perc))
        
        target_vol = self.min_vol + vol_perc * (self.max_vol - self.min_vol)
        
        # Smooth lerping
        if not hasattr(self, 'current_vol'):
            self.current_vol = target_vol
        self.current_vol = self.current_vol + (target_vol - self.current_vol) * 0.2
        
        try:
            self.volume.SetMasterVolumeLevel(self.current_vol, None)
        except Exception as e:
            from .logger import logger
            logger.error(f"Failed to set volume: {e}")
        return int(vol_perc * 100)

    def _action(self, key, cooldown=0.3):
        if time.time() - self.last_action_time > cooldown:
            keyboard.send(key)
            self.last_action_time = time.time()

    def volume_up(self):
        self._action("volume up")
        
    def volume_down(self):
        self._action("volume down")
