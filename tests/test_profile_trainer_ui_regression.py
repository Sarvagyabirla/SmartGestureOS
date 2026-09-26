"""Profile/training recovery and UI feedback, with files only under tmp_path.

UI methods run on plain mock objects; no Tk windows, camera or OS input is used.
"""

import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import config
import src.gesture_trainer as trainer_module
import src.settings_manager as settings_module
import src.ui as ui_module
import src.ui_settings as settings_ui_module
import src.ui_trainer as trainer_ui_module


@pytest.fixture
def profiles(tmp_path):
    folder = tmp_path / "profiles"
    folder.mkdir()
    return folder


@pytest.mark.parametrize("contents", ['{"camera":', '[]', '{"camera": []}', '{"gestures": {"smoothing": 0}}'])
def test_malformed_startup_profile_is_preserved_with_safe_in_memory_defaults(profiles, contents):
    path = profiles / "default.json"
    path.write_text(contents, encoding="utf-8")

    manager = settings_module.SettingsManager(profiles_dir=profiles)

    settings_module.validate_settings(manager.settings)
    assert manager.current_profile == "default"
    assert manager.last_error
    assert path.read_text(encoding="utf-8") == contents
    assert list(profiles.glob("*.tmp")) == []


def test_bad_factory_defaults_recover_to_complete_safe_defaults(profiles, tmp_path, monkeypatch):
    resources = tmp_path / "resources"
    (resources / "config").mkdir(parents=True)
    factory = resources / "config" / "defaults.json"
    factory.write_text('{"camera": null}', encoding="utf-8")
    monkeypatch.setattr(settings_module, "RESOURCE_DIR", resources)

    manager = settings_module.SettingsManager(profiles_dir=profiles)

    settings_module.validate_settings(manager.settings)
    assert manager.settings["mappings"] == {"GENERAL": {}, "MEDIA": {}, "DRAW": {}}
    assert factory.read_text(encoding="utf-8") == '{"camera": null}'
    assert list(profiles.iterdir()) == []


INVALID_PROFILES = [
    [], {"camera": None}, {"gestures": []}, {"ui": "dark"}, {"mappings": []},
    {"calibration": 1}, {"camera": {"index": True}}, {"camera": {"width": 0}},
    {"camera": {"fps": "30"}}, {"camera": {"height": 4321}},
    {"gestures": {"smoothing": 2.5}}, {"gestures": {"sensitivity": float("nan")}},
    {"gestures": {"hold_time_ms": -1}}, {"gestures": {"cooldown_ms": float("inf")}},
    {"calibration": {"hand_size_baseline": 0}}, {"calibration": {"active_roi_margin": 0.5}},
    {"calibration": {"pinch_enter_threshold": 0.8, "pinch_release_threshold": 0.6}},
    {"calibration": {"two_finger_max_spacing": 0.5, "victory_min_spacing": 0.35}},
    {"mappings": {"GENERAL": []}}, {"mappings": {"GENERAL": {"Victory": 42}}},
    {"ui": {"theme": False}},
]


@pytest.mark.parametrize("bad_profile", INVALID_PROFILES)
def test_invalid_profile_switch_keeps_active_settings_and_original_file(profiles, bad_profile):
    manager = settings_module.SettingsManager(profiles_dir=profiles)
    assert manager.load_profile("working")
    manager.settings["gestures"]["smoothing"] = 7
    assert manager.save_profile()
    settings_reference = manager.settings
    before = deepcopy(manager.settings)
    callback = MagicMock()
    manager.register_callback(callback)
    path = profiles / "broken.json"
    original = json.dumps(bad_profile)
    path.write_text(original, encoding="utf-8")

    assert manager.load_profile("broken") is False

    assert manager.settings is settings_reference
    assert manager.settings == before
    assert manager.current_profile == "working"
    assert manager.last_error
    assert path.read_text(encoding="utf-8") == original
    callback.assert_not_called()


def test_failed_new_profile_write_restores_active_configuration(profiles, monkeypatch):
    manager = settings_module.SettingsManager(profiles_dir=profiles)
    before = deepcopy(manager.settings)
    callback = MagicMock()
    manager.register_callback(callback)
    monkeypatch.setattr(Path, "replace", MagicMock(side_effect=PermissionError("read only")))

    assert manager.load_profile("new profile") is False

    assert manager.settings == before
    assert manager.current_profile == "default"
    assert "read only" in manager.last_error
    assert list(profiles.iterdir()) == []
    callback.assert_not_called()


def test_invalid_save_preserves_last_good_file(profiles):
    manager = settings_module.SettingsManager(profiles_dir=profiles)
    assert manager.save_profile()
    path = profiles / "default.json"
    before = path.read_bytes()
    manager.settings["camera"]["fps"] = float("nan")

    assert manager.save_profile() is False

    assert path.read_bytes() == before
    assert manager.last_error
    assert not path.with_suffix(".tmp").exists()


