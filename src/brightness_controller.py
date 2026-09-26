import ctypes
from ctypes import wintypes
import math
import time
from .logger import logger
from .models import ActionResult


class PhysicalMonitor(ctypes.Structure):
    _fields_ = [('handle', wintypes.HANDLE),
                ('description', wintypes.WCHAR * 128)]


class BrightnessController:
    """Set monitor brightness via DXVA2 (external monitors) with
    screen-brightness-control fallback (internal laptop panels)."""

    def __init__(self):
        self.current = 50.0
        self.last_applied: int | None = None
        self.last_api_call = float("-inf")
        self.api_rate_limit = 0.1  # Max 10 calls/s

        # Binding a DLL does not establish that a display supports DDC/CI.
        # Check the monitor's actual brightness range when applying a request.
        self._backend = "sbc"
        try:
            self.user32 = ctypes.windll.user32
            self.dxva2 = ctypes.windll.dxva2
            monitor_pointer = ctypes.POINTER(PhysicalMonitor)
            dword_pointer = ctypes.POINTER(wintypes.DWORD)
            # HANDLE/HMONITOR are pointer sized on 64-bit Windows. ctypes'
            # default integer return type would truncate MonitorFromWindow.
            self.user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            self.user32.MonitorFromWindow.restype = wintypes.HANDLE
            for name, arguments in (
                ("GetNumberOfPhysicalMonitorsFromHMONITOR", [wintypes.HANDLE, dword_pointer]),
                ("GetPhysicalMonitorsFromHMONITOR", [wintypes.HANDLE, wintypes.DWORD, monitor_pointer]),
                ("GetMonitorBrightness", [wintypes.HANDLE, dword_pointer, dword_pointer, dword_pointer]),
                ("SetMonitorBrightness", [wintypes.HANDLE, wintypes.DWORD]),
                ("DestroyPhysicalMonitors", [wintypes.DWORD, monitor_pointer]),
            ):
                function = getattr(self.dxva2, name)
                function.argtypes = arguments
                function.restype = wintypes.BOOL
            self._backend = "dxva2"
        except Exception as e:
            logger.warning(f"DXVA2 brightness unavailable: {e}")
            self.user32 = None
            self.dxva2 = None

    def _set_brightness_dxva2(self, level: int) -> None:
        monitor = self.user32.MonitorFromWindow(None, 1)  # Primary display
        if not monitor:
            raise RuntimeError("Primary monitor was not found")
        count = wintypes.DWORD()
        if not self.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(monitor, ctypes.byref(count)):
            raise RuntimeError("Physical monitor enumeration failed")
        if count.value == 0:
            raise RuntimeError("No physical monitors support brightness control")
        monitors = (PhysicalMonitor * count.value)()
        if not self.dxva2.GetPhysicalMonitorsFromHMONITOR(monitor, count.value, monitors):
            raise RuntimeError("Physical monitor handles could not be opened")
        try:
            for physical in monitors:
                minimum, current, maximum = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
                if not self.dxva2.GetMonitorBrightness(
                    physical.handle, ctypes.byref(minimum), ctypes.byref(current), ctypes.byref(maximum)
                ):
                    raise RuntimeError("Display does not support DDC/CI brightness control")
                if maximum.value <= minimum.value:
                    raise RuntimeError("Display reported an invalid brightness range")
                native_level = round(minimum.value + (maximum.value - minimum.value) * level / 100)
                if not self.dxva2.SetMonitorBrightness(physical.handle, native_level):
                    raise RuntimeError("Display rejected the brightness update")
        finally:
            if not self.dxva2.DestroyPhysicalMonitors(count.value, monitors):
                raise RuntimeError("Physical monitor handles could not be released")

    def _set_brightness_sbc(self, level: int) -> None:
        import screen_brightness_control as sbc
        sbc.set_brightness(level)

    def _set_brightness_api(self, level: int) -> ActionResult:
        now = time.perf_counter()
        if now - self.last_api_call < self.api_rate_limit:
            return ActionResult(False, "brightness", "Brightness update pending", None, now)
        self.last_api_call = now
        native_error = None
        if self._backend == "dxva2":
            try:
                self._set_brightness_dxva2(level)
                return ActionResult(True, "brightness", f"Brightness: {level}%", None, now)
            except Exception as error:
                native_error = str(error)
                logger.debug(f"DXVA2 brightness failed; trying fallback: {error}")
        try:
            self._set_brightness_sbc(level)
            self._backend = "sbc"
            return ActionResult(True, "brightness", f"Brightness: {level}%", None, now)
        except Exception as error:
            fallback_error = str(error) or type(error).__name__
            details = f"{native_error}; fallback: {fallback_error}" if native_error else fallback_error
            logger.debug(f"Brightness update failed: {details}")
            return ActionResult(False, "brightness", "Display does not support brightness control or is unavailable",
                                details, now)

    def set_brightness_from_y(self, normalized_y: float) -> ActionResult:
        """Map Y to a smoothed percentage and report only successful updates."""
        try:
            if isinstance(normalized_y, bool):
                raise ValueError("Brightness position must be a finite number")
            normalized_y = float(normalized_y)
            if not math.isfinite(normalized_y):
                raise ValueError("Brightness position must be a finite number")
        except (TypeError, ValueError, OverflowError) as error:
            return ActionResult(False, "brightness", "Invalid brightness position", str(error), time.perf_counter())
        y_clamped = max(0.2, min(0.8, normalized_y))
        target_brightness = ((0.8 - y_clamped) / 0.6) * 100.0
        self.current = self.current + (target_brightness - self.current) * 0.2
        brightness = max(0, min(100, int(self.current)))
        if brightness == self.last_applied:
            return ActionResult(True, "brightness", f"Brightness: {brightness}%", None, time.perf_counter())
        result = self._set_brightness_api(brightness)
        if result.success:
            self.last_applied = brightness
        return result
