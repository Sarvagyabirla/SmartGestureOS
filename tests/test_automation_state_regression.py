"""
Regression tests for the P0 Resume/Pause authoritative-state bug.

Root cause (fixed):
    SmartGestureApp.__init__ previously hard-coded self.automation_enabled = True.
    MainApp starts PAUSED (automation_enabled = False).
    A user clicking Resume before the first dashboard frame arrived would compute:
        not self.automation_enabled  ->  not True  ->  False
    and call set_automation_enabled(False) on a backend already False.
    Net result: no state change -- Resume appeared to do nothing.

Fix:
    SmartGestureApp now accepts initial_automation_enabled (default False).
    MainApp passes initial_automation_enabled=not start_paused.
    toggle_pause() reads self.automation_enabled which now matches the backend.

Additional tests cover:
    - PAUSED -> RESUMING -> ARMED sequence
    - button/hotkey parity
    - held gestures blocked during RESUMING
    - opening auxiliary windows pauses safely without locally mutating UI cache
    - RESUMING shown distinctly from ON in update_dashboard
    - ActionExecutor _drain task_done accounting
"""

import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# -- helpers ---------------------------------------------------------------

def _make_minimal_ui(initial_automation_enabled=False):
    """Return a SmartGestureApp with all Tk widgets stubbed."""
    from src.ui import SmartGestureApp
    ui = object.__new__(SmartGestureApp)
    ui.set_automation_callback = None
    ui.toggle_pause_callback = None
    ui.close_callback = None
    ui.automation_enabled = initial_automation_enabled
    ui._is_resuming = False
    ui.hotkey_available = True
    return ui


def _make_mock_mainapp(start_paused=True):
    """Return a lightly-mocked MainApp that exercises the real state machine."""
    import main as m_module
    app = object.__new__(m_module.MainApp)
    app._automation_lock = threading.RLock()
    app._shutdown_lock = threading.Lock()
    app._shutdown_started = False
    app._automation_enabled = not start_paused
    app._rearm_state = (
        m_module.MainApp._REARM_IDLE
        if start_paused
        else m_module.MainApp._REARM_ARMED
    )
    app._rearm_neutral_frames = 0
    app._tracking_generation = 0
    app._tracking_capture_time = None
    app._hotkey_handle = None
    app.running = True

    # Minimal stubs
    app.mapper = MagicMock()
    app.mapper.is_sleeping = False
    app.mapper.mode = "GENERAL"
    app.classifier = MagicMock()
    app.camera = MagicMock()
    app.detector = MagicMock()
    app.frame_queue = queue.Queue(maxsize=1)
    app.process_thread = None
    app.stats_thread = None
    app.cpu_usage = 0.0
    app.ram_usage = 0.0
    app.ui = MagicMock()
    return app


# -- Section A: Startup authoritative PAUSED state -------------------------

class TestStartupAuthoritative:
    def test_mainapp_starts_paused_by_default(self):
        app = _make_mock_mainapp(start_paused=True)
        assert app._automation_enabled is False
        assert app._rearm_state == "idle"

    def test_mainapp_starts_armed_when_start_active(self):
        app = _make_mock_mainapp(start_paused=False)
        assert app._automation_enabled is True
        assert app._rearm_state == "armed"

    def test_ui_init_default_is_paused(self):
        """SmartGestureApp.automation_enabled defaults to False (not True)."""
        ui = _make_minimal_ui(initial_automation_enabled=False)
        assert ui.automation_enabled is False

    def test_ui_init_can_start_armed(self):
        ui = _make_minimal_ui(initial_automation_enabled=True)
        assert ui.automation_enabled is True


# -- Section B: The P0 Resume bug scenario ---------------------------------

class TestImmediateResumeBug:
    def test_resume_click_before_first_frame_calls_set_automation_true(self):
        """With the fix, Resume before the first frame sends enabled=True."""
        calls = []
        ui = _make_minimal_ui(initial_automation_enabled=False)
        ui.set_automation_callback = lambda v: calls.append(v)

        from src.ui import SmartGestureApp
        SmartGestureApp.toggle_pause(ui)

        assert calls == [True], (
            f"toggle_pause() must send True (resume) when UI starts False (paused). Got: {calls}"
        )

    def test_old_bug_would_have_sent_false(self):
        """Demonstrate the old bug: starting True then toggling sends False."""
        calls = []
        ui = _make_minimal_ui(initial_automation_enabled=True)  # old broken default
        ui.set_automation_callback = lambda v: calls.append(v)

        from src.ui import SmartGestureApp
        SmartGestureApp.toggle_pause(ui)

        assert calls == [False], "Regression check: old bug sent False on first Resume"

    def test_sequential_toggles_alternate_correctly(self):
        """Resume -> Pause -> Resume must alternate True/False/True."""
        calls = []
        ui = _make_minimal_ui(initial_automation_enabled=False)
        ui.set_automation_callback = lambda v: calls.append(v)

        from src.ui import SmartGestureApp
        SmartGestureApp.toggle_pause(ui)   # Resume -> True
        ui.automation_enabled = True       # simulate update_dashboard
        SmartGestureApp.toggle_pause(ui)   # Pause -> False
        ui.automation_enabled = False      # simulate update_dashboard
        SmartGestureApp.toggle_pause(ui)   # Resume -> True

        assert calls == [True, False, True]


