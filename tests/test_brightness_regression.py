"""Brightness APIs are always fake; these checks never adjust a real display."""

import ctypes
import sys
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import src.brightness_controller as brightness_module
from src.models import ActionResult


@pytest.fixture
def brightness(monkeypatch):
    logical_handle = 0x100000001
    physical_handle = 0x100000002
    user32 = SimpleNamespace(MonitorFromWindow=MagicMock(return_value=logical_handle))
    dxva2 = SimpleNamespace(**{name: MagicMock(return_value=True) for name in (
        "GetNumberOfPhysicalMonitorsFromHMONITOR", "GetPhysicalMonitorsFromHMONITOR",
        "GetMonitorBrightness", "SetMonitorBrightness", "DestroyPhysicalMonitors",
    )})

    def count(monitor, output):
        output._obj.value = 1
        return True

    def enumerate_monitors(monitor, number, output):
        output[0].handle = physical_handle
        return True

    def get_brightness(monitor, minimum, current, maximum):
        minimum._obj.value = 10
        current._obj.value = 110
        maximum._obj.value = 210
        return True

    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.side_effect = count
    dxva2.GetPhysicalMonitorsFromHMONITOR.side_effect = enumerate_monitors
    dxva2.GetMonitorBrightness.side_effect = get_brightness
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32, dxva2=dxva2))
    sbc = SimpleNamespace(set_brightness=MagicMock())
    monkeypatch.setitem(sys.modules, "screen_brightness_control", sbc)
    clock = SimpleNamespace(now=10.0)
    monkeypatch.setattr(brightness_module, "time", SimpleNamespace(perf_counter=lambda: clock.now))
    controller = brightness_module.BrightnessController()
    return SimpleNamespace(controller=controller, dxva2=dxva2, user32=user32, sbc=sbc,
                           clock=clock, physical_handle=physical_handle,
                           logical_handle=logical_handle)


def test_native_percent_is_scaled_and_large_handles_preserved(brightness):
    result = brightness.controller.set_brightness_from_y(0.2)

    assert isinstance(result, ActionResult)
    assert result.success is True
    assert result.message == "Brightness: 60%"
    assert brightness.controller.last_applied == 60
    assert brightness.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.call_args.args[0] == brightness.logical_handle
    brightness.dxva2.SetMonitorBrightness.assert_called_once_with(brightness.physical_handle, 130)
    brightness.dxva2.DestroyPhysicalMonitors.assert_called_once()
    brightness.sbc.set_brightness.assert_not_called()


def test_win32_monitor_functions_declare_pointer_sized_handles(brightness):
    assert brightness.user32.MonitorFromWindow.restype is wintypes.HANDLE
    assert brightness.user32.MonitorFromWindow.argtypes == [wintypes.HWND, wintypes.DWORD]
    assert brightness.dxva2.GetMonitorBrightness.argtypes == [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    assert brightness.dxva2.SetMonitorBrightness.argtypes == [wintypes.HANDLE, wintypes.DWORD]
    assert brightness.dxva2.GetPhysicalMonitorsFromHMONITOR.restype is wintypes.BOOL
    assert brightness.dxva2.DestroyPhysicalMonitors.restype is wintypes.BOOL


def test_initial_stationary_gesture_sends_real_request_before_reporting_success(brightness):
    result = brightness.controller.set_brightness_from_y(0.5)

    assert result.success is True
    assert brightness.controller.last_applied == 50
    brightness.dxva2.SetMonitorBrightness.assert_called_once()


def test_rate_limit_does_not_record_unsent_brightness_and_allows_later_retry(brightness):
    controller = brightness.controller
    assert controller.set_brightness_from_y(0.2).success is True
    brightness.clock.now += 0.01

    pending = controller.set_brightness_from_y(0.2)

    assert pending.success is False
    assert pending.error is None
    assert pending.message == "Brightness update pending"
    assert controller.last_applied == 60
    brightness.dxva2.SetMonitorBrightness.assert_called_once()

    brightness.clock.now += 0.11
    assert controller.set_brightness_from_y(0.2).success is True
    assert controller.last_applied > 60
    assert brightness.dxva2.SetMonitorBrightness.call_count == 2


@pytest.mark.parametrize("failure", ["unsupported", "set_false", "set_exception", "bad_range"])
def test_ddc_failure_releases_handles_and_uses_laptop_fallback(brightness, failure):
    if failure == "unsupported":
        brightness.dxva2.GetMonitorBrightness.side_effect = None
        brightness.dxva2.GetMonitorBrightness.return_value = False
    elif failure == "bad_range":
        def invalid_range(monitor, minimum, current, maximum):
            minimum._obj.value = 10
            maximum._obj.value = 10
            return True
        brightness.dxva2.GetMonitorBrightness.side_effect = invalid_range
    elif failure == "set_false":
        brightness.dxva2.SetMonitorBrightness.return_value = False
    else:
        brightness.dxva2.SetMonitorBrightness.side_effect = OSError("DDC disconnected")

    result = brightness.controller.set_brightness_from_y(0.2)

    assert result.success is True
    assert brightness.controller.last_applied == 60
    brightness.dxva2.DestroyPhysicalMonitors.assert_called_once()
    brightness.sbc.set_brightness.assert_called_once_with(60)
    assert brightness.controller._backend == "sbc"


def test_both_backends_fail_without_recording_success_and_retry_can_recover(brightness):
    brightness.dxva2.SetMonitorBrightness.return_value = False
    brightness.sbc.set_brightness.side_effect = OSError("No supported displays")

    result = brightness.controller.set_brightness_from_y(0.2)

    assert result.success is False
    assert "No supported displays" in result.error
    assert brightness.controller.last_applied is None
    brightness.dxva2.DestroyPhysicalMonitors.assert_called_once()

    brightness.sbc.set_brightness.side_effect = None
    brightness.clock.now += 0.11
    assert brightness.controller.set_brightness_from_y(0.2).success is True
    assert brightness.controller.last_applied is not None


@pytest.mark.parametrize("empty", [True, False])
def test_missing_physical_monitor_falls_back_without_destroying_unowned_handles(brightness, empty):
    def no_monitors(monitor, number):
        number._obj.value = 0
        return empty
    brightness.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.side_effect = no_monitors

    assert brightness.controller.set_brightness_from_y(0.2).success is True

    brightness.sbc.set_brightness.assert_called_once_with(60)
    brightness.dxva2.GetPhysicalMonitorsFromHMONITOR.assert_not_called()
    brightness.dxva2.DestroyPhysicalMonitors.assert_not_called()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), None, "bad", True])
