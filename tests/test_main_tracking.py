"""Execute the production loop with scripted frames and no hardware side effects."""

import queue
import threading
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import numpy as np
import pytest

import main as main_module
from src.models import GestureResult, Landmark


class ScriptFinished(BaseException):
    """End a finite loop script without being mistaken for a runtime error."""


class RecordingQueue(queue.Queue):
    def __init__(self):
        super().__init__(maxsize=1)
        self.published = []

    def put_nowait(self, item):
        self.published.append(item)
        super().put_nowait(item)


@dataclass
class FrameStep:
    at: float
    hands: list = field(default_factory=list)
    connected: bool = True
    has_frame: bool = True
    inference: str = "success"
    pause_during_inference: bool = False
    route_error: bool = False


def hand_at(x=0.5):
    return [{"landmarks": [
        Landmark(id=i, x=x, y=0.5, z=0.0, pixel_x=int(x * 80), pixel_y=30)
        for i in range(21)
    ], "score": 95}]


@pytest.fixture
def make_loop(monkeypatch):
    def build(steps, *, paused=False):
        app = main_module.MainApp.__new__(main_module.MainApp)
        app.running = True
        app._automation_lock = threading.RLock()
        app._automation_enabled = not paused
        app._tracking_generation = 0
        app._tracking_capture_time = None
        app._rearm_state = app._REARM_IDLE if paused else app._REARM_ARMED
        app._rearm_neutral_frames = 0
        app._was_camera_connected = False
        app._shutdown_lock = threading.Lock()
        app._shutdown_started = False
        app._hotkey_handle = None
        app.process_thread = None
        app.stats_thread = None
        app.cpu_usage = app.ram_usage = 0.0
        app.frame_queue = RecordingQueue()

        app.camera = MagicMock(width=80, height=60, is_connected=True)
        app.detector = MagicMock(available=True, error=None)
        app.classifier = MagicMock()
        app.mapper = MagicMock(mode="GENERAL", is_sleeping=False)
        clock = SimpleNamespace(now=steps[0].at)
        current = SimpleNamespace(step=None)
        frames = iter(enumerate(steps))
        sleep = MagicMock()
        monkeypatch.setattr(main_module, "time", SimpleNamespace(
            perf_counter=lambda: clock.now, sleep=sleep
        ))
        monkeypatch.setattr(main_module, "logger", MagicMock())

        def read():
            try:
                frame_id, step = next(frames)
            except StopIteration:
                raise ScriptFinished
            current.step = step
            clock.now = step.at
            app.camera.is_connected = step.connected
            if not step.has_frame:
                return None, -1, None
            return np.zeros((60, 80, 3), dtype=np.uint8), frame_id, step.at

        def infer(frame, timestamp_ms):
            step = current.step
            if step.pause_during_inference:
                app.set_automation_enabled(False)
            if step.inference == "exception":
                raise RuntimeError("Simulated inference failure")
            if step.inference == "none":
                return None
            return object()

        def route(hands, stable, raw, frame):
            if current.step.route_error:
                raise RuntimeError("Simulated mapper failure")
            return frame, None, 0.0

        app.camera.read_with_timestamp.side_effect = read
        app.detector.process_frame.side_effect = infer
        app.detector.get_all_hands_data.side_effect = lambda result, shape: current.step.hands
        app.classifier.classify.side_effect = lambda hands: (
            GestureResult("Pointing", "Pointing", 95.0, 100.0) if hands
            else GestureResult("Unknown", "None", 0.0, 0.0)
        )
        app.mapper.process.side_effect = route

        def run():
            with pytest.raises(ScriptFinished):
                app.processing_loop()
            return app.frame_queue.published

        run.clock = clock
        return app, run

    return build


def assert_cleared(observation):
    assert observation[1] == []
    assert observation[3:6] == ("Unknown", "Unknown", 0)


def test_hand_loss_resets_before_classifying_empty_and_reacquiring(make_loop):
    first, reacquired = hand_at(0.3), hand_at(0.7)
    app, run = make_loop([
        FrameStep(10.0, first), FrameStep(10.05), FrameStep(10.10, reacquired)
    ])

    observations = run()

    assert [item[1] for item in observations] == [first, [], reacquired]
    assert app.classifier.method_calls == [
        call.classify(first), call.reset(), call.classify([]), call.classify(reacquired)
    ]
    app.mapper.mouse.release_all.assert_called_once()
    app.mapper.reset_temporal_state.assert_called_once()
    assert app.mapper.process.call_count == 3
    assert len(app.mapper.process.call_args.args[0][0]["landmarks"]) == 21
    assert app.detector.draw_landmarks.call_count == 2


