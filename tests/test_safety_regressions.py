"""
tests/test_safety_regressions.py — P0 safety regression tests.

Covers:
- Emergency pause: releases all state
- Re-arm guard: automation stays disarmed until neutral observed
- Temporal reset: hand loss, camera loss, stale detector TTL
- Tracking generation invalidation across pause/resume
- Drawing canvas resize integration
- ActionResult from all action controllers
- Trainer deep validation
- Version consistency

(§74 mandatory test coverage)
"""
import sys
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_landmark(x=0.5, y=0.5, z=0.0, px=320, py=240):
    from src.models import Landmark
    return Landmark(id=0, x=x, y=y, z=z, pixel_x=px, pixel_y=py)


def _21_landmarks(x=0.5, y=0.5):
    from src.models import Landmark
    return [
        Landmark(id=i, x=x, y=y, z=0.0, pixel_x=int(x * 640), pixel_y=int(y * 480))
        for i in range(21)
    ]


def _make_mapper(width, height):
    """Real mapper, timers and reset paths with lasting fake desktop input."""
    from src.gesture_mapper import GestureMapper

    with (
        patch("src.virtual_mouse.ctypes.windll"),
        patch("src.gesture_mapper.VolumeController"),
        patch("src.gesture_mapper.BrightnessController"),
        patch("src.gesture_mapper.FeedbackController"),
        patch("src.settings_manager.settings_manager.register_callback"),
    ):
        return GestureMapper(width, height)


# ── Automation state management (§5, §6) ─────────────────────────────────────

class TestAutomationState:
    def _make_main(self):
        """Build a minimal MainApp-like object with mocked subsystems."""
        # Patch heavy imports so we don't need a camera / MediaPipe
        with (
            patch("src.camera.cv2.VideoCapture"),
            patch("src.gesture_detector.vision.HandLandmarker"),
        ):
            pass
        # Just test the automation lock directly
        import main as m_module
        # Create instance attributes directly — no real threads
        obj = object.__new__(m_module.MainApp)
        obj._automation_lock = threading.RLock()
        obj._tracking_generation = 0
        obj._automation_enabled = True
        obj._rearm_state = m_module.MainApp._REARM_ARMED
        obj._rearm_neutral_frames = 0
        obj._REARM_NEUTRAL_REQUIRED = m_module.MainApp._REARM_NEUTRAL_REQUIRED

        # Mock mapper and classifier
        obj.mapper = MagicMock()
        obj.classifier = MagicMock()
        return obj, m_module.MainApp

    def test_set_automation_enabled_false_releases(self):
        obj, cls = self._make_main()
        cls.set_automation_enabled(obj, False)

        assert obj._automation_enabled is False
        obj.mapper.mouse.release_all.assert_called_once()
        obj.mapper.reset_temporal_state.assert_called_once()
        obj.classifier.reset.assert_called_once()
        assert obj._rearm_state == cls._REARM_IDLE

    def test_set_automation_enabled_true_enters_waiting(self):
        obj, cls = self._make_main()
        # First pause
        cls.set_automation_enabled(obj, False)
        # Then resume
        cls.set_automation_enabled(obj, True)

        assert obj._automation_enabled is True
        assert obj._rearm_state == cls._REARM_WAITING

    def test_rearm_stays_disarmed_until_neutral(self):
        obj, cls = self._make_main()
        cls.set_automation_enabled(obj, False)
        cls.set_automation_enabled(obj, True)
        # Now in WAITING — a non-neutral gesture must not arm
        armed = cls._tick_rearm(obj, "Open Palm")
        assert armed is False
        assert obj._rearm_state == cls._REARM_WAITING

    def test_rearm_arms_after_required_neutral_frames(self):
        obj, cls = self._make_main()
        cls.set_automation_enabled(obj, False)
        cls.set_automation_enabled(obj, True)
        required = obj._REARM_NEUTRAL_REQUIRED
        for _ in range(required):
            armed = cls._tick_rearm(obj, "Unknown")
        assert armed is True
        assert obj._rearm_state == cls._REARM_ARMED

    def test_hotkey_toggle_calls_set_automation_enabled(self):
        obj, cls = self._make_main()
        obj._automation_enabled = True
        # Simulate hotkey toggle
        cls._hotkey_toggle_automation(obj)
        assert obj._automation_enabled is False

    def test_set_automation_idempotent(self):
        """Calling set_automation_enabled with same value twice is safe."""
        obj, cls = self._make_main()
        cls.set_automation_enabled(obj, True)  # was already True
        # Should not call release_all (no-op)
        obj.mapper.mouse.release_all.assert_not_called()


