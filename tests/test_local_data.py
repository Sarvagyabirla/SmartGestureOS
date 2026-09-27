"""Local-data upgrades preserve user-created files and tolerate storage failures."""
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

import src.logger as logger_module
import src.paths as paths
from src.settings_manager import validate_profile_name


def test_new_data_root_uses_product_name(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(paths, "user_data_dir", lambda name, appauthor: (calls.append((name, appauthor)), tmp_path / name)[1])

    assert paths.get_user_data_dir() == tmp_path / "SmartGestureOS"
    assert calls == [("SmartGestureOS", False)]


def test_upgrade_copies_local_data_once_without_overwriting_or_deleting(tmp_path):
    source = tmp_path / "SmartGesture"
    destination = tmp_path / "SmartGestureOS"
    for folder in ("profiles", "custom_gestures", "screenshots", "drawings", "logs", "benchmarks"):
        (source / folder).mkdir(parents=True)
        (source / folder / "saved.data").write_bytes(b"original")
    (destination / "profiles").mkdir(parents=True)
    (destination / "profiles" / "saved.data").write_bytes(b"current preferences")

    assert paths.migrate_legacy_user_data(source, destination)

    assert (destination / "profiles" / "saved.data").read_bytes() == b"current preferences"
    assert (destination / "drawings" / "saved.data").read_bytes() == b"original"
    assert all(file.read_bytes() == b"original" for file in source.glob("*/*"))
    (destination / "drawings" / "saved.data").unlink()
    assert paths.migrate_legacy_user_data(source, destination)
    assert not (destination / "drawings" / "saved.data").exists()


def test_failed_upgrade_preserves_original_and_retries_next_launch(tmp_path, monkeypatch):
    source, destination = tmp_path / "old", tmp_path / "new"
    (source / "profiles").mkdir(parents=True)
    original = source / "profiles" / "default.json"
    original.write_text('{"smoothing": 3}', encoding="utf-8")
    with monkeypatch.context() as context:
        context.setattr(paths.shutil, "copy2", lambda *_: (_ for _ in ()).throw(PermissionError("read only")))
        assert not paths.migrate_legacy_user_data(source, destination)

    assert original.read_text(encoding="utf-8") == '{"smoothing": 3}'
    assert not (destination / ".legacy-data-copied").exists()
    assert paths.migrate_legacy_user_data(source, destination)
    assert (destination / "profiles" / "default.json").read_bytes() == original.read_bytes()


def test_unavailable_log_file_does_not_prevent_startup(monkeypatch):
    isolated = logging.Logger("test-unavailable-log")
    monkeypatch.setattr(logger_module, "RotatingFileHandler", lambda *a, **kw: (_ for _ in ()).throw(PermissionError("read only")))
    with patch.object(logger_module.logging, "getLogger", return_value=isolated):
        assert logger_module.setup_logger() is isolated
        assert len(isolated.handlers) == 1
        # Repeated setup must not reopen files or add duplicate handlers.
        assert logger_module.setup_logger() is isolated
        assert len(isolated.handlers) == 1
    for handler in isolated.handlers:
        handler.close()


@pytest.mark.parametrize("name", ["   ", "CON ", " profile", "profile "])
def test_profile_names_reject_ambiguous_windows_spaces(name):
    assert validate_profile_name(name)[0] is False
