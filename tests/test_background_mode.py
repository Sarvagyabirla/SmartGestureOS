"""
test_background_mode.py — regression tests for the UI-freeze fix and for
Background Control Mode.

These lock in the measured behaviour recorded in docs/UI_FREEZE_ROOT_CAUSE.md:

  * the Tk tick is change-detected and rate-limited, not unconditional;
  * preview rendering is a latest-frame mailbox, never a backlog;
  * hiding the dashboard stops ALL preview work but never stops control;
  * every worker thread reaches Tk only through UiCommandQueue;
  * both hotkeys are independent and both are released on exit.
"""
import sys
import threading
import time
import queue
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui_commands import UiCommandQueue, PreviewBudget


# ── UiCommandQueue: the only sanctioned worker -> Tk path ─────────────────────

def test_command_queue_defers_every_call_until_drain():
    queue = UiCommandQueue()
    ran = []
    for i in range(3):
        queue.post(ran.append, i)

    assert ran == [], "commands must NOT run on the posting thread"
    assert queue.pending == 3
    assert queue.drain() == 3
    assert ran == [0, 1, 2]


def test_command_queue_from_a_worker_thread_never_touches_tk():
    """The real invariant: a worker thread can post, but cannot execute."""
    queue = UiCommandQueue()
    ran = []
    worker = threading.Thread(target=lambda: queue.post(ran.append, "from-worker"))
    worker.start()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert ran == [], "drain() must be required even for worker-thread posts"
    queue.drain()
    assert ran == ["from-worker"]


def test_command_queue_drops_stale_instead_of_blocking_the_caller():
    queue = UiCommandQueue(maxsize=2)
    started = time.perf_counter()
    for i in range(50):
        queue.post(lambda: None, i)

    assert time.perf_counter() - started < 0.5, "post() must never block"
    assert queue.pending == 2
    assert queue.dropped > 0


# ── UI: rendering is change-detected ─────────────────────────────────────────


# ── UiCommandQueue: the only sanctioned worker -> Tk path ─────────────────────


# ── UI: rendering is change-detected ─────────────────────────────────────────

def _bare_ui():
    """A SmartGestureApp-shaped double with recording widgets."""
    from src.ui import SmartGestureApp
    ui = object.__new__(SmartGestureApp)
    for name in ("mode_label", "raw_gesture_label", "gesture_label", "conf_label",
                 "fps_label", "latency_label", "cpu_label", "ram_label",
                 "camera_state_label", "automation_state_label", "pause_btn",
                 "background_status_label"):
        setattr(ui, name, MagicMock())
    ui.confidence_bar = MagicMock()
    ui.accent_color = "#00E5FF"
    ui.muted_text = "gray"
    ui.last_stat_update = 0.0
    ui.add_to_history = MagicMock()
    ui.hotkey_available = True
    ui.automation_enabled = False
    ui._is_resuming = False
    return ui


def test_repeated_identical_dashboard_updates_issue_no_tcl_calls():
    """THE freeze fix: a steady gesture must cost zero configure() calls.

    One priming call paints the current state and arms the cache; the 50
    steady-state ticks that follow must issue no Tcl round trips at all.
    """
    from src.ui import SmartGestureApp
    ui = _bare_ui()
    args = dict(mode="GENERAL", stable_gesture="Pointing", raw_gesture="Pointing",
                confidence=90, action=None, fps=29, cpu_usage=20.0, ram_usage=400.0,
                camera_on=True, avg_latency=40, automation_enabled=True)

    SmartGestureApp.update_dashboard(ui, **args)          # prime
    ui.last_stat_update = time.time()                    # skip the stat row
    for widget in (ui.mode_label, ui.gesture_label, ui.raw_gesture_label,
                   ui.conf_label, ui.camera_state_label,
                   ui.automation_state_label, ui.pause_btn):
        widget.configure.reset_mock()
    ui.confidence_bar.set.reset_mock()

    # The confidence bar is the one widget with a deliberate animation: it
    # eases from its previous value to the new one and then snaps. Let it
    # finish, re-arm, and only then measure the steady state.
    for _ in range(60):
        SmartGestureApp.update_dashboard(ui, **args)
    ui.confidence_bar.set.reset_mock()
    for widget in (ui.mode_label, ui.gesture_label, ui.raw_gesture_label,
                   ui.conf_label, ui.camera_state_label,
                   ui.automation_state_label, ui.pause_btn):
        widget.configure.reset_mock()

    for _ in range(50):
        SmartGestureApp.update_dashboard(ui, **args)

    ui.gesture_label.configure.assert_not_called()
    ui.raw_gesture_label.configure.assert_not_called()
    ui.conf_label.configure.assert_not_called()
    ui.mode_label.configure.assert_not_called()
    ui.camera_state_label.configure.assert_not_called()
    ui.automation_state_label.configure.assert_not_called()
    ui.pause_btn.configure.assert_not_called()
    ui.confidence_bar.set.assert_not_called()