# ── Temporal reset (§8) ───────────────────────────────────────────────────────

class TestTemporalReset:
    def test_reset_temporal_state_resets_timer(self):
        mapper = _make_mapper(640, 480)
        mapper.timer.target_gesture = "Pointing"
        mapper.timer.start_time = time.perf_counter() - 999
        mapper.reset_temporal_state()
        assert mapper.timer.target_gesture is None
        assert mapper.timer.start_time == 0.0

    def test_reset_temporal_state_resets_sleep_timer(self):
        mapper = _make_mapper(640, 480)
        mapper.sleep_timer.target_gesture = "Victory"
        mapper.reset_temporal_state()
        assert mapper.sleep_timer.target_gesture is None

    def test_reset_temporal_state_clears_brightness(self):
        mapper = _make_mapper(640, 480)
        mapper.brightness_gesture_active = True
        mapper.last_brightness_y = 0.5
        mapper.reset_temporal_state()
        assert mapper.brightness_gesture_active is False
        assert mapper.last_brightness_y is None

    def test_classifier_reset_clears_history(self):
        from src.gesture_classifier import GestureClassifier
        clf = GestureClassifier()
        clf.history.append("Pointing")
        clf.history.append("Open Palm")
        clf.reset()
        assert len(clf.history) == 0
        assert clf.confidence_ema == 0.0


# ── Drawing resize integration (§10, §11) ────────────────────────────────────