@pytest.mark.parametrize("failure", ["none", "exception", "route"])
def test_failed_processing_releases_input_and_clears_observation(make_loop, failure):
    app, run = make_loop([
        FrameStep(10.0, hand_at()),
        FrameStep(10.05, hand_at(), inference=failure, route_error=failure == "route"),
    ])

    observations = run()

    assert_cleared(observations[-1])
    assert observations[-1][6] is None
    app.mapper.mouse.release_all.assert_called_once()
    app.mapper.reset_temporal_state.assert_called_once()
    app.classifier.reset.assert_called_once()
    assert app.mapper.process.call_count == (2 if failure == "route" else 1)


def test_connected_camera_stall_releases_after_frame_expires(make_loop):
    first = hand_at()
    app, run = make_loop([
        FrameStep(10.0, first),
        FrameStep(10.1, has_frame=False),
        FrameStep(10.3, has_frame=False),
        FrameStep(10.4, has_frame=False),
    ])

    observations = run()

    assert len(observations) == 3  # Fresh preview, then two stale-camera status frames.
    assert observations[0][1] == first
    assert_cleared(observations[1])
    assert_cleared(observations[2])
    assert observations[-1][10] is True  # Driver still reports a connected camera.
    app.mapper.mouse.release_all.assert_called_once()
    app.classifier.reset.assert_called_once()
    assert app.mapper.process.call_count == 1


def test_camera_disconnection_clears_tracking_and_can_reacquire(make_loop):
    first, reacquired = hand_at(0.3), hand_at(0.7)
    app, run = make_loop([
        FrameStep(10.0, first),
        FrameStep(10.05, connected=False, has_frame=False),
        FrameStep(10.10, reacquired),
    ])

    observations = run()

    assert_cleared(observations[1])
    assert observations[1][10] is False
    assert observations[2][1] == reacquired
    assert observations[2][10] is True
    app.mapper.mouse.release_all.assert_called_once()
    assert app.mapper.process.call_count == 2


def test_pause_during_inference_discards_the_inflight_result(make_loop):
    app, run = make_loop([
        FrameStep(10.0, hand_at(), pause_during_inference=True)
    ])

    observations = run()

    assert_cleared(observations[-1])
    assert observations[-1][6] == "Paused"
    assert observations[-1][13] is False
    app.detector.get_all_hands_data.assert_not_called()
    app.classifier.classify.assert_not_called()
    app.mapper.process.assert_not_called()
    app.mapper.mouse.release_all.assert_called_once()


def test_paused_tracking_still_draws_21_landmarks_without_routing(make_loop):
    hand = hand_at()
    app, run = make_loop([FrameStep(10.0, hand)], paused=True)

    observations = run()

    assert observations[-1][1] == hand
    assert observations[-1][6] == "Paused"
    assert observations[-1][13] is False
    app.detector.draw_landmarks.assert_called_once()
    assert app.detector.draw_landmarks.call_args.args[1] == hand[0]["landmarks"]
    app.mapper.process.assert_not_called()


def test_skipped_inference_does_not_route_the_previous_result_again(make_loop):
    hand = hand_at()
    app, run = make_loop([
        FrameStep(10.0, hand), FrameStep(10.01, hand), FrameStep(10.02, hand)
    ])

    observations = run()

    assert len(observations) == 3
    app.detector.process_frame.assert_called_once()
    app.classifier.classify.assert_called_once_with(hand)
    app.mapper.process.assert_called_once()
    assert app.detector.draw_landmarks.call_count == 3


def test_constructor_can_start_paused_without_desktop_or_camera_side_effects(monkeypatch):
    for name in ("Camera", "GestureDetector", "GestureClassifier", "GestureMapper", "SmartGestureApp"):
        monkeypatch.setattr(main_module, name, MagicMock())
    import keyboard

    monkeypatch.setattr(keyboard, "add_hotkey", MagicMock(return_value="test-hotkey"))
    start = MagicMock()
    monkeypatch.setattr(main_module.MainApp, "start_system", start)
    monkeypatch.setattr(main_module, "SETTINGS", {
        "camera": {"index": 0, "width": 80, "height": 60, "fps": 30}
    })

    app = main_module.MainApp(start_paused=True)

    assert app.automation_enabled is False
    assert app._rearm_state == app._REARM_IDLE
    app.mapper.mouse.release_all.assert_called_once()
    app.classifier.reset.assert_called_once()
    app.camera.start.assert_not_called()
    start.assert_called_once()