def test_command_queue_survives_a_failing_command():
    queue = UiCommandQueue()
    ran = []
    queue.post(lambda: 1 / 0)
    queue.post(ran.append, "after")

    assert queue.drain() == 2
    assert ran == ["after"], "one bad command must not stall the queue"
    assert queue.failed == 1


def test_command_queue_clear_discards_pending_on_shutdown():
    queue = UiCommandQueue()
    queue.post(lambda: None)
    assert queue.clear() == 1
    assert queue.pending == 0


# ── PreviewBudget: latest-frame + rate limit, no Tk ──────────────────────────

class _Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_preview_budget_refuses_anything_while_hidden():
    clock = _Clock()
    budget = PreviewBudget(max_fps=30, clock=clock)

    for i in range(10):
        clock.now += 1.0
        assert budget.should_render(False, i) is False

    assert budget.rendered == 0
    assert budget.suppressed_hidden == 10


def test_preview_budget_is_latest_frame_not_backlog():
    clock = _Clock()
    budget = PreviewBudget(max_fps=30, clock=clock)   # one frame per 33.3 ms

    assert budget.should_render(True, 1) is True
    budget.mark_rendered(1)
    # Frames 2..6 all arrive inside the SAME preview interval. None of them may
    # render: they are dropped, not queued. This is the latest-frame mailbox
    # contract - the dashboard must never show a 2-second-old frame.
    for i in range(2, 7):
        clock.now += 0.001
        assert budget.should_render(True, i) is False
    assert budget.rendered == 1
    assert budget.throttled == 5

    # Once the interval elapses, the newest frame is accepted - and it is the
    # newest one, never a replay of frame 2.
    clock.now += 0.05
    assert budget.should_render(True, 7) is True
    budget.mark_rendered(7)
    assert budget.last_frame_id == 7


def test_preview_budget_rejects_a_duplicate_of_the_shown_frame():
    clock = _Clock()
    budget = PreviewBudget(max_fps=30, clock=clock)
    budget.should_render(True, 7)
    budget.mark_rendered(7)

    clock.now += 5.0
    assert budget.should_render(True, 7) is False
    assert budget.duplicates == 1


def test_preview_budget_invalidate_forces_the_next_frame_through():
    """A restore must not be blocked by the throttle from before the hide."""
    clock = _Clock()
    budget = PreviewBudget(max_fps=30, clock=clock)
    budget.should_render(True, 1)
    budget.mark_rendered(1)

    budget.invalidate()
    assert budget.should_render(True, 2) is True


def test_changed_dashboard_values_still_reach_the_widgets():
    from src.ui import SmartGestureApp
    ui = _bare_ui()
    SmartGestureApp.update_dashboard(
        ui, mode="GENERAL", stable_gesture="Pointing", raw_gesture="Pointing",
        confidence=90, action=None, fps=29, automation_enabled=True)
    ui.gesture_label.configure.assert_called_with(text="Pointing")

    SmartGestureApp.update_dashboard(
        ui, mode="DRAW", stable_gesture="Victory", raw_gesture="Victory",
        confidence=95, action=None, fps=29, automation_enabled=True)
    assert ui.gesture_label.configure.call_args.kwargs["text"] == "Victory"
    assert ui.mode_label.configure.call_args.kwargs["text"] == "DRAW"