def test_partial_profile_merges_defaults_and_keeps_shared_dict(profiles):
    manager = settings_module.SettingsManager(profiles_dir=profiles)
    reference = manager.settings
    (profiles / "custom.json").write_text(json.dumps({"gestures": {"smoothing": 4}}), encoding="utf-8")

    assert manager.load_profile("custom") is True

    assert manager.settings is reference
    assert manager.settings["gestures"]["smoothing"] == 4
    assert manager.settings["camera"]["fps"] == 30
    assert manager.settings["profile_name"] == "custom"
    settings_module.validate_settings(manager.settings)


def landmarks():
    return [{"x": i * 0.01, "y": i * 0.02, "z": i * -0.003} for i in range(21)]


def test_trainer_load_filters_invalid_vectors_names_and_excess_samples(tmp_path):
    trainer = trainer_module.GestureTrainer(models_dir=tmp_path)
    sample = trainer._normalize_landmarks(landmarks())
    invalid = [[0.0] * 62, [True] * 63, ["0"] * 63, [float("nan")] * 63, [float("inf")] * 63, None]
    data = {"Custom Pose": invalid + [sample] * 55, "Victory": [sample], "../bad": [sample], "Invalid": "data"}
    path = tmp_path / "custom_gestures.json"
    original = json.dumps(data)
    path.write_text(original, encoding="utf-8")

    trainer.load_models()

    assert set(trainer.custom_gestures) == {"Custom Pose"}
    assert len(trainer.custom_gestures["Custom Pose"]) == 50
    assert all(len(vector) == 63 and all(math.isfinite(v) for v in vector)
               for vector in trainer.custom_gestures["Custom Pose"])
    assert trainer.classify(landmarks())[0] == "Custom Pose"
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("contents", ['{"unfinished":', '[]', '{"Bad": [[1, 2, 3]]}'])
def test_corrupt_training_file_does_not_crash_classification_or_get_overwritten(tmp_path, contents):
    path = tmp_path / "custom_gestures.json"
    path.write_text(contents, encoding="utf-8")

    trainer = trainer_module.GestureTrainer(models_dir=tmp_path)

    assert trainer.classify(landmarks()) == (None, float("inf"))
    assert path.read_text(encoding="utf-8") == contents


def test_classification_ignores_corrupt_in_memory_samples(tmp_path):
    trainer = trainer_module.GestureTrainer(models_dir=tmp_path)
    assert trainer.add_sample("Valid", landmarks())[0]
    trainer.custom_gestures.update({"WrongLength": [[0] * 62], "NotNumbers": [["bad"] * 63],
                                   "NonFinite": [[float("nan")] * 63], "WrongType": 42})

    assert trainer.classify(landmarks())[0] == "Valid"


@pytest.mark.parametrize("bad_landmarks", [42, [None] * 21, [{"x": 1}] * 21,
    [{"x": 10 ** 400, "y": 0, "z": 0}] * 21,
    [{"x": float("nan"), "y": 0, "z": 0}] * 21])
def test_invalid_training_input_is_rejected_without_breaking_ui_loop(tmp_path, bad_landmarks):
    trainer = trainer_module.GestureTrainer(models_dir=tmp_path)

    success, message = trainer.add_sample("New Pose", bad_landmarks)

    assert success is False
    assert message
    assert trainer.custom_gestures == {}


def test_failed_model_save_and_delete_preserve_previous_data(tmp_path, monkeypatch):
    trainer = trainer_module.GestureTrainer(models_dir=tmp_path)
    assert trainer.add_sample("Saved", landmarks())[0]
    assert trainer.save_models()
    path = tmp_path / "custom_gestures.json"
    original = path.read_bytes()
    saved = deepcopy(trainer.custom_gestures)
    monkeypatch.setattr(Path, "replace", MagicMock(side_effect=PermissionError("read only")))

    assert trainer.delete_gesture("Saved") is False

    assert trainer.custom_gestures == saved
    assert path.read_bytes() == original
    assert not path.with_suffix(".tmp").exists()


AUXILIARY_WINDOWS = [
    ("open_settings", "settings_window", "src.ui_settings", "SettingsUI"),
    ("open_trainer", "trainer_window", "src.ui_trainer", "TrainerUI"),
    ("open_coach", "coach_window", "src.ui_coach", "CoachUI"),
]