def test_invalid_coordinates_do_not_touch_backends_or_smoothing(brightness, value):
    result = brightness.controller.set_brightness_from_y(value)

    assert result.success is False
    assert result.error
    assert brightness.controller.current == 50.0
    assert brightness.controller.last_applied is None
    brightness.dxva2.SetMonitorBrightness.assert_not_called()
    brightness.sbc.set_brightness.assert_not_called()


@pytest.mark.parametrize("coordinate,expected", [(-1000.0, 60), (1000.0, 40)])
def test_coordinates_outside_image_are_clamped(brightness, coordinate, expected):
    assert brightness.controller.set_brightness_from_y(coordinate).success is True
    assert brightness.controller.last_applied == expected


def test_sbc_selected_when_native_dll_is_unavailable(monkeypatch):
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace())
    sbc = SimpleNamespace(set_brightness=MagicMock())
    monkeypatch.setitem(sys.modules, "screen_brightness_control", sbc)
    controller = brightness_module.BrightnessController()

    assert controller.set_brightness_from_y(0.2).success is True
    sbc.set_brightness.assert_called_once_with(60)


def test_failed_handle_acquisition_does_not_destroy_unowned_handles(brightness):
    brightness.dxva2.GetPhysicalMonitorsFromHMONITOR.side_effect = None
    brightness.dxva2.GetPhysicalMonitorsFromHMONITOR.return_value = False

    assert brightness.controller.set_brightness_from_y(0.2).success is True

    brightness.dxva2.DestroyPhysicalMonitors.assert_not_called()
    brightness.dxva2.SetMonitorBrightness.assert_not_called()
    brightness.sbc.set_brightness.assert_called_once_with(60)


def test_native_read_exception_still_destroys_handles(brightness):
    brightness.dxva2.GetMonitorBrightness.side_effect = OSError("Display removed")

    assert brightness.controller.set_brightness_from_y(0.2).success is True

    brightness.dxva2.DestroyPhysicalMonitors.assert_called_once()
    brightness.dxva2.SetMonitorBrightness.assert_not_called()
    brightness.sbc.set_brightness.assert_called_once_with(60)


def test_cleanup_failure_is_reported_when_fallback_also_fails(brightness):
    brightness.dxva2.DestroyPhysicalMonitors.return_value = False
    brightness.sbc.set_brightness.side_effect = OSError("Unavailable")

    result = brightness.controller.set_brightness_from_y(0.2)

    assert result.success is False
    assert "handles could not be released" in result.error
    assert brightness.controller.last_applied is None


def test_missing_sbc_dependency_returns_error_instead_of_success(brightness, monkeypatch):
    brightness.controller._backend = "sbc"
    monkeypatch.setitem(sys.modules, "screen_brightness_control", None)

    result = brightness.controller.set_brightness_from_y(0.2)

    assert result.success is False
    assert result.error
    assert brightness.controller.last_applied is None


def test_same_successfully_applied_level_does_not_send_duplicate_update(brightness):
    assert brightness.controller.set_brightness_from_y(0.5).success is True

    unchanged = brightness.controller.set_brightness_from_y(0.5)

    assert unchanged.success is True
    assert unchanged.message == "Brightness: 50%"
    brightness.dxva2.SetMonitorBrightness.assert_called_once()