def test_first_paint_is_never_skipped_by_the_change_cache():
    from src.ui import SmartGestureApp
    ui = _bare_ui()
    SmartGestureApp.update_dashboard(
        ui, mode="GENERAL", stable_gesture="Unknown", raw_gesture="Unknown",
        confidence=0, action=None, fps=0, automation_enabled=False)
    ui.automation_state_label.configure.assert_called()


# ── UI: background mode switches preview rendering off ───────────────────────

def test_hide_dashboard_disables_preview_and_show_reenables_it():
    from src.ui import SmartGestureApp
    ui = _bare_ui()
    ui._dashboard_visible = True
    ui._preview_enabled = True
    ui.preview_budget = PreviewBudget(max_fps=30)
    ui.withdraw = MagicMock()
    ui.deiconify = MagicMock()
    ui.lift = MagicMock()
    ui.focus_force = MagicMock()
    ui._set_background_status = MagicMock()

    SmartGestureApp.set_dashboard_visible(ui, False)
    assert ui._preview_enabled is False
    assert ui.dashboard_visible is False
    ui.withdraw.assert_called_once()

    SmartGestureApp.set_dashboard_visible(ui, True)
    assert ui._preview_enabled is True
    ui.deiconify.assert_called_once()
    ui.lift.assert_called_once()


def test_restore_discards_frames_queued_while_hidden():
    """No stale preview may flash when the dashboard comes back."""
    from src.ui import SmartGestureApp
    clock = _Clock()
    ui = _bare_ui()
    ui._dashboard_visible = True
    ui._preview_enabled = True
    ui.preview_budget = PreviewBudget(max_fps=30, clock=clock)
    ui.withdraw = MagicMock()
    ui.deiconify = MagicMock()
    ui.lift = MagicMock()
    ui.focus_force = MagicMock()
    ui._set_background_status = MagicMock()

    ui.preview_budget.should_render(True, 1)
    ui.preview_budget.mark_rendered(1)

    SmartGestureApp.set_dashboard_visible(ui, False)
    clock.now += 0.001
    assert ui.preview_budget.should_render(True, 2) is False, "hidden -> no render"

    SmartGestureApp.set_dashboard_visible(ui, True)
    assert ui.preview_budget.should_render(True, 3) is True, "restore must not be throttled"


def test_hidden_dashboard_renders_nothing_at_all():
    """No cvtColor, no PIL, no ImageTk while hidden - the CPU saving."""
    from src.ui import SmartGestureApp
    ui = _bare_ui()
    ui._preview_enabled = False
    ui.preview_budget = PreviewBudget(max_fps=30)
    ui.video_label = MagicMock()
    ui.current_imgtk = None
    ui.frames_rendered = 0
    ui.frames_suppressed_hidden = 0

    for _ in range(20):
        SmartGestureApp.update_frame(ui, np.zeros((720, 1280, 3), dtype=np.uint8))

    ui.video_label.configure.assert_not_called()
    assert ui.current_imgtk is None, "a hidden dashboard must not build PhotoImages"
    assert ui.frames_rendered == 0
    assert ui.frames_suppressed_hidden == 20