@pytest.mark.parametrize("method,attribute,module_name,class_name", AUXILIARY_WINDOWS)
@pytest.mark.parametrize("existing", [False, True])
def test_auxiliary_windows_pause_before_creation_or_focus(monkeypatch, method, attribute, module_name, class_name, existing):
    events = []
    window = MagicMock()
    window.winfo_exists.return_value = True
    window.focus.side_effect = lambda: events.append("focus")
    factory = MagicMock(side_effect=lambda *args, **kwargs: (events.append("create"), window)[1])
    monkeypatch.setitem(sys.modules, module_name, SimpleNamespace(**{class_name: factory}))
    app = SimpleNamespace(set_automation_callback=lambda value: events.append(("pause", value)),
                          toggle_pause_callback=None, automation_enabled=True,
                          settings_window=None, trainer_window=None, coach_window=None)
    if existing:
        setattr(app, attribute, window)
    app._pause_for_auxiliary_ui = lambda: ui_module.SmartGestureApp._pause_for_auxiliary_ui(app)

    getattr(ui_module.SmartGestureApp, method)(app)

    assert events == [("pause", False), "focus" if existing else "create"]
    assert app.automation_enabled is False


def test_legacy_pause_callback_never_resumes_an_already_paused_app():
    toggle = MagicMock()
    app = SimpleNamespace(set_automation_callback=None, toggle_pause_callback=toggle, automation_enabled=True)

    ui_module.SmartGestureApp._pause_for_auxiliary_ui(app)
    ui_module.SmartGestureApp._pause_for_auxiliary_ui(app)

    toggle.assert_called_once()
    assert app.automation_enabled is False


@pytest.fixture
def settings_ui(profiles, monkeypatch):
    manager = settings_module.SettingsManager(profiles_dir=profiles)
    monkeypatch.setattr(config, "settings_manager", manager)
    monkeypatch.setattr(settings_ui_module, "settings_manager", manager)
    messages = SimpleNamespace(showerror=MagicMock(), showinfo=MagicMock())
    monkeypatch.setattr(settings_ui_module, "messagebox", messages)
    window = SimpleNamespace(**{name: MagicMock(get=MagicMock(return_value=value)) for name, value in (
        ("sensitivity_slider", 0.8), ("smoothing_slider", 5), ("hold_slider", 600),
        ("cooldown_slider", 800), ("rock_on_var", "open_chrome"), ("call_me_var", "switch_mode"),
    )})
    window.on_closing = MagicMock()
    window.apply_settings = lambda: settings_ui_module.SettingsUI.apply_settings(window)
    return manager, window, messages


def test_settings_save_failure_rolls_back_and_keeps_window_open(settings_ui, monkeypatch):
    manager, window, messages = settings_ui
    previous = deepcopy(manager.settings)
    reference = manager.settings
    monkeypatch.setattr(manager, "save_profile", MagicMock(return_value=False))
    manager.last_error = "Disk full"

    settings_ui_module.SettingsUI.save_and_close(window)

    assert manager.settings == previous
    assert manager.settings is reference
    messages.showerror.assert_called_once_with("Save failed", "Disk full")
    messages.showinfo.assert_not_called()
    window.on_closing.assert_not_called()


def test_calibration_save_failure_restores_value_and_does_not_claim_success(settings_ui, monkeypatch):
    manager, _, messages = settings_ui
    before = manager.settings["gestures"]["base_hand_size"]
    monkeypatch.setattr(manager, "save_profile", MagicMock(return_value=False))
    points = [SimpleNamespace(**lm) for lm in landmarks()]
    wizard = SimpleNamespace(master=SimpleNamespace(master=SimpleNamespace(current_hands_data=[{"landmarks": points}])),
                             destroy=MagicMock())

    settings_ui_module.CalibrationWizard.do_calibrate(wizard)

    assert manager.settings["gestures"]["base_hand_size"] == before
    messages.showerror.assert_called_once()
    messages.showinfo.assert_not_called()
    wizard.destroy.assert_not_called()


def test_failed_profile_selection_keeps_ui_on_active_profile(settings_ui, monkeypatch):
    manager, window, messages = settings_ui
    monkeypatch.setattr(manager, "load_profile", MagicMock(return_value=False))
    window.profile_var = MagicMock()

    settings_ui_module.SettingsUI.on_profile_change(window, "Broken")

    window.profile_var.set.assert_called_once_with(manager.current_profile)
    messages.showerror.assert_called_once()
    window.sensitivity_slider.set.assert_not_called()


@pytest.mark.parametrize("saved", [False, True])
def test_trainer_feedback_reflects_save_result_without_opening_tk(monkeypatch, saved):
    trainer = SimpleNamespace(save_models=MagicMock(return_value=saved))
    monkeypatch.setattr(trainer_ui_module, "gesture_trainer", trainer)
    window = SimpleNamespace(is_recording=True, master=SimpleNamespace(current_hands_data=[]),
                             samples_collected=30, target_samples=30, record_btn=MagicMock(),
                             status_label=MagicMock(), name_entry=MagicMock(), update_list=MagicMock())

    trainer_ui_module.TrainerUI.record_loop(window, "Pose")

    assert window.is_recording is False
    trainer.save_models.assert_called_once()
    text = window.status_label.configure.call_args.kwargs["text"]
    assert ("Saved Successfully" in text) is saved
    if not saved:
        assert "Save failed" in text
        window.name_entry.delete.assert_not_called()
        window.update_list.assert_not_called()
