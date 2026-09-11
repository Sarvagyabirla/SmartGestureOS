import ctypes
from ctypes import wintypes
from .logger import logger

class PhysicalMonitor(ctypes.Structure):
    _fields_ = [('handle', wintypes.HANDLE),
                ('description', wintypes.WCHAR * 128)]

class BrightnessController:
    def __init__(self):
        self.current = 50
        self.last_applied = int(self.current)
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

    def set_absolute_brightness(self, target_brightness):
        target_brightness = max(0, min(100, target_brightness))
        self.current = self.current + (target_brightness - self.current) * 0.2
        brightness = int(self.current)
        
        if brightness != self.last_applied:
            self._set_brightness_api(brightness)
            self.last_applied = brightness
        return brightness
