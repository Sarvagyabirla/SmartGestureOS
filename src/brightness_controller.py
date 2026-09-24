import ctypes
from ctypes import wintypes
import time
from .logger import logger


class PhysicalMonitor(ctypes.Structure):
    _fields_ = [('handle', wintypes.HANDLE),
                ('description', wintypes.WCHAR * 128)]


class BrightnessController:
    """Set monitor brightness via DXVA2 (external monitors) with
    screen-brightness-control fallback (internal laptop panels)."""

    def __init__(self):
        self.current = 50.0
        self.last_applied = int(self.current)
        self.last_api_call = 0.0
        self.api_rate_limit = 0.1  # Max 10 calls/s

        # Detect which backend is available
        self._backend = "none"
        try:
            self.user32 = ctypes.windll.user32
            self.dxva2 = ctypes.windll.dxva2
            # Try a probe call to see if dxva2 is functional
            monitor = self.user32.MonitorFromWindow(0, 2)
            num_monitors = wintypes.DWORD()
            if self.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
                    monitor, ctypes.byref(num_monitors)):
                self._backend = "dxva2"
                logger.info("BrightnessController: DXVA2 backend active.")
            else:
                raise RuntimeError("GetNumberOfPhysicalMonitors returned False")
        except Exception as e:
            logger.warning(f"DXVA2 brightness unavailable: {e}")
            self.user32 = None
            self.dxva2 = None
            try:
                import screen_brightness_control as sbc  # noqa: F401
                self._backend = "sbc"
                logger.info("BrightnessController: screen_brightness_control fallback active.")
            except ImportError:
                logger.warning("BrightnessController: no brightness backend available.")
                self._backend = "none"

    def _set_brightness_dxva2(self, level: int):
        now = time.perf_counter()
        if now - self.last_api_call < self.api_rate_limit:
            return
        self.last_api_call = now
        try:
            monitor = self.user32.MonitorFromWindow(0, 2)
            num_monitors = wintypes.DWORD()
            if self.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
                    monitor, ctypes.byref(num_monitors)):
                physical_monitors = (PhysicalMonitor * num_monitors.value)()
                if self.dxva2.GetPhysicalMonitorsFromHMONITOR(
                        monitor, num_monitors.value, physical_monitors):
                    for i in range(num_monitors.value):
                        self.dxva2.SetMonitorBrightness(
                            physical_monitors[i].handle, int(level))
                    self.dxva2.DestroyPhysicalMonitors(
                        num_monitors.value, physical_monitors)
        except Exception as e:
            logger.error(f"DXVA2 set brightness failed: {e}")

    def _set_brightness_sbc(self, level: int):
        now = time.perf_counter()
        if now - self.last_api_call < self.api_rate_limit:
            return
        self.last_api_call = now
        try:
            import screen_brightness_control as sbc
            sbc.set_brightness(int(level))
        except Exception as e:
            logger.error(f"screen_brightness_control set brightness failed: {e}")

    def _set_brightness_api(self, level: int):
        if self._backend == "dxva2":
            self._set_brightness_dxva2(level)
        elif self._backend == "sbc":
            self._set_brightness_sbc(level)
        # "none" → silently skip

    def set_brightness_from_y(self, normalized_y: float) -> int:
        """Map normalized Y (0–1, top = bright) → brightness 0–100."""
        y_clamped = max(0.2, min(0.8, normalized_y))
        target_brightness = ((0.8 - y_clamped) / 0.6) * 100.0
        self.current = self.current + (target_brightness - self.current) * 0.2
        brightness = int(self.current)
        if brightness != self.last_applied:
            self._set_brightness_api(brightness)
            self.last_applied = brightness
        return brightness