def test_visible_dashboard_keeps_exactly_one_photimage_reference():
    """PhotoImage must not accumulate: each render replaces the reference.

    Uses a real Tk window because ImageTk needs a live interpreter. The
    rate limiter is driven by an injected clock so the test never depends on
    how fast the machine happens to execute it.
    """
    from src.ui import SmartGestureApp
    clock = _Clock()
    ui = SmartGestureApp(set_automation_callback=lambda enabled: None)
    try:
        ui.geometry("1100x700")
        ui.update_idletasks()
        ui.frame_width, ui.frame_height = 320, 240
        ui.preview_budget = PreviewBudget(max_fps=30, clock=clock)
        ui.frames_rendered = 0

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        SmartGestureApp.update_frame(ui, frame.copy(), frame_id=1)
        assert ui.frames_rendered == 1
        first = ui.current_imgtk
        assert first is not None

        # A genuinely new frame must render and REPLACE the single
        # `current_imgtk` slot. PhotoImage objects must not accumulate.
        clock.now += 0.05
        SmartGestureApp.update_frame(ui, frame.copy(), frame_id=2)
        assert ui.frames_rendered == 2
        assert ui.current_imgtk is not first

        # A repeated frame id is suppressed even after the rate limit has
        # elapsed, so a stalled producer cannot make the dashboard repaint the
        # identical image.
        clock.now += 0.05
        before = ui.frames_rendered
        SmartGestureApp.update_frame(ui, frame, frame_id=2)
        assert ui.frames_rendered == before, "a repeated frame id must not re-render"
        assert ui.preview_budget.duplicates == 1
    finally:
        try:
            ui.destroy()
        except Exception:
            pass


def test_close_button_is_predictable_and_never_traps_the_user():
    from src.ui import SmartGestureApp
    ui = _bare_ui()
    ui._minimize_to_tray = True
    ui._dashboard_visible = True
    ui.set_dashboard_visible = MagicMock()
    ui.force_quit = MagicMock()

    SmartGestureApp.on_window_close(ui)
    ui.set_dashboard_visible.assert_called_with(False)
    ui.force_quit.assert_not_called()

    ui.set_dashboard_visible.reset_mock()
    ui._minimize_to_tray = False
    SmartGestureApp.on_window_close(ui)
    ui.force_quit.assert_called_once()


# ── MainApp: background mode is a view change, never a control change ────────

def _main_app_double():
    """A MainApp-shaped double: no camera, no Tk, no threads."""
    import main as main_module
    app = object.__new__(main_module.MainApp)
    app.ui = MagicMock(dashboard_visible=True, current_hands_data=[])
    app.ui_commands = UiCommandQueue()
    app.camera = MagicMock(is_connected=True)
    app.mapper = MagicMock(mode="GENERAL", is_sleeping=False)
    app.detector = MagicMock(available=True, error=None,
                              average_inference_latency=5.0)
    app._automation_enabled = True
    app._tracking_generation = 0
    app._tracking_capture_time = None
    app._rearm_state = main_module.MainApp._REARM_ARMED
    app._hotkey_handle = None
    app._restore_hotkey_handle = None
    app.running = False
    app._shutdown_started = False
    app._shutdown_lock = threading.Lock()
    app._automation_lock = threading.RLock()
    app.classifier = MagicMock()
    app.fps_history = []
    app.latency_history = []
    app.frame_queue = queue.Queue(maxsize=1)
    app.process_thread = None
    app.stats_thread = None
    app.tray_icon = None
    app.tray_thread = None
    return app


def test_hiding_the_dashboard_never_touches_the_control_pipeline():
    """THE contract: background mode is a VIEW change only."""
    app = _main_app_double()
    app.mapper.mouse = MagicMock()

    app.hide_dashboard()
    app.ui_commands.drain()

    app.ui.set_dashboard_visible.assert_called_once_with(False)
    app.camera.stop.assert_not_called()
    app.mapper.mouse.release_all.assert_not_called()
    app.detector.close.assert_not_called()
    assert app.running is False            # unchanged by a view operation
    assert app._automation_enabled is True  # automation is untouched


def test_restoring_the_dashboard_from_a_worker_thread_only_posts():
    """A hotkey/tray thread must not execute Tk work itself."""
    app = _main_app_double()
    restored = []

    app._show_dashboard_on_tk_thread = lambda: (
        restored.append("restored"), app.ui.set_dashboard_visible(True))
    errors = []

    def worker():
        try:
            app.show_dashboard()      # called from a non-Tk thread
        except Exception as exc:      # pragma: no cover - failure detail
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=2.0)

    assert not errors, f"show_dashboard() must be safe off-thread: {errors}"
    assert restored == [], "the worker thread must not have executed Tk work"
    app.ui_commands.drain()
    assert restored == ["restored"]