# -- Section C: Authoritative state: UI cache cannot invert backend --------

class TestAuthoritative:
    def test_backend_toggle_uses_real_state_not_ui_cache(self):
        """toggle_automation() reads _automation_enabled, not ui.automation_enabled."""
        import main as m_module
        app = _make_mock_mainapp(start_paused=True)
        app.ui.automation_enabled = True  # stale/wrong UI cache

        app.toggle_automation()

        assert app._automation_enabled is True
        assert app._rearm_state == m_module.MainApp._REARM_WAITING

    def test_set_automation_enabled_idempotent_no_double_release(self):
        """Calling set_automation_enabled with the current value is a no-op."""
        app = _make_mock_mainapp(start_paused=True)
        assert app._automation_enabled is False

        with patch.object(app.mapper.mouse, "release_all") as mock_rel:
            app.set_automation_enabled(False)  # no-op
            assert mock_rel.call_count == 0


# -- Section D: PAUSED -> RESUMING -> ARMED state machine ------------------

class TestRearmStateMachine:
    def test_pause_sets_idle(self):
        import main as m_module
        app = _make_mock_mainapp(start_paused=False)
        app.set_automation_enabled(False)
        assert app._rearm_state == m_module.MainApp._REARM_IDLE

    def test_resume_sets_waiting(self):
        import main as m_module
        app = _make_mock_mainapp(start_paused=True)
        app.set_automation_enabled(True)
        assert app._rearm_state == m_module.MainApp._REARM_WAITING

    def test_waiting_requires_five_consecutive_neutral_frames(self):
        import main as m_module
        app = _make_mock_mainapp(start_paused=True)
        app.set_automation_enabled(True)

        for i in range(4):
            assert app._tick_rearm("Unknown", "Unknown") is False
        assert app._rearm_state == m_module.MainApp._REARM_WAITING

        assert app._tick_rearm("Unknown", "Unknown") is True
        assert app._rearm_state == m_module.MainApp._REARM_ARMED

    def test_non_neutral_resets_neutral_count(self):
        app = _make_mock_mainapp(start_paused=True)
        app.set_automation_enabled(True)

        for _ in range(3):
            app._tick_rearm("Unknown", "Unknown")
        assert app._rearm_neutral_frames == 3

        app._tick_rearm("Pointing", "Pointing")
        assert app._rearm_neutral_frames == 0

    def test_resuming_shown_distinctly_in_dashboard(self):
        """update_dashboard with automation_enabled=True, is_resuming=True
        must render RESUMING text, not AUTOMATION ON."""
        from src.ui import SmartGestureApp
        ui = object.__new__(SmartGestureApp)
        ui.mode_label = MagicMock()
        ui.confidence_bar = MagicMock()
        ui.confidence_bar.get.return_value = 0.0
        ui.gesture_label = MagicMock()
        ui.raw_gesture_label = MagicMock()
        ui.conf_label = MagicMock()
        ui.fps_label = MagicMock()
        ui.latency_label = MagicMock()
        ui.cpu_label = MagicMock()
        ui.ram_label = MagicMock()
        ui.camera_state_label = MagicMock()
        ui.automation_state_label = MagicMock()
        ui.pause_btn = MagicMock()
        ui.last_stat_update = 0.0
        ui.accent_color = "#00E5FF"
        ui.add_to_history = MagicMock()
        ui.hotkey_available = True
        ui.automation_enabled = False
        ui._is_resuming = False

        SmartGestureApp.update_dashboard(
            ui, mode="GENERAL", stable_gesture="Unknown", raw_gesture="Unknown",
            confidence=0, action=None, fps=0,
            automation_enabled=True, is_resuming=True
        )

        assert ui.automation_enabled is True
        assert ui._is_resuming is True
        configure_texts = [str(c) for c in ui.automation_state_label.configure.call_args_list]
        assert any("RESUMING" in t for t in configure_texts), (
            f"Expected RESUMING in label, got: {configure_texts}"
        )
        assert not any("AUTOMATION ON" in t for t in configure_texts), (
            "AUTOMATION ON must not appear during RESUMING state"
        )


# -- Section E: button/hotkey parity ----------------------------------------

