"""Controller outcomes must reflect mocked Windows input and launch failures."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import src.desktop_controller as desktop_module
import src.presentation_controller as presentation_module
import src.shortcut_controller as shortcut_module
from src.models import ActionResult


KEY_ACTIONS = [
    (desktop_module, "DesktopController", "show_desktop", "windows+d", 1.0),
    (desktop_module, "DesktopController", "task_view", "windows+tab", 1.0),
    (desktop_module, "DesktopController", "switch_window", "alt+tab", 1.0),
    (desktop_module, "DesktopController", "open_start", "windows", 1.0),
    (presentation_module, "PresentationController", "next_slide", "right", 1.5),
    (presentation_module, "PresentationController", "prev_slide", "left", 1.5),
]


def mock_key_controller(monkeypatch, module, controller_name, *, now=10.0):
    clock = SimpleNamespace(now=now)
    # Deliberately provide no wall-clock API: cooldowns must use elapsed time.
    monkeypatch.setattr(module, "time", SimpleNamespace(perf_counter=lambda: clock.now))
    send = MagicMock()
    monkeypatch.setattr(module, "keyboard", SimpleNamespace(send=send))
    return getattr(module, controller_name)(), send, clock


@pytest.mark.parametrize("module,controller_name,method,key,cooldown", KEY_ACTIONS)
def test_shortcut_returns_success_and_enforces_monotonic_cooldown(
    monkeypatch, module, controller_name, method, key, cooldown
):
    controller, send, clock = mock_key_controller(monkeypatch, module, controller_name)

    first = getattr(controller, method)()
    assert isinstance(first, ActionResult)
    assert first.success is True
    assert first.action == key
    assert first.timestamp == 10.0
    send.assert_called_once_with(key)

    clock.now += cooldown / 2
    blocked = getattr(controller, method)()
    assert isinstance(blocked, ActionResult)
    assert blocked.success is False
    assert blocked.error is None
    assert blocked.timestamp == clock.now
    send.assert_called_once_with(key)

    clock.now += cooldown
    assert getattr(controller, method)().success is True
    assert send.call_count == 2


@pytest.mark.parametrize("module,controller_name,method,key,cooldown", KEY_ACTIONS)
def test_failed_keyboard_send_returns_failure_and_allows_retry(
    monkeypatch, module, controller_name, method, key, cooldown
):
    controller, send, clock = mock_key_controller(monkeypatch, module, controller_name)
    send.side_effect = [OSError("input unavailable"), None]

    failed = getattr(controller, method)()

    assert isinstance(failed, ActionResult)
    assert failed.success is False
    assert failed.action == key
    assert failed.error == "input unavailable"
    assert failed.timestamp == clock.now
    assert getattr(controller, method)().success is True
    assert send.call_count == 2


@pytest.mark.parametrize(
    "module,controller_name,method",
    [(desktop_module, "DesktopController", "task_view"),
     (presentation_module, "PresentationController", "next_slide")],
)
def test_first_key_action_is_available_at_monotonic_clock_origin(
    monkeypatch, module, controller_name, method
):
    controller, send, _ = mock_key_controller(monkeypatch, module, controller_name, now=0.0)

    assert getattr(controller, method)().success is True
    send.assert_called_once()


@pytest.mark.parametrize("shim_in_bin", [True, False])
def test_vscode_cmd_shim_resolves_to_executable_without_running_batch(
    monkeypatch, tmp_path, shim_in_bin
):
    installation = tmp_path / "Portable VS Code"
    shim = installation / "bin" / "code.cmd" if shim_in_bin else installation / "code.cmd"
    executable = str(installation / "Code.exe")
    controller = shortcut_module.ShortcutController()
    monkeypatch.setattr(controller, "_find_exe", MagicMock(side_effect=[None, str(shim)]))
    monkeypatch.setattr(shortcut_module, "time", SimpleNamespace(perf_counter=lambda: 10.0))
    monkeypatch.setattr(shortcut_module, "os", SimpleNamespace(path=SimpleNamespace(
        join=os.path.join, dirname=os.path.dirname, basename=os.path.basename,
        isfile=lambda path: path == executable,
    )))
    popen = MagicMock()
    monkeypatch.setattr(shortcut_module, "subprocess", SimpleNamespace(Popen=popen))

    result = controller.open_vscode()

    assert result.success is True
    popen.assert_called_once_with([executable], shell=False)


def test_vscode_shim_without_executable_returns_failure(monkeypatch, tmp_path):
    controller = shortcut_module.ShortcutController()
    shim = str(tmp_path / "bin" / "code.cmd")
    monkeypatch.setattr(controller, "_find_exe", MagicMock(side_effect=[None, shim]))
    monkeypatch.setattr(shortcut_module, "os", SimpleNamespace(path=SimpleNamespace(
        join=os.path.join, dirname=os.path.dirname, isfile=lambda path: False,
    )))
    popen = MagicMock()
    monkeypatch.setattr(shortcut_module, "subprocess", SimpleNamespace(Popen=popen))

    result = controller.open_vscode()

    assert result.success is False
    assert result.action == "open_vscode"
    popen.assert_not_called()