def test_restore_hotkey_and_pause_hotkey_are_separate_combinations():
    import main as main_module
    assert main_module.RESTORE_HOTKEY == "ctrl+alt+shift+g"
    assert main_module.RESTORE_HOTKEY != "ctrl+alt+g", (
        "Ctrl+Alt+G is reserved for emergency Pause/Resume and must not be "
        "overloaded with dashboard restore"
    )


def test_dashboard_visible_is_readable_without_a_tk_mainloop():
    app = _main_app_double()
    assert app.dashboard_visible is True
    app.ui.dashboard_visible = False
    assert app.dashboard_visible is False

    # A broken UI must not take the control engine down.
    type(app.ui).dashboard_visible = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("no Tk")))
    try:
        assert app.dashboard_visible is True
    finally:
        del type(app.ui).dashboard_visible


# ── Pointer filter: group delay must stay inside the usability budget ────────

def _group_delay_ms(cutoff_hz, sample_hz):
    """First-order low-pass group delay of the One Euro smoothing step."""
    import math
    dt = 1.0 / sample_hz
    r = 2 * math.pi * cutoff_hz * dt
    a = r / (r + 1)
    return ((1 - a) / (2 * math.pi * cutoff_hz)) * 1000.0


@pytest.mark.parametrize("smoothing", list(range(1, 21)))
def test_pointer_filter_never_adds_a_freezing_group_delay(smoothing):
    """The old 0.55 Hz end cost ~290 ms and made the cursor look frozen.

    Budget: no slider position may add more than ~100 ms of filter delay, at
    either the measured ~15 FPS detector cadence or a fast 30 FPS camera.
    """
    from src.mouse_controller import MouseController
    cutoff = MouseController._smoothing_cutoff(smoothing)
    for sample_hz in (15.0, 30.0):
        delay = _group_delay_ms(cutoff, sample_hz)
        assert delay < 100.0, (
            f"smoothing={smoothing} -> {cutoff:.2f} Hz -> {delay:.0f} ms delay "
            f"at {sample_hz:.0f} FPS; the cursor would visibly trail the hand")


def test_pointer_smoothing_ordering_is_preserved():
    """Higher smoothing must still mean more smoothing, just within budget."""
    from src.mouse_controller import MouseController
    cutoffs = [MouseController._smoothing_cutoff(s) for s in range(1, 21)]
    assert all(a > b for a, b in zip(cutoffs, cutoffs[1:])), \
        "smoothing slider must be monotonically smoother as it increases"
    assert cutoffs[0] > cutoffs[-1]


def test_live_profile_smoothing_value_stays_responsive():
    """The shipped default profile must not be a laggy setting."""
    from src.mouse_controller import MouseController
    from config import SETTINGS
    smoothing = int(SETTINGS.get("gestures", {}).get("smoothing", 2))
    cutoff = MouseController._smoothing_cutoff(smoothing)
    assert _group_delay_ms(cutoff, 15.0) < 100.0


def test_shutdown_releases_both_hotkey_handles():
    import keyboard
    app = _main_app_double()
    removed = []
    original = keyboard.remove_hotkey
    keyboard.remove_hotkey = lambda handle: removed.append(handle)
    try:
        app._hotkey_handle = "pause-handle"
        app._restore_hotkey_handle = "restore-handle"
        app.stop_system()
    finally:
        keyboard.remove_hotkey = original

    assert removed == ["pause-handle", "restore-handle"], (
        "both hotkeys must be released or the keyboard hook outlives the app")
    assert app._hotkey_handle is None
    assert app._restore_hotkey_handle is None
    assert app.ui_commands.pending == 0