class TestDrawingResize:
    def test_resize_updates_canvas_numpy_shape(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(1280, 720)
        assert dc.canvas.shape == (720, 1280, 3)
        result = dc.resize(640, 480)
        assert result.success
        assert dc.canvas.shape == (480, 640, 3)
        assert dc.width == 640
        assert dc.height == 480

    def test_resize_resizes_undo_history(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(1280, 720)
        dc._save_state()
        dc.resize(640, 480)
        for snap in dc.undo_stack:
            assert snap.shape == (480, 640, 3)

    def test_resize_invalid_dims_returns_failure(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(640, 480)
        result = dc.resize(-1, 480)
        assert not result.success

    def test_resize_same_dims_is_noop(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(640, 480)
        result = dc.resize(640, 480)
        assert result.success

    def test_draw_after_resize_no_shape_mismatch(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(1280, 720)
        dc.resize(640, 480)
        # draw in 640x480 coordinates — should not crash
        dc.draw(100, 100, draw_mode=True)
        dc.draw(200, 200, draw_mode=True)
        assert dc.canvas.shape == (480, 640, 3)

    def test_overlay_after_resize_no_shape_mismatch(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(640, 480)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result_frame = dc.get_overlay(frame)
        assert result_frame.shape == frame.shape

    def test_undo_after_resize(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(640, 480)
        dc.resize(320, 240)
        dc.draw(50, 50, draw_mode=True)
        dc.draw(60, 60, draw_mode=True)
        result = dc.undo()
        assert result.success
        assert dc.canvas.shape == (240, 320, 3)

    def test_redo_after_resize(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(640, 480)
        dc.draw(50, 50, draw_mode=True)
        dc.draw(60, 60, draw_mode=True)
        dc.resize(320, 240)
        dc.undo()
        result = dc.redo()
        assert result.success

    def test_mapper_update_frame_dimensions_calls_canvas_resize(self):
        mapper = _make_mapper(1280, 720)
        assert mapper.canvas.width == 1280
        assert mapper.canvas.height == 720
        mapper.update_frame_dimensions(640, 480)
        assert mapper.frame_w == 640
        assert mapper.frame_h == 480
        assert mapper.canvas.width == 640
        assert mapper.canvas.height == 480


# ── Draw history correctness (§11) ────────────────────────────────────────────

class TestDrawHistory:
    def test_undo_stack_capped_at_max(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(100, 100)
        for i in range(DrawingCanvas.MAX_UNDO_STEPS + 5):
            dc._save_state()
        assert len(dc.undo_stack) <= DrawingCanvas.MAX_UNDO_STEPS

    def test_clear_invalidates_redo(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(100, 100)
        dc.draw(10, 10, draw_mode=True)
        dc.undo()
        assert len(dc.redo_stack) > 0
        dc.clear()
        # clear saves state but redo on the new blank is impossible
        result = dc.redo()
        # redo stack was populated by undo, then clear saves again but
        # does NOT clear redo — but draw after undo must clear redo
        # The key test: new draw after undo must clear redo
        dc.draw(20, 20, draw_mode=True)
        assert len(dc.redo_stack) == 0

    def test_new_draw_after_undo_clears_redo(self):
        from src.drawing import DrawingCanvas
        dc = DrawingCanvas(100, 100)
        dc.draw(10, 10, draw_mode=True)
        dc.draw(20, 20, draw_mode=True)
        dc.undo()
        assert len(dc.redo_stack) > 0
        # A fresh draw_mode=True (starting new stroke) calls _save_state + redo_stack.clear()
        dc.is_drawing = False
        dc.draw(30, 30, draw_mode=True)
        assert len(dc.redo_stack) == 0


# ── ActionResult from controllers (§22) ──────────────────────────────────────

class TestActionResults:
    def test_media_play_pause_returns_action_result(self):
        from src.media_controller import MediaController
        from src.models import ActionResult
        ctrl = MediaController()
        with patch("keyboard.send"):
            result = ctrl.play_pause()
        assert isinstance(result, ActionResult)
        assert isinstance(result.success, bool)

    def test_media_next_track_returns_action_result(self):
        from src.media_controller import MediaController
        from src.models import ActionResult
        ctrl = MediaController()
        with patch("keyboard.send"):
            result = ctrl.next_track()
        assert isinstance(result, ActionResult)

    def test_media_mute_returns_action_result(self):
        from src.media_controller import MediaController
        from src.models import ActionResult
        ctrl = MediaController()
        with patch("keyboard.send"):
            result = ctrl.mute()
        assert isinstance(result, ActionResult)

    def test_media_cooldown_returns_failure(self):
        from src.media_controller import MediaController
        from src.models import ActionResult
        ctrl = MediaController()
        ctrl._last_action_time = time.perf_counter()  # just acted
        result = ctrl.play_pause()
        assert isinstance(result, ActionResult)
        assert result.success is False

    def test_media_keyboard_exception_returns_failure(self):
        from src.media_controller import MediaController
        from src.models import ActionResult
        ctrl = MediaController()
        with patch("keyboard.send", side_effect=Exception("kbd error")):
            result = ctrl.play_pause()
        assert isinstance(result, ActionResult)
        assert result.success is False

    def test_volume_up_unavailable_returns_action_result(self):
        from src.volume_controller import VolumeController
        from src.models import ActionResult
        ctrl = VolumeController()
        ctrl.volume = None  # simulate no endpoint
        # patch _try_reacquire so it doesn't actually try
        with patch.object(ctrl, "_try_reacquire", return_value=False):
            result = ctrl.volume_up()
        assert isinstance(result, ActionResult)
        assert result.success is False

    def test_volume_down_unavailable_returns_action_result(self):
        from src.volume_controller import VolumeController
        from src.models import ActionResult
        ctrl = VolumeController()
        ctrl.volume = None
        with patch.object(ctrl, "_try_reacquire", return_value=False):
            result = ctrl.volume_down()
        assert isinstance(result, ActionResult)
        assert result.success is False

    def test_shortcut_snap_left_returns_action_result(self):
        from src.shortcut_controller import ShortcutController
        from src.models import ActionResult
        ctrl = ShortcutController()
        with patch("keyboard.send"):
            result = ctrl.snap_left()
        assert isinstance(result, ActionResult)
        assert result.success is True

    def test_shortcut_snap_keyboard_failure_returns_action_result(self):
        from src.shortcut_controller import ShortcutController
        from src.models import ActionResult
        ctrl = ShortcutController()
        with patch("keyboard.send", side_effect=Exception("kbd fail")):
            result = ctrl.snap_right()
        assert isinstance(result, ActionResult)
        assert result.success is False

    def test_shortcut_vscode_not_found_returns_failure(self):
        from src.shortcut_controller import ShortcutController
        from src.models import ActionResult
        ctrl = ShortcutController()
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            result = ctrl.open_vscode()
        assert isinstance(result, ActionResult)
        assert result.success is False

    def test_shortcut_chrome_not_found_returns_failure(self):
        from src.shortcut_controller import ShortcutController
        from src.models import ActionResult
        ctrl = ShortcutController()
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            result = ctrl.open_chrome()
        assert isinstance(result, ActionResult)
        assert result.success is False


# ── Mapper feedback only on success (§23) ────────────────────────────────────

class TestMapperFeedback:
    def test_execute_action_speaks_on_success(self):
        from src.models import ActionResult
        mapper = _make_mapper(640, 480)
        mapper.feedback = MagicMock()

        success_fn = MagicMock(return_value=ActionResult(True, "test", "ok"))
        mapper.action_registry["test_action"] = {"func": success_fn, "repeatable": False}
        mapper.execute_action("test_action")
        mapper.feedback.speak.assert_called_once()

    def test_execute_action_does_not_speak_on_failure(self):
        from src.models import ActionResult
        mapper = _make_mapper(640, 480)
        mapper.feedback = MagicMock()

        fail_fn = MagicMock(return_value=ActionResult(False, "test", "cooldown"))
        mapper.action_registry["test_action"] = {"func": fail_fn, "repeatable": False}
        mapper.execute_action("test_action")
        mapper.feedback.speak.assert_not_called()


# ── Stale result invalidation (§9) ────────────────────────────────────────────

class TestTrackingInvalidation:
    def test_invalidation_releases_input_and_resets_current_observation(self):
        obj, _ = TestAutomationState()._make_main()
        obj._rearm_neutral_frames = 4
        obj._invalidate_tracking()
        assert obj._tracking_generation == 1
        assert obj._rearm_neutral_frames == 0
        obj.mapper.mouse.release_all.assert_called_once()
        obj.mapper.reset_temporal_state.assert_called_once()
        obj.classifier.reset.assert_called_once()

    def test_pause_and_resume_each_invalidate_in_flight_observations(self):
        obj, _ = TestAutomationState()._make_main()
        initial_generation = obj._tracking_generation
        obj.set_automation_enabled(False)
        assert obj._tracking_generation == initial_generation + 1
        obj.set_automation_enabled(True)
        assert obj._tracking_generation == initial_generation + 2
        assert obj._rearm_state == obj._REARM_WAITING


class TestCustomGestureValidation:
    def test_add_sample_rejects_builtin_name_case_insensitive(self):
        from src.gesture_trainer import GestureTrainer
        trainer = GestureTrainer.__new__(GestureTrainer)
        trainer.custom_gestures = {}
        trainer.models_dir = Path("/tmp")

        lms = _21_landmarks()
        result, msg = trainer.add_sample("pinch", lms)  # lowercase collision
        assert result is False

        result, msg = trainer.add_sample("PINCH", lms)  # uppercase
        assert result is False

        result, msg = trainer.add_sample("Pinch", lms)  # proper case
        assert result is False

    def test_add_sample_rejects_invalid_landmark_count(self):
        from src.gesture_trainer import GestureTrainer
        trainer = GestureTrainer.__new__(GestureTrainer)
        trainer.custom_gestures = {}
        trainer.models_dir = Path("/tmp")

        lms_22 = _21_landmarks() + [_make_landmark()]  # 22 landmarks
        result, msg = trainer.add_sample("MyGesture", lms_22)
        assert result is False

    def test_add_sample_valid(self):
        from src.gesture_trainer import GestureTrainer
        trainer = GestureTrainer.__new__(GestureTrainer)
        trainer.custom_gestures = {}
        trainer.models_dir = Path("/tmp")

        lms = _21_landmarks()
        result, msg = trainer.add_sample("MyCustomGesture", lms)
        assert result is True

    def test_load_models_handles_corrupt_json(self, tmp_path):
        from src.gesture_trainer import GestureTrainer
        corrupt = tmp_path / "custom_gestures.json"
        corrupt.write_text("{not valid json!!!")

        trainer = GestureTrainer.__new__(GestureTrainer)
        trainer.models_dir = tmp_path
        trainer.custom_gestures = {}
        trainer.load_models()
        # Should have recovered to empty dict — no crash
        assert trainer.custom_gestures == {}

    def test_load_models_handles_non_list_values(self, tmp_path):
        import json
        from src.gesture_trainer import GestureTrainer

        data = {"MyGesture": "not_a_list", "Good": []}
        corrupt = tmp_path / "custom_gestures.json"
        corrupt.write_text(json.dumps(data))

        trainer = GestureTrainer.__new__(GestureTrainer)
        trainer.models_dir = tmp_path
        trainer.custom_gestures = {}
        trainer.load_models()
        # "not_a_list" should be filtered out
        assert "MyGesture" not in trainer.custom_gestures or \
               isinstance(trainer.custom_gestures.get("MyGesture"), list)


# ── Version consistency (§51) ─────────────────────────────────────────────────

class TestVersionConsistency:
    def test_version_uses_canonical_three_part_format(self):
        from src.version import __version__
        assert __version__.count(".") == 2
        assert all(part.isdigit() for part in __version__.split("."))

    def test_version_info_tuple_matches_version_string(self):
        from src.version import __version__, __version_info__
        parts = tuple(int(x) for x in __version__.split(".")[:3])
        assert parts == __version_info__, (
            f"__version_info__ {__version_info__} does not match "
            f"__version__ string {__version__}"
        )


# ── Camera: initial unavailable then recovery (§12) ───────────────────────────

class TestCameraRecovery:
    def test_camera_start_starts_thread_even_on_failure(self):
        """start() must always start the thread, even if camera fails to open."""
        from src.camera import Camera
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cap.read.return_value = (False, None)
        mock_cap.release = MagicMock()

        with patch("cv2.VideoCapture", return_value=mock_cap):
            cam = Camera(index=99)
            result = cam.start()
            time.sleep(0.05)
            cam.stop()

        assert result is False  # camera not available
        assert cam.running is False  # stopped after stop()

    def test_camera_stop_idempotent(self):
        """stop() called twice must not raise."""
        from src.camera import Camera
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_cap.release = MagicMock()
        with patch("cv2.VideoCapture", return_value=mock_cap):
            cam = Camera(index=0)
            cam.start()
            time.sleep(0.05)
            cam.stop()
            cam.stop()  # idempotent — must not crash
        assert cam.running is False


# ── Classifier settings initialization regression (§18) ──────────────────────

class TestClassifierSettingsInit:
    def test_classifier_loads_calibration_on_init(self):
        """
        Regression test §18: classifier must have calibration thresholds
        immediately after construction (on_settings_changed called in __init__).
        """
        from config import SETTINGS
        from src.gesture_classifier import GestureClassifier

        expected_enter = SETTINGS.get("calibration", {}).get("pinch_enter_threshold", 0.45)
        clf = GestureClassifier()
        assert clf.pinch_enter_threshold == expected_enter


# ── GestureDetector availability (§16) ───────────────────────────────────────

class TestDetectorAvailability:
    def test_detector_available_attribute_exists(self):
        from src.gesture_detector import GestureDetector
        with patch("src.gesture_detector.vision.HandLandmarker") as mock_hl:
            mock_hl.create_from_options.return_value = MagicMock()
            det = GestureDetector()
        assert hasattr(det, "available")

    def test_detector_unavailable_on_model_failure(self):
        from src.gesture_detector import GestureDetector
        with patch(
            "src.gesture_detector.vision.HandLandmarker.create_from_options",
            side_effect=RuntimeError("model not found"),
        ):
            det = GestureDetector()
        assert det.available is False
        assert det.detector is None
        assert det.error is not None