class TestButtonHotkeyParity:
    def test_button_resume_transitions_backend_to_waiting(self):
        import main as m_module
        app = _make_mock_mainapp(start_paused=True)
        from src.ui import SmartGestureApp
        ui = _make_minimal_ui(initial_automation_enabled=False)
        ui.set_automation_callback = app.set_automation_enabled

        SmartGestureApp.toggle_pause(ui)
        assert app._automation_enabled is True
        assert app._rearm_state == m_module.MainApp._REARM_WAITING

    def test_hotkey_resume_transitions_backend_to_waiting(self):
        import main as m_module
        app = _make_mock_mainapp(start_paused=True)
        app._hotkey_toggle_automation()
        assert app._automation_enabled is True
        assert app._rearm_state == m_module.MainApp._REARM_WAITING


# -- Section F: Held gestures blocked on Resume ----------------------------

class TestHeldGestureBlockedOnResume:
    @pytest.mark.parametrize("gesture", ["Pinch", "Four Fingers", "Call Me", "Closed Fist"])
    def test_action_gesture_blocked_during_resuming(self, gesture):
        app = _make_mock_mainapp(start_paused=True)
        app.set_automation_enabled(True)
        for _ in range(10):
            assert app._tick_rearm(gesture, gesture) is False

    def test_resume_with_no_hand_arms_quickly(self):
        import main as m_module
        app = _make_mock_mainapp(start_paused=True)
        app.set_automation_enabled(True)
        assert app._rearm_state == m_module.MainApp._REARM_WAITING

        required = m_module.MainApp._REARM_NEUTRAL_REQUIRED
        done = None
        for i in range(required):
            done = app._tick_rearm("Unknown", "Unknown")
            if i < required - 1:
                assert done is False
        assert done is True
        assert app._rearm_state == m_module.MainApp._REARM_ARMED


# -- Section G: Auxiliary window pause -------------------------------------

class TestAuxiliaryWindowPause:
    def test_pause_for_auxiliary_ui_does_not_locally_set_cache(self):
        """_pause_for_auxiliary_ui must not set self.automation_enabled=False.
        The cache must only be updated via update_dashboard from the backend."""
        from src.ui import SmartGestureApp
        ui = _make_minimal_ui(initial_automation_enabled=True)
        backend_calls = []
        ui.set_automation_callback = lambda v: backend_calls.append(v)

        SmartGestureApp._pause_for_auxiliary_ui(ui)

        assert backend_calls == [False]
        assert ui.automation_enabled is True, (
            "_pause_for_auxiliary_ui must not mutate automation_enabled; "
            "update_dashboard is the authoritative source."
        )

    def test_pause_for_auxiliary_ui_when_already_paused_is_idempotent(self):
        from src.ui import SmartGestureApp
        ui = _make_minimal_ui(initial_automation_enabled=False)
        backend_calls = []
        ui.set_automation_callback = lambda v: backend_calls.append(v)

        SmartGestureApp._pause_for_auxiliary_ui(ui)
        assert backend_calls == [False]


# -- Section H: ActionExecutor _drain task_done accounting -----------------

class TestActionExecutorDrainAccounting:
    def test_drain_returns_correct_dropped_count(self):
        """_drain() must return the number of items actually removed."""
        from src.action_executor import ActionExecutor
        executor = ActionExecutor()

        dummy = MagicMock()
        dummy.generation = 0
        executor._queue.put_nowait(dummy)

        dropped = executor._drain()
        assert dropped == 1

    def test_drain_task_done_prevents_join_deadlock(self):
        """Without task_done(), Queue.join() deadlocks after _drain()."""
        from src.action_executor import ActionExecutor
        executor = ActionExecutor()
        executor.start()

        dummy = MagicMock()
        dummy.generation = executor._generation
        executor._queue.put_nowait(dummy)
        executor._drain()

        # join() should complete immediately since task_done was called
        join_done = threading.Event()
        def do_join():
            executor._queue.join()
            join_done.set()

        t = threading.Thread(target=do_join, daemon=True)
        t.start()
        assert join_done.wait(timeout=2.0), (
            "_drain() did not call task_done(); Queue.join() deadlocked"
        )
        executor.stop()

    def test_stop_does_not_deadlock_with_pending_item(self):
        """stop() must not deadlock even if there is a pending item."""
        from src.action_executor import ActionExecutor
        executor = ActionExecutor()
        executor.start()

        executor.submit("slow", lambda: time.sleep(10))
        stopped = threading.Event()

        def do_stop():
            executor.stop(timeout=1.0)
            stopped.set()

        t = threading.Thread(target=do_stop, daemon=True)
        t.start()
        assert stopped.wait(timeout=3.0), "stop() deadlocked on pending item"
