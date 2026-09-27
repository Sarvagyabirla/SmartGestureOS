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

        def route(hands, stable, raw, frame, *, render_canvas=True, capture_at=None):
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


@pytest.mark.parametrize("paused,lose_hand", [(False, False), (True, False), (False, True)])
def test_draw_artwork_persists_between_inferences_while_paused_and_after_hand_loss(
    make_loop, monkeypatch, paused, lose_hand,
):
    from src.drawing import DrawingCanvas
    from src.gesture_mapper import GestureMapper

    hand = hand_at()
    app, run = make_loop([
        FrameStep(10.0, hand), FrameStep(10.01, hand),
        FrameStep(10.05, [] if lose_hand else hand),
        FrameStep(10.06, [] if lose_hand else hand),
    ], paused=paused)
    app.mapper.mode = "DRAW"
    app.mapper.canvas = DrawingCanvas(80, 60)
    app.mapper.canvas.canvas[0, 0] = (255, 0, 255)
    app.mapper.canvas.get_overlay = MagicMock(wraps=app.mapper.canvas.get_overlay)
    app.mapper.get_sleep_gesture.return_value = None
    monkeypatch.setattr("src.gesture_mapper.SETTINGS", {"mappings": {"DRAW": {}}})
    # Use production DRAW routing with only the OS controllers mocked.
    app.mapper.process.side_effect = lambda *args, **kwargs: GestureMapper.process(app.mapper, *args, **kwargs)

    observations = run()

    assert [item[0][0, 0].tolist() for item in observations] == [[255, 0, 255]] * 4
    assert app.mapper.canvas.get_overlay.call_count == 4  # Exactly one composite per preview.
    assert app.detector.process_frame.call_count == 2
    assert app.mapper.process.call_count == (0 if paused else 2)
    if lose_hand:
        assert observations[-1][1] == []


def test_pause_status_is_visible_above_retained_drawing(make_loop):
    from src.drawing import DrawingCanvas

    app, run = make_loop([FrameStep(10.0, hand_at())], paused=True)
    app.mapper.mode = "DRAW"
    app.mapper.canvas = DrawingCanvas(80, 60)
    app.mapper.canvas.canvas[:] = (255, 0, 255)

    frame = run()[0][0]

    assert frame[0, 0].tolist() == [255, 0, 255]
    assert np.any(np.all(frame == (0, 0, 255), axis=2))  # Red pause text above the artwork.
    app.mapper.process.assert_not_called()


def test_resume_does_not_treat_low_confidence_held_pose_as_neutral(make_loop):
    app, run = make_loop([
        FrameStep(10.0 + i * 0.05, hand_at()) for i in range(8)
    ], paused=True)
    app.set_automation_enabled(True)
    # The classifier preserves its raw pose when confidence suppresses the
    # stable result. Holding that pose has not satisfied the release gate.
    app.classifier.classify.side_effect = lambda hands: GestureResult(
        "Unknown", "Pinch", 40.0, 100.0, "Low confidence"
    )

    run()

    assert app._rearm_state == app._REARM_WAITING
    assert app._rearm_neutral_frames == 0
    app.mapper.process.assert_not_called()


def test_inference_preserves_camera_aspect_ratio(make_loop):
    app, run = make_loop([FrameStep(10.0, hand_at())])

    run()

    # The scripted camera is 4:3. Stretching it to 640x360 distorts hand geometry.
    inference_frame = app.detector.process_frame.call_args.args[0]
    height, width = inference_frame.shape[:2]
    assert width / height == pytest.approx(4 / 3)
    assert max(width, height) <= 640


def test_detector_rate_counts_fresh_inference_not_preview_frames(make_loop):
    app, run = make_loop([
        FrameStep(10.0, hand_at()), FrameStep(10.01, hand_at()),
        FrameStep(10.05, hand_at()), FrameStep(10.06, hand_at()),
        FrameStep(10.10, hand_at()),
    ])

    run()

    assert app.detector_fps == pytest.approx(20.0)
    assert app.detector.process_frame.call_count == 3


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
    assert app._tracking_capture_time is None
    assert app._tracking_generation == 1


# ── Automation lock scope (Phase 4.2) ──────────────────────────────────────
# mapper.process() reaches ImageGrab, subprocess.Popen and pycaw, which can
# block for hundreds of milliseconds. Holding _automation_lock across it
# blocked the Tk thread (which also needs that lock) and appeared to freeze
# the application, and it left the tracking watchdog reading a stale capture
# timestamp. The lock must cover short state transitions only.


def _blocking_route(entered, release):
    def route(hands, stable, raw, frame, **kwargs):
        entered.set()
        if not release.wait(timeout=5.0):
            raise AssertionError("Test did not release the blocked action")
        return frame, "Executed: slow_action", 1.0

    return route


def _run_in_thread(app, run):
    errors = []

    def worker():
        try:
            run()
        except BaseException as exc:  # ScriptFinished ends the script
            errors.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread, errors


def test_slow_action_does_not_hold_the_automation_lock(make_loop):
    app, run = make_loop([FrameStep(10.0, hand_at())])
    app.ui = MagicMock(current_hands_data=[])
    entered, release = threading.Event(), threading.Event()
    app.mapper.process.side_effect = _blocking_route(entered, release)

    thread, errors = _run_in_thread(app, run)
    try:
        assert entered.wait(timeout=3.0), "routing never started"
        acquired = threading.Event()

        def try_lock():
            with app._automation_lock:
                acquired.set()

        probe = threading.Thread(target=try_lock, daemon=True)
        probe.start()
        probe.join(timeout=2.0)
        assert acquired.is_set(), (
            "_automation_lock was held across a slow action; the UI thread "
            "would block for the whole duration"
        )
    finally:
        release.set()
        thread.join(timeout=3.0)

    assert not errors or isinstance(errors[0], BaseException)


def test_pause_during_a_slow_action_invalidates_its_result(make_loop):
    """A pause that lands while an action is running must discard that action."""
    app, run = make_loop([FrameStep(10.0, hand_at())])
    app.ui = MagicMock(current_hands_data=[])
    entered, release = threading.Event(), threading.Event()
    app.mapper.process.side_effect = _blocking_route(entered, release)

    thread, errors = _run_in_thread(app, run)
    published = None
    try:
        assert entered.wait(timeout=3.0), "routing never started"
        # Pause lands while the slow action is still inside mapper.process.
        app.set_automation_enabled(False)
        release.set()
        thread.join(timeout=3.0)
        published = app.frame_queue.published[-1]
    finally:
        release.set()
        thread.join(timeout=3.0)

    assert published[6] != "Executed: slow_action", (
        "a stale action result was published after Pause"
    )
    assert app._tracking_generation == 1
