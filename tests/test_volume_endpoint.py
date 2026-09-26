"""Core Audio API and COM lifecycle, without changing Windows audio."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.volume_controller import VolumeController


@pytest.fixture
def audio(monkeypatch):
    endpoint = MagicMock()
    endpoint.GetVolumeRange.return_value = (-60.0, 0.0, 1.0)
    endpoint.GetMasterVolumeLevelScalar.return_value = 0.5
    device = SimpleNamespace(EndpointVolume=endpoint)  # No obsolete Activate API.
    get_speakers = MagicMock(return_value=device)
    com = SimpleNamespace(CoInitialize=MagicMock(), CoUninitialize=MagicMock())
    monkeypatch.setitem(__import__("sys").modules, "comtypes", com)
    monkeypatch.setitem(__import__("sys").modules, "pycaw.pycaw",
                        SimpleNamespace(AudioUtilities=SimpleNamespace(GetSpeakers=get_speakers)))
    return endpoint, get_speakers, com


def test_endpoint_is_acquired_on_worker_initialization_and_closed_once(audio):
    endpoint, get_speakers, com = audio
    controller = VolumeController()
    get_speakers.assert_not_called()
    assert controller.initialize()
    assert controller.volume is endpoint
    assert (controller.min_vol, controller.max_vol) == (-60.0, 0.0)
    assert controller.initialize()
    com.CoInitialize.assert_called_once_with()
    controller.close()
    controller.close()
    assert controller.volume is None
    com.CoUninitialize.assert_called_once_with()


@pytest.mark.parametrize("method,current,expected", [
    ("volume_up", 0.99, 1.0), ("volume_down", 0.01, 0.0),
    ("volume_up", 0.5, 0.52), ("volume_down", 0.5, 0.48),
])
def test_volume_steps_use_supported_endpoint_and_clamp(audio, method, current, expected):
    endpoint, _, _ = audio
    endpoint.GetMasterVolumeLevelScalar.return_value = current
    controller = VolumeController()
    result = getattr(controller, method)()
    assert result.success
    endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(expected, None)
    controller.close()


def test_endpoint_loss_returns_failure_then_reacquires(audio):
    endpoint, get_speakers, com = audio
    controller = VolumeController()
    endpoint.SetMasterVolumeLevelScalar.side_effect = [RuntimeError("device unplugged"), None]
    assert not controller.volume_up().success
    assert controller.volume is None
    assert controller.volume_up().success
    assert get_speakers.call_count == 2
    com.CoInitialize.assert_called_once_with()
    controller.close()


def test_no_endpoint_does_not_disable_processing_or_leak_com(audio):
    _, get_speakers, com = audio
    get_speakers.side_effect = RuntimeError("no speakers")
    controller = VolumeController()
    assert not controller.initialize()
    assert not controller.volume_up().success
    controller.close()
    com.CoInitialize.assert_called_once_with()
    com.CoUninitialize.assert_called_once_with()


@pytest.mark.parametrize("distance,low,high", [(50, 1, 1), (50, 2, 1), (float("nan"), 0, 1)])
def test_invalid_continuous_range_does_not_touch_endpoint(audio, distance, low, high):
    endpoint, get_speakers, _ = audio
    controller = VolumeController()
    assert controller.set_volume_by_distance(distance, low, high) == 0
    get_speakers.assert_not_called()
    endpoint.SetMasterVolumeLevel.assert_not_called()


def test_failed_continuous_write_and_reacquire_does_not_report_success(audio):
    endpoint, get_speakers, _ = audio
    controller = VolumeController()
    assert controller.initialize()
    endpoint.SetMasterVolumeLevel.side_effect = RuntimeError("device lost")
    get_speakers.side_effect = RuntimeError("still absent")
    assert controller.set_volume_by_distance(120) == 0
    controller.close()


def test_reacquire_does_not_move_an_endpoint_to_another_com_thread(audio, monkeypatch):
    _, get_speakers, com = audio
    controller = VolumeController()
    assert controller.initialize()
    monkeypatch.setattr("src.volume_controller.threading.get_ident", lambda: -1)
    assert not controller.initialize()
    get_speakers.assert_called_once_with()
    controller.close()
    com.CoUninitialize.assert_not_called()
