import ctypes
from ctypes import wintypes
import time
from .logger import logger

class PhysicalMonitor(ctypes.Structure):
    _fields_ = [('handle', wintypes.HANDLE),
                ('description', wintypes.WCHAR * 128)]

class BrightnessController:
    def __init__(self):
        self.current = 50.0
        self.last_applied = int(self.current)
        self.last_api_call = 0.0
        self.api_rate_limit = 0.1 # Max 10 calls per second
        
        try:
            self.user32 = ctypes.windll.user32
            self.dxva2 = ctypes.windll.dxva2
        except Exception as e:
            logger.error(f"Failed to load user32/dxva2: {e}")
            self.user32 = None
            self.dxva2 = None
        
    def _set_brightness_api(self, level):
        if not self.user32 or not self.dxva2:
            return
            
        now = time.perf_counter()
        if now - self.last_api_call < self.api_rate_limit:
            return
        self.last_api_call = now
            
        try:
            # 2 = MONITOR_DEFAULTTONEAREST
            monitor = self.user32.MonitorFromWindow(0, 2) 
            num_monitors = wintypes.DWORD()
            if self.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(monitor, ctypes.byref(num_monitors)):
                physical_monitors = (PhysicalMonitor * num_monitors.value)()
                if self.dxva2.GetPhysicalMonitorsFromHMONITOR(monitor, num_monitors.value, physical_monitors):
                    for i in range(num_monitors.value):
                        self.dxva2.SetMonitorBrightness(physical_monitors[i].handle, int(level))
                    self.dxva2.DestroyPhysicalMonitors(num_monitors.value, physical_monitors)
        except Exception as e:
            logger.error(f"Failed to set brightness via API: {e}")

    def set_brightness_from_y(self, normalized_y):
        """Map normalized_y (0.0 to 1.0) to brightness (20% to 80% or 0% to 100%)
           where top of screen (0.2) = 100%, bottom (0.8) = 0%.
        """
        # Clamp between 0.2 and 0.8
        y_clamped = max(0.2, min(0.8, normalized_y))
        
        # Invert and scale to 0-100 range
        # y=0.2 -> (0.8 - 0.2)/0.6 = 1.0 -> 100%
        # y=0.8 -> (0.8 - 0.8)/0.6 = 0.0 -> 0%
        target_brightness = ((0.8 - y_clamped) / 0.6) * 100.0
        
        self.current = self.current + (target_brightness - self.current) * 0.2
        brightness = int(self.current)
        
        if brightness != self.last_applied:
            self._set_brightness_api(brightness)
            self.last_applied = brightness
        return brightness