@pytest.mark.parametrize("worker_alive", [False, True])
def test_shutdown_does_not_close_a_detector_owned_by_a_live_worker(make_loop, worker_alive):
    app, _ = make_loop([FrameStep(10.0)])
    app.process_thread = MagicMock()
    app.process_thread.is_alive.return_value = worker_alive

    app.stop_system()
    app.stop_system()

    assert app.running is False
    assert app.automation_enabled is False
    app.camera.stop.assert_called_once()
    app.mapper.cleanup.assert_called_once()
    if worker_alive:
        app.process_thread.join.assert_called_once_with(timeout=2.0)
        app.detector.close.assert_not_called()
    else:
        app.detector.close.assert_called_once()


@pytest.mark.parametrize("fails", [False, True])
def test_inference_worker_closes_its_detector_on_exit(make_loop, fails):
    app, _ = make_loop([FrameStep(10.0)])
    app.processing_loop = MagicMock(side_effect=RuntimeError("worker failed") if fails else None)

    if fails:
        with pytest.raises(RuntimeError, match="worker failed"):
            app._run_processing()
    else:
        app._run_processing()

    app.detector.close.assert_called_once()

    app.mapper.volume.initialize.assert_called_once_with()
    app.mapper.volume.close.assert_called_once_with()


def test_watchdog_keeps_tracking_at_the_250ms_boundary(make_loop):
    app, run = make_loop([FrameStep(10.0, hand_at())])
    run()
    assert app._tracking_capture_time == 10.0
    run.clock.now = 10.25

    assert app._expire_tracking() is False

    app.mapper.mouse.release_all.assert_not_called()
    assert app._tracking_capture_time == 10.0
    assert not app.frame_queue.empty()


@pytest.mark.parametrize("paused", [False, True])
def test_watchdog_expiry_clears_preview_once_and_preserves_automation(make_loop, paused):
    app, run = make_loop([FrameStep(10.0, hand_at())], paused=paused)
    run()
    run.clock.now = 10.251

    assert app._expire_tracking() is True
    run.clock.now = 11.0
    assert app._expire_tracking() is False

    app.mapper.mouse.release_all.assert_called_once()
    app.mapper.reset_temporal_state.assert_called_once()
    app.classifier.reset.assert_called_once()
    assert app._tracking_capture_time is None
    assert app.frame_queue.empty()
    assert app.automation_enabled is not paused
    assert app._tracking_generation == 1


def test_ui_watchdog_releases_before_blocked_inference_returns_and_discards_result(make_loop):
    first, late = hand_at(0.3), hand_at(0.7)
    app, run = make_loop([FrameStep(10.0, first), FrameStep(10.05, late)])
    app.ui = MagicMock(current_hands_data=first)
    entered_inference = threading.Event()
    finish_inference = threading.Event()
    returned_inference = threading.Event()
    worker_errors = []
    original_infer = app.detector.process_frame.side_effect

    def blocking_infer(frame, timestamp_ms):
        if timestamp_ms == 10050:
            entered_inference.set()
            if not finish_inference.wait(timeout=3.0):
                raise AssertionError("Test did not release blocked inference")
            returned_inference.set()
        return original_infer(frame, timestamp_ms)

    def worker_target():
        try:
            run()
        except BaseException as error:
            worker_errors.append(error)

    app.detector.process_frame.side_effect = blocking_infer
    worker = threading.Thread(target=worker_target, daemon=True)
    worker.start()
    try:
        assert entered_inference.wait(timeout=3.0), "Worker did not reach second inference"
        app.mapper.process.assert_called_once()
        app.mapper.mouse.release_all.assert_not_called()
        run.clock.now = 10.4

        # The UI runs independently while the worker is blocked in native inference.
        app.update_ui_loop()

        assert not returned_inference.is_set()
        app.mapper.mouse.release_all.assert_called_once()
        assert app.ui.current_hands_data == []
        app.ui.update_dashboard.assert_called_once()
        assert app.ui.update_dashboard.call_args.args[1:4] == ("Unknown", "Unknown", 0)
        app.ui.update_frame.assert_called_once()
        app.ui.after.assert_called_once_with(15, app.update_ui_loop)
        assert app.frame_queue.empty()
        assert app._tracking_capture_time is None
        assert app.automation_enabled is True
    finally:
        finish_inference.set()
        worker.join(timeout=3.0)

    assert not worker.is_alive(), "Scripted worker failed to finish"
    assert not worker_errors
    assert returned_inference.is_set()
    # The late result was captured before watchdog invalidation and must not act.
    app.detector.get_all_hands_data.assert_called_once()
    app.classifier.classify.assert_called_once_with(first)
    app.mapper.process.assert_called_once()
    assert_cleared(app.frame_queue.published[-1])
    assert app._tracking_capture_time is None
    assert app._tracking_generation == 1
