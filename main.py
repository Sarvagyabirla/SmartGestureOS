import time
import cv2
import threading
import queue
import psutil
import os
import collections
from pathlib import Path
from config import SETTINGS
from src.camera import Camera
from src.gesture_detector import GestureDetector
from src.gesture_classifier import GestureClassifier
from src.gesture_mapper import GestureMapper
from src.ui import SmartGestureApp
from src.models import AppStateSnapshot
from src.ui_commands import UiCommandQueue
from src.logger import logger

#: Restore the hidden dashboard. Deliberately NOT Ctrl+Alt+G: that hotkey is
#: reserved for emergency Pause/Resume and must stay reachable when no window
#: is visible. Ctrl+Alt+Shift+G is an unused Windows combination and gives
#: the user a way back into the UI even if the tray icon is unavailable.
RESTORE_HOTKEY = "ctrl+alt+shift+g"

try:
    import pystray
    from PIL import Image
    _HAS_PYSTRAY = True
except ImportError:
    _HAS_PYSTRAY = False


class MainApp:
    # ── Re-arm states (§7) ────────────────────────────────────────────────────
    _REARM_IDLE     = "idle"        # automation off (just paused)
    _REARM_WAITING  = "waiting"     # waiting for neutral before arming
    _REARM_ARMED    = "armed"       # full automation active
    _REARM_NEUTRAL_REQUIRED: int = 5  # frames of neutral required to arm

    def __init__(self, start_paused: bool = True):
        """Production startup is PAUSED by default.

        Camera and landmarks stay live so the user can position their hand,
        but no Windows action can fire until they deliberately Resume (button
        or Ctrl+Alt+G) and neutral re-arm completes. Starting armed risks a
        random action while the hand is still moving into position.
        """
        self.camera = Camera(
            index=SETTINGS["camera"]["index"],
            width=SETTINGS["camera"]["width"],
            height=SETTINGS["camera"]["height"],
            fps=SETTINGS["camera"]["fps"],
        )

        self.detector = GestureDetector()
        self.classifier = GestureClassifier()

        self.mapper = GestureMapper(
            SETTINGS["camera"]["width"],
            SETTINGS["camera"]["height"],
        )

        self.fps_history = collections.deque(maxlen=30)
        self.latency_history: collections.deque = collections.deque(maxlen=30)

        # Snapshot & Preview state for explicit UI providers
        self._state_lock = threading.RLock()
        self._preview_lock = threading.Lock()
        self._latest_preview_frame = None
        self._latest_preview_frame_id = -1
        self._latest_hands_data = []
        self._latest_raw_gesture = "Unknown"
        self._latest_stable_gesture = "Unknown"
        self._latest_confidence = 0
        self._latest_action = None
        self._detector_fps = 0.0
        self._pointer_fps = 0.0
        self._inference_ms = 0.0
        self._frame_age_ms = 0.0

        self.ui = SmartGestureApp(
            close_callback=self.stop_system,
            toggle_pause_callback=self.toggle_automation,
            set_automation_callback=self.set_automation_enabled,
            # Match UI initial state to authoritative backend: production starts
            # PAUSED, so start_paused=True → initial_automation_enabled=False.
            # This prevents toggle_pause() from computing (not True) = False
            # before the first dashboard frame arrives (the P0 Resume bug).
            initial_automation_enabled=not start_paused,
            set_mode_callback=self.set_mode,
            get_state_callback=self.get_state_snapshot,
            get_latest_preview_callback=self.get_latest_preview,
            show_dashboard_callback=self.show_dashboard,
            hide_dashboard_callback=self.hide_dashboard,
            quit_callback=self.stop_system,
        )

        # Pipeline state
        self.running: bool = False
        self.frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self.process_thread: threading.Thread | None = None
        self.stats_thread: threading.Thread | None = None
        self.tray_thread: threading.Thread | None = None
        self.tray_icon = None

        self.cpu_usage: float = 0.0
        self.ram_usage: float = 0.0

        self._was_camera_connected: bool = False

        # ── Automation state (§5) ─────────────────────────────────────────────
        # Thread-safe: protected by _automation_lock.
        # Only set_automation_enabled() mutates _automation_enabled.
        self._automation_lock = threading.RLock()
        self._automation_enabled: bool = not start_paused
        self._rearm_state: str = self._REARM_IDLE if start_paused else self._REARM_ARMED
        self._rearm_neutral_frames: int = 0
        self._tracking_generation: int = 0
        self._tracking_capture_time: float | None = None

        # Shutdown guard (§47)
        self._shutdown_started: bool = False
        self._shutdown_lock: threading.Lock = threading.Lock()

        # Global hotkey (§5) — store handles for cleanup.
        # Two independent hotkeys, never overloaded:
        #   Ctrl+Alt+G        -> Pause / Resume automation (emergency stop)
        #   Ctrl+Alt+Shift+G  -> show the hidden dashboard
        # Both must work while the dashboard is hidden, which is why they are
        # registered globally with the `keyboard` library rather than bound to
        # a Tk widget.
        self._hotkey_handle = None
        self._restore_hotkey_handle = None
        self.ui_commands = UiCommandQueue()
        try:
            import keyboard
            self._hotkey_handle = keyboard.add_hotkey(
                "ctrl+alt+g", self._hotkey_toggle_automation
            )
            is_listening = getattr(getattr(keyboard, "_listener", None), "listening", False)
            logger.info(
                f"Ctrl+Alt+G hotkey registered. Handle={repr(self._hotkey_handle)}, "
                f"ListenerActive={is_listening}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to bind Ctrl+Alt+G hotkey: {e} — "
                "Global shortcut unavailable; UI pause button still works."
            )

        try:
            import keyboard
            self._restore_hotkey_handle = keyboard.add_hotkey(
                RESTORE_HOTKEY, self._hotkey_restore_dashboard
            )
            logger.info(f"{RESTORE_HOTKEY.upper()} dashboard-restore hotkey registered.")
        except Exception as e:
            # Not fatal: the tray icon and the taskbar button remain available.
            logger.warning(f"Failed to bind {RESTORE_HOTKEY}: {e} — "
                           "use the tray icon or taskbar to restore the dashboard.")

        self.ui.set_hotkey_available(self._hotkey_handle is not None)
        self.ui.set_restore_hotkey_available(self._restore_hotkey_handle is not None)

        if start_paused:
            self._invalidate_tracking()
            logger.info("Starting with automation PAUSED; live tracking remains visible.")
        self.start_system()

    # ── Automation state management (§5) ─────────────────────────────────────

    def set_automation_enabled(self, enabled: bool) -> None:
        """Change automation atomically with action routing and reset state."""
        with self._automation_lock:
            if enabled == self._automation_enabled:
                return
            self._automation_enabled = enabled
            self._invalidate_tracking()
            if not enabled:
                self._rearm_state = self._REARM_IDLE
                logger.info("Automation PAUSED - all state released.")
            else:
                self._rearm_state = self._REARM_WAITING
                logger.info("Automation RESUMED - waiting for neutral before arming.")

    def _invalidate_tracking(self) -> None:
        """Release input and invalidate observations from before this reset."""
        with self._automation_lock:
            self._tracking_generation += 1
            self._tracking_capture_time = None
            self._rearm_neutral_frames = 0
            # Central safety invalidation for mapper, mouse, and gesture engine
            if hasattr(self.mapper, "mouse") and self.mapper.mouse is not None:
                if hasattr(self.mapper.mouse, "release_all"):
                    self.mapper.mouse.release_all()
            if hasattr(self.mapper, "reset_temporal_state"):
                self.mapper.reset_temporal_state()
            self.classifier.reset()
            if hasattr(self.mapper, "_action_executor"):
                self.mapper._action_executor.cancel("tracking invalidated")

    def _expire_tracking(self) -> bool:
        """UI-thread watchdog also releases input while native inference stalls."""
        with self._automation_lock:
            captured_at = self._tracking_capture_time
            if captured_at is None or time.perf_counter() - captured_at <= 0.25:
                return False
            self._invalidate_tracking()
            # Do not display a preview queued before the watchdog reset.
            try:
                while not self.frame_queue.empty():
                    self.frame_queue.get_nowait()
            except queue.Empty:
                pass
            logger.warning("Tracking watchdog expired; input released.")
            return True

    def _hotkey_toggle_automation(self) -> None:
        """Called by keyboard library (possibly off main thread)."""
        logger.info("Hotkey 'Ctrl+Alt+G' callback triggered.")
        with self._automation_lock:
            current = self._automation_enabled
        self.set_automation_enabled(not current)

    @property
    def automation_enabled(self) -> bool:
        with self._automation_lock:
            return self._automation_enabled

    def _tick_rearm(self, stable_gesture: str, raw_gesture: str | None = None) -> bool:
        """
        Returns True if automation is fully armed and actions may execute.
        Implements the re-arm guard (§7): after resume, automation stays
        logically disarmed until a neutral or Unknown/None gesture is observed
        for _REARM_NEUTRAL_REQUIRED consecutive frames.
        """
        if self._rearm_state == self._REARM_ARMED:
            return True
        if self._rearm_state == self._REARM_IDLE:
            return False

        # WAITING state
        neutral_states = ("Unknown", "None", None, "")
        neutral = stable_gesture in neutral_states and raw_gesture in neutral_states
        if neutral:
            self._rearm_neutral_frames += 1
            logger.debug(
                f"Re-arm neutral frame count: {self._rearm_neutral_frames}/{self._REARM_NEUTRAL_REQUIRED}"
            )
        else:
            if self._rearm_neutral_frames > 0:
                logger.debug(
                    f"Re-arm interrupted by gesture '{stable_gesture}' — resetting neutral count."
                )
            self._rearm_neutral_frames = 0  # reset on non-neutral

        if self._rearm_neutral_frames >= self._REARM_NEUTRAL_REQUIRED:
            self.classifier.reset()
            self.mapper.reset_temporal_state()
            self._rearm_state = self._REARM_ARMED
            logger.info("Automation armed — neutral gesture confirmed.")
            return True

        return False

    # ── Legacy toggle (kept for backward compat — UIs should use set_automation_enabled) ──

    def toggle_automation(self) -> None:
        with self._automation_lock:
            current = self._automation_enabled
        self.set_automation_enabled(not current)

    def set_mode(self, mode: str) -> None:
        """Switch mode safely from any thread, releasing input and resetting temporal state."""
        with self._automation_lock:
            if hasattr(self, "mapper") and self.mapper:
                self.mapper.set_mode(mode)
            if hasattr(self, "classifier") and self.classifier:
                self.classifier.reset()
        if hasattr(self, "ui") and self.ui:
            self.ui_commands.post(self.ui.set_mode_display, mode)

    def get_state_snapshot(self) -> AppStateSnapshot:
        with self._automation_lock:
            auto_state = ("RESUMING" if getattr(self, "_rearm_state", "") == self._REARM_WAITING
                          else "ACTIVE" if getattr(self, "_automation_enabled", False)
                          else "PAUSED")
            mode = self.mapper.mode if hasattr(self, "mapper") and self.mapper else "GENERAL"
        connected = bool(getattr(self, "camera", None) and self.camera.is_connected)
        if not connected:
            auto_state = "CAMERA DISCONNECTED"
        cam_fps = float(self.camera.current_fps) if hasattr(getattr(self, "camera", None), "current_fps") else (
            float(sum(self.fps_history) / len(self.fps_history)) if getattr(self, "fps_history", None) else 0.0
        )
        state_lock = getattr(self, "_state_lock", None)
        if state_lock is not None:
            with state_lock:
                raw_g = getattr(self, "_latest_raw_gesture", "Unknown")
                stable_g = getattr(self, "_latest_stable_gesture", "Unknown")
                conf = getattr(self, "_latest_confidence", 0)
                hands_len = len(getattr(self, "_latest_hands_data", []))
        else:
            raw_g = getattr(self, "_latest_raw_gesture", "Unknown")
            stable_g = getattr(self, "_latest_stable_gesture", "Unknown")
            conf = getattr(self, "_latest_confidence", 0)
            hands_len = len(getattr(self, "_latest_hands_data", []))

        return AppStateSnapshot(
            automation_state=auto_state,
            mode=mode,
            raw_gesture=raw_g,
            stable_gesture=stable_g,
            confidence=conf,
            camera_connected=connected,
            camera_fps=cam_fps,
            detector_fps=getattr(self, "detector_fps", 0.0),
            pointer_fps=getattr(self, "_pointer_fps", 0.0),
            inference_ms=getattr(self, "_inference_ms", 0.0),
            frame_age_ms=getattr(self, "_frame_age_ms", 0.0),
            hands_detected=hands_len,
        )

    def get_latest_preview(self) -> tuple:
        preview_lock = getattr(self, "_preview_lock", None)
        if preview_lock is not None:
            with preview_lock:
                frame = self._latest_preview_frame.copy() if getattr(self, "_latest_preview_frame", None) is not None else None
                return frame, getattr(self, "_latest_preview_frame_id", -1)
        else:
            frame = self._latest_preview_frame.copy() if getattr(self, "_latest_preview_frame", None) is not None else None
            return frame, getattr(self, "_latest_preview_frame_id", -1)

    # ── System start ──────────────────────────────────────────────────────────

    def start_system(self) -> None:
        """
        Start the application pipeline regardless of camera availability (§12).
        Camera retries in its own thread. Processing thread starts immediately.
        """
        # Camera.start() always returns — even if camera isn't available
        # (the camera thread will retry internally)
        self.camera.start()

        self.running = True

        self.process_thread = threading.Thread(
            target=self._run_processing, daemon=True, name="process"
        )
        self.process_thread.start()

        self.stats_thread = threading.Thread(
            target=self.monitoring_loop, daemon=True, name="stats"
        )
        self.stats_thread.start()

        if _HAS_PYSTRAY:
            self.tray_thread = threading.Thread(
                target=self._run_tray, daemon=True, name="tray"
            )
            self.tray_thread.start()

        self.update_ui_loop()

    # ── Background Tray ───────────────────────────────────────────────────────

    def _run_tray(self) -> None:
        """System tray icon. Runs on its own thread; never touches Tk itself.

        pystray invokes menu callbacks on the tray thread. Calling
        ``deiconify()`` or ``configure()`` from there is exactly the Tk
        thread-safety violation that produces a stuck window, so every
        callback only *posts* to :attr:`ui_commands`; the Tk thread drains
        that queue in ``update_ui_loop``.
        """
        try:
            icon_path = self._tray_icon_path()
            image = Image.open(icon_path) if icon_path else Image.new(
                "RGB", (64, 64), color=(0, 128, 255))

            def on_open(icon, item):
                self.ui_commands.post(self._show_dashboard_on_tk_thread)

            def on_stop_bg(icon, item):
                self.ui_commands.post(self._show_dashboard_on_tk_thread)

            def on_pause(icon, item):
                self.ui_commands.post(self.set_automation_enabled, False)

            def on_resume(icon, item):
                self.ui_commands.post(self.set_automation_enabled, True)

            def on_status(icon, item):
                self.ui_commands.post(self._show_status_on_tk_thread)

            def on_quit(icon, item):
                # Stop the tray first so it cannot outlive the process.
                try:
                    icon.stop()
                except Exception:
                    pass
                self.ui_commands.post(self.stop_system)
                self.ui_commands.post(self.ui.force_quit)

            menu = pystray.Menu(
                pystray.MenuItem("Open SmartGestureOS / Show Dashboard", on_open, default=True),
                pystray.MenuItem("Stop Background Mode (Show Dashboard)", on_stop_bg),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Resume Gesture Control", on_resume),
                pystray.MenuItem("Pause Gesture Control", on_pause),
                pystray.MenuItem("Show Status", on_status),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit SmartGestureOS", on_quit),
            )
            self.tray_icon = pystray.Icon("SmartGestureOS", image, "SmartGestureOS — ACTIVE", menu)
            self.tray_icon.run()
        except Exception:
            logger.exception("System tray error:")

    @staticmethod
    def _tray_icon_path() -> str | None:
        """Locate the tray icon in both source and PyInstaller layouts."""
        candidates = []
        try:
            from src.paths import RESOURCE_DIR
            candidates.append(RESOURCE_DIR / "packaging" / "windows" / "SmartGestureOS.ico")
            candidates.append(RESOURCE_DIR / "SmartGestureOS.ico")
        except Exception:
            pass
        root_dir = Path(__file__).resolve().parent
        candidates.append(root_dir / "packaging" / "windows" / "SmartGestureOS.ico")
        candidates.append(root_dir / "SmartGestureOS.ico")
        for candidate in candidates:
            try:
                if candidate.exists():
                    return str(candidate)
            except OSError:
                continue
        return None

    # -- Background control mode ------------------------------------------------

    def show_dashboard(self) -> None:
        """Restore the dashboard. Safe to call from ANY thread.

        Hiding the window must never stop the control engine, so this is a
        view-only operation; the Tk work is marshalled through the queue.
        """
        self.ui_commands.post(self._show_dashboard_on_tk_thread)

    def hide_dashboard(self) -> None:
        """Run in the background. Safe to call from ANY thread."""
        self.ui_commands.post(self._hide_dashboard_on_tk_thread)

    def toggle_dashboard(self) -> None:
        """Flip background mode. Safe to call from ANY thread."""
        self.ui_commands.post(self._toggle_dashboard_on_tk_thread)

    def _show_dashboard_on_tk_thread(self) -> None:
        try:
            self.ui.set_dashboard_visible(True)
        except Exception:
            logger.exception("Could not restore the dashboard.")

    def _hide_dashboard_on_tk_thread(self) -> None:
        try:
            self.ui.set_dashboard_visible(False)
        except Exception:
            logger.exception("Could not hide the dashboard.")

    def _toggle_dashboard_on_tk_thread(self) -> None:
        try:
            self.ui.set_dashboard_visible(not self.ui.dashboard_visible)
        except Exception:
            logger.exception("Could not toggle the dashboard.")

    @property
    def dashboard_visible(self) -> bool:
        """Authoritative background-mode state, safe to read from any thread."""
        try:
            return bool(self.ui.dashboard_visible)
        except Exception:
            return True

    def show_status(self) -> None:
        """Report current state. Thread-safe; the Tk work is queued."""
        self.ui_commands.post(self._show_status_on_tk_thread)

    def _show_status_on_tk_thread(self) -> None:
        view = "visible" if self.dashboard_visible else "HIDDEN (background mode)"
        automation = "ON" if self.automation_enabled else "PAUSED"
        camera = "connected" if self.camera.is_connected else "DISCONNECTED"
        try:
            self.ui.show_status_message(
                f"SmartGestureOS\n"
                f"Dashboard: {view}\n"
                f"Automation: {automation}\n"
                f"Camera: {camera}\n"
                f"Mode: {self.mapper.mode}"
            )
        except Exception:
            logger.exception("Could not display status.")

    def _hotkey_restore_dashboard(self) -> None:
        """Ctrl+Alt+Shift+G. Runs on the `keyboard` listener thread."""
        logger.info("Hotkey '%s' callback: restoring dashboard.", RESTORE_HOTKEY)
        self.show_dashboard()


    # ── Monitoring ────────────────────────────────────────────────────────────

    def _run_processing(self) -> None:
        try:
            # Core Audio interfaces must be acquired and released by the worker
            # that uses them; camera tracking can continue without an endpoint.
            self.mapper.volume.initialize()
            self.processing_loop()
        finally:
            try:
                self.mapper.volume.close()
            finally:
                # Native shutdown belongs to the thread that performs inference.
                self.detector.close()

    def monitoring_loop(self) -> None:
        try:
            process = psutil.Process(os.getpid())
            process.cpu_percent()  # initial call (discard)
        except psutil.NoSuchProcess:
            return

        while self.running:
            try:
                for _ in range(10):
                    if not self.running:
                        break
                    time.sleep(0.1)

                if not self.running:
                    break

                total_cpu = process.cpu_percent()
                total_ram = process.memory_info().rss

                for child in process.children(recursive=True):
                    try:
                        total_cpu += child.cpu_percent()
                        total_ram += child.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass

                self.cpu_usage = total_cpu
                self.ram_usage = total_ram / (1024 * 1024)  # MB
            except Exception:
                logger.exception("Stats monitoring error:")
                time.sleep(1)

    # ── Shutdown (§47) ────────────────────────────────────────────────────────

    def stop_system(self) -> None:
        """Idempotent shutdown — safe to call from close callback and finally."""
        with self._shutdown_lock:
            if self._shutdown_started:
                return
            self._shutdown_started = True

        with self._automation_lock:
            self.running = False
            self._automation_enabled = False
            self._invalidate_tracking()
            self.mapper.cleanup()

        # Unblock queues to prevent thread deadlock
        try:
            while not self.frame_queue.empty():
                self.frame_queue.get_nowait()
        except queue.Empty:
            pass

        self.camera.stop()

        # Unregister global hotkeys (§5). Both handles must be released or the
        # `keyboard` listener keeps the keyboard hook alive after exit, which
        # breaks every other application on the machine.
        # getattr is used throughout because shutdown must also work on
        # partially constructed instances (shutdown tests build MainApp with
        # __new__) and on a half-initialised application.
        try:
            import keyboard as _keyboard_module
        except Exception:
            _keyboard_module = None
        for attribute, label in (("_hotkey_handle", "Ctrl+Alt+G"),
                                 ("_restore_hotkey_handle", RESTORE_HOTKEY.upper())):
            handle = getattr(self, attribute, None)
            if handle is None:
                continue
            if _keyboard_module is not None:
                try:
                    _keyboard_module.remove_hotkey(handle)
                    logger.info(f"{label} hotkey unregistered. Handle={handle!r}")
                except Exception as e:
                    logger.warning(f"Could not unregister {label} hotkey: {e}")
            setattr(self, attribute, None)

        ui_commands = getattr(self, "ui_commands", None)
        if ui_commands is not None:
            ui_commands.clear()

        if self.process_thread and self.process_thread.is_alive():
            self.process_thread.join(timeout=2.0)
        if not self.process_thread or not self.process_thread.is_alive():
            self.detector.close()
        if self.stats_thread and self.stats_thread.is_alive():
            self.stats_thread.join(timeout=1.0)

        if getattr(self, 'tray_icon', None):
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        if getattr(self, "tray_thread", None) and self.tray_thread.is_alive():
            self.tray_thread.join(timeout=1.0)

    # ── Overlays ──────────────────────────────────────────────────────────────

    def draw_overlays(self, frame, hands_data, progress):
        if not hands_data:
            return frame

        h1 = hands_data[0]["landmarks"]
        index_x, index_y = h1[8].pixel_x, h1[8].pixel_y

        # Virtual cursor indicator
        cv2.circle(frame, (index_x, index_y), 12, (255, 255, 50), 2)
        cv2.circle(frame, (index_x, index_y), 3, (255, 255, 50), -1)

        # Gesture-hold loading ring
        if progress > 0.0:
            angle = int(360 * progress)
            cv2.ellipse(
                frame, (index_x, index_y), (25, 25), -90, 0, angle, (0, 255, 0), 4
            )

        return frame

    # ── Processing loop ───────────────────────────────────────────────────────

    def processing_loop(self) -> None:
        last_frame_id = -1
        last_inference_time = 0.0
        last_capture_time = time.perf_counter()
        last_preview_time = None
        observed_generation = self._tracking_generation
        tracking_valid = False
        latest_hands_data = []
        latest_stable_gesture = latest_raw_gesture = "Unknown"
        latest_confidence = 0
        latest_action = None
        latest_progress = 0.0
        self.fps_history = collections.deque(maxlen=30)
        self.latency_history = collections.deque(maxlen=30)
        detector_times = collections.deque(maxlen=30)
        self.detector_fps = 0.0

        def clear_observation():
            nonlocal latest_hands_data, latest_stable_gesture, latest_raw_gesture
            nonlocal latest_confidence, latest_action, latest_progress, tracking_valid
            latest_hands_data = []
            latest_stable_gesture = latest_raw_gesture = "Unknown"
            latest_confidence = 0
            latest_action = None
            latest_progress = 0.0
            tracking_valid = False
            detector_times.clear()
            self.detector_fps = 0.0
            state_lock = getattr(self, "_state_lock", None)
            if state_lock is not None:
                with state_lock:
                    self._latest_hands_data = []
                    self._latest_stable_gesture = self._latest_raw_gesture = "Unknown"
                    self._latest_confidence = 0
                    self._latest_action = None
            else:
                self._latest_hands_data = []
                self._latest_stable_gesture = self._latest_raw_gesture = "Unknown"
                self._latest_confidence = 0
                self._latest_action = None

        def invalidate(reason):
            nonlocal observed_generation
            if tracking_valid:
                logger.info("Tracking reset: %s", reason)
            self._invalidate_tracking()
            observed_generation = self._tracking_generation
            clear_observation()

        def publish(frame, connected, fps=0, frame_id=None):
            """Latest-frame mailbox. Drops the stale entry, never queues.

            ``frame_id`` rides along with the frame so the UI thread can
            suppress a frame it has already painted without needing access to
            this loop's locals (which it does not and must not have).
            """
            preview_lock = getattr(self, "_preview_lock", None)
            if preview_lock is not None:
                with preview_lock:
                    self._latest_preview_frame = frame
                    self._latest_preview_frame_id = frame_id if frame_id is not None else -1
            else:
                self._latest_preview_frame = frame
                self._latest_preview_frame_id = frame_id if frame_id is not None else -1

            state_lock = getattr(self, "_state_lock", None)
            if state_lock is not None:
                with state_lock:
                    self._latest_hands_data = list(latest_hands_data)
                    self._latest_stable_gesture = latest_stable_gesture
                    self._latest_raw_gesture = latest_raw_gesture
                    self._latest_confidence = latest_confidence
                    self._latest_action = latest_action
            else:
                self._latest_hands_data = list(latest_hands_data)
                self._latest_stable_gesture = latest_stable_gesture
                self._latest_raw_gesture = latest_raw_gesture
                self._latest_confidence = latest_confidence
                self._latest_action = latest_action
            avg_latency = (int(sum(self.latency_history) / len(self.latency_history))
                           if self.latency_history else 0)
            try:
                if self.frame_queue.full():
                    self.frame_queue.get_nowait()
                self.frame_queue.put_nowait((
                    frame, latest_hands_data, self.mapper.mode,
                    latest_stable_gesture, latest_raw_gesture, latest_confidence,
                    latest_action, fps, self.cpu_usage, self.ram_usage,
                    connected, self.mapper.is_sleeping, avg_latency,
                    self.automation_enabled, self._rearm_state == self._REARM_WAITING,
                    frame_id,
                ))
            except (queue.Empty, queue.Full):
                pass

        def status_frame(message):
            import numpy as np
            frame = np.zeros((self.camera.height, self.camera.width, 3), dtype=np.uint8)
            cv2.putText(frame, message, (30, self.camera.height // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return frame

        while self.running:
            loop_start = time.perf_counter()
            try:
                with self._automation_lock:
                    if observed_generation != self._tracking_generation:
                        clear_observation()
                        observed_generation = self._tracking_generation
                frame, frame_id, captured_at = self.camera.read_with_timestamp()
                is_connected = self.camera.is_connected

                if not is_connected:
                    if self._was_camera_connected or tracking_valid:
                        invalidate("camera disconnected")
                    self._was_camera_connected = False
                    publish(status_frame("CAMERA DISCONNECTED - RECOVERING..."), False)
                    time.sleep(0.1)
                    continue

                self._was_camera_connected = True
                now = time.perf_counter()
                # Check even when read() has no new frames: a stalled driver can
                # stay connected while holding an old drag/gesture indefinitely.
                if tracking_valid and now - last_capture_time > 0.25:
                    invalidate("camera frame expired")

                if frame is None or frame_id == last_frame_id:
                    if now - last_capture_time > 0.25:
                        publish(status_frame("WAITING FOR FRESH CAMERA FRAMES..."), True)
                else:
                    last_frame_id = frame_id
                    capture_time = captured_at if captured_at is not None else now
                    if now - capture_time > 0.25:
                        invalidate("stale captured frame")
                        publish(status_frame("WAITING FOR FRESH CAMERA FRAMES..."), True)
                        continue

                    with self._automation_lock:
                        actual_h, actual_w = frame.shape[:2]
                        self.mapper.update_frame_dimensions(actual_w, actual_h)
                        inference_interval = 1.0 / (5.0 if self.mapper.is_sleeping else 30.0)
                        inference_generation = self._tracking_generation

                    has_new_result = False
                    if now - last_inference_time >= inference_interval:
                        last_inference_time = now
                        # Preserve hand geometry for 4:3, portrait and other
                        # camera formats; only downscale large frames.
                        scale = min(1.0, 640.0 / max(actual_w, actual_h))
                        small_frame = cv2.resize(frame, (
                            max(1, round(actual_w * scale)),
                            max(1, round(actual_h * scale)),
                        )) if scale < 1.0 else frame
                        inf_t0 = time.perf_counter()
                        results = self.detector.process_frame(small_frame, int(now * 1000))
                        self._inference_ms = (time.perf_counter() - inf_t0) * 1000.0
                        self._frame_age_ms = (time.perf_counter() - capture_time) * 1000.0
                        with self._automation_lock:
                            if not self.running:
                                break
                            if inference_generation != self._tracking_generation:
                                # Pause/resume happened during native inference.
                                clear_observation()
                                observed_generation = self._tracking_generation
                            elif results is None or time.perf_counter() - capture_time > 0.25:
                                invalidate("inference failed or frame expired")
                            else:
                                hands = self.detector.get_all_hands_data(results, frame.shape)
                                if latest_hands_data and not hands:
                                    invalidate("hand left frame")
                                latest_hands_data = hands
                                result = self.classifier.classify(hands)
                                latest_stable_gesture = result.gesture
                                latest_raw_gesture = result.raw_gesture
                                latest_confidence = int(result.confidence)
                                tracking_valid = True
                                has_new_result = True
                                last_capture_time = capture_time
                                self._tracking_capture_time = capture_time
                                detector_times.append(time.perf_counter())
                                duration = detector_times[-1] - detector_times[0]
                                self.detector_fps = (
                                    (len(detector_times) - 1) / duration if duration > 0 else 0.0
                                )
                                self._detector_fps = self.detector_fps

                    # Read visibility once per frame. `self.ui.dashboard_visible`
                    # is a plain bool on the Tk thread; reading it here is a
                    # non-blocking attribute access, never a Tk call, so the
                    # processing thread never mutates or queries widget state.
                    dashboard_visible = True
                    try:
                        dashboard_visible = bool(self.ui.dashboard_visible)
                    except Exception:
                        dashboard_visible = True
                    # While hidden, skip the full-resolution copy entirely: the
                    # frame is only needed for the preview.
                    display_frame = frame.copy() if dashboard_visible else frame
                    # No action may start after pause/reset completes. Never
                    # count the same inference twice toward re-arm or a hold.
                    routed_result = False

                    # ── Phase 1: short, locked state transition ────────────────
                    # The lock protects state only. mapper.process() reaches
                    # ImageGrab, subprocess.Popen and pycaw, which can block
                    # for hundreds of milliseconds; holding the lock across it
                    # froze the Tk thread (which also needs this lock) and made
                    # the tracking watchdog observe a stale capture timestamp.
                    with self._automation_lock:
                        if not self.running:
                            break
                        if observed_generation != self._tracking_generation:
                            clear_observation()
                            observed_generation = self._tracking_generation
                            has_new_result = False
                        automation_on = self._automation_enabled
                        route_generation = self._tracking_generation
                        rearm_ok = False
                        if automation_on and has_new_result:
                            rearm_ok = self._tick_rearm(
                                latest_stable_gesture, latest_raw_gesture,
                            )

                    # ── Phase 2: slow routing, NO lock held ─────────────────────
                    if not automation_on:
                        latest_action, latest_progress = "Paused", 0.0
                    elif has_new_result and not rearm_ok:
                        latest_action, latest_progress = "Re-arming", 0.0
                    elif has_new_result:
                        kwargs = {"render_canvas": False, "capture_at": capture_time}
                        try:
                            import inspect
                            target_func = getattr(self.mapper.process, "side_effect", None) or self.mapper.process
                            sig = inspect.signature(target_func)
                            if "confidence" in sig.parameters:
                                kwargs["confidence"] = latest_confidence
                        except Exception:
                            pass
                        display_frame, latest_action, latest_progress = self.mapper.process(
                            latest_hands_data, latest_stable_gesture,
                            latest_raw_gesture, display_frame, **kwargs
                        )
                        routed_result = True
                        # Interaction telemetry for physical diagnosis.
                        # Guarded so it costs nothing and calls nothing when
                        # disabled (the default). The identity check matters:
                        # a test double returns a truthy mock attribute.
                        if getattr(self.classifier, "telemetry_enabled", False) is True:
                            self.classifier.emit_telemetry(
                                latest_raw_gesture, latest_stable_gesture,
                                latest_confidence, self.mapper.mouse.engine.state,
                            )

                    # ── Phase 3: re-validate after the unlocked section ─────────
                    # A pause, tracking reset or shutdown that happened while
                    # the action was running must invalidate its result.
                    with self._automation_lock:
                        route_stale = (
                            self._tracking_generation != route_generation
                            or not self.running
                        )
                    if route_stale:
                        latest_action, latest_progress = None, 0.0
                        routed_result = False
                        display_frame = frame

                    # Presentation runs for every camera frame, including
                    # skipped inference, pause and hand loss. Routing edits
                    # the canvas only on fresh results; composite it once.
                    # Drawn outside the lock: pure CPU work with no shared
                    # state, and keeping it out shortens lock hold time.
                    #
                    # BACKGROUND MODE: when the dashboard is hidden nothing can
                    # see this compositing, so the whole block is skipped. The
                    # frame.copy(), the canvas overlay, 21-landmark drawing and
                    # every cv2.putText are pure wasted CPU in that state, and
                    # skipping them is what makes background mode cheaper than
                    # the visible dashboard rather than merely equal to it.
                    with self._automation_lock:
                        mode_is_draw = self.mapper.mode == "DRAW"
                        paused_overlay = not self._automation_enabled
                        waiting_overlay = self._rearm_state == self._REARM_WAITING
                    if dashboard_visible:
                        if mode_is_draw:
                            display_frame = self.mapper.canvas.get_overlay(display_frame)
                        for hand in latest_hands_data:
                            self.detector.draw_landmarks(display_frame, hand["landmarks"])
                        if routed_result:
                            display_frame = self.draw_overlays(
                                display_frame, latest_hands_data, latest_progress,
                            )
                        # Feedback stays above artwork, so pausing is visible
                        # even when the user has filled the entire canvas.
                        if not self.detector.available:
                            cv2.putText(display_frame,
                                        f"HAND TRACKING UNAVAILABLE: {self.detector.error or 'Init failed'}",
                                        (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        if paused_overlay:
                            cv2.putText(display_frame, "AUTOMATION PAUSED", (50, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                        elif waiting_overlay:
                            cv2.putText(display_frame, "RESUMING - WAITING FOR NEUTRAL",
                                        (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
                        elif self.mapper.is_sleeping:
                            cv2.putText(display_frame, "AUTOMATION SLEEPING", (50, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

                    if has_new_result:
                        self.latency_history.append(int((time.perf_counter() - capture_time) * 1000))
                    preview_time = time.perf_counter()
                    if last_preview_time is not None:
                        self.fps_history.append(preview_time - last_preview_time)
                    last_preview_time = preview_time
                    # Actual preview cadence, including capture/inference waits.
                    fps = int(len(self.fps_history) / sum(self.fps_history)) if self.fps_history else 0
                    publish(display_frame, True, fps, frame_id=last_frame_id)

            except Exception:
                logger.exception("Error in processing loop:")
                invalidate("processing error")
                publish(status_frame("TRACKING ERROR - RETRYING..."), self.camera.is_connected)

            elapsed = time.perf_counter() - loop_start
            if elapsed < 1.0 / 60.0:
                time.sleep(1.0 / 60.0 - elapsed)

    def _pointer_metrics_snapshot(self) -> dict:
        """Real measured pointer-path counters for the diagnostic log.

        Returns an empty dict rather than raising when the pointer path is
        unavailable, so logging can never disturb the control pipeline.
        Values are measured, never extrapolated: the camera runs at ~30 FPS,
        so a pointer rate above the detector rate is not reported as such.
        """
        try:
            return self.mapper.mouse.pointer_metrics.as_dict()
        except Exception:
            return {}

    def update_ui_loop(self) -> None:
        """Tk-thread tick. Runs every 15 ms; must stay far under that budget.

        This is the only place Tk is touched, so it is also where commands
        posted by the hotkey and tray threads are executed. The three
        measured costs are:

          * ``_expire_tracking``  — cheap lock + timestamp compare
          * ``update_dashboard``  — now change-detected, ~0.4 ms steady state
          * ``update_frame``      — throttled to ~24 FPS and skipped entirely
                                     while the dashboard is hidden

        Before the fix the dashboard plus frame rendering cost ~27 ms per
        15 ms tick, so the Tk event loop never went idle and Windows
        reported the window as frozen. After the fix the same tick measures
        ~0.5 ms p50 / ~1.1 ms p95 (scripts/diagnose_ui_freeze.py).
        """
        # 1. Worker-thread commands FIRST, so a queued "show dashboard" is
        #    honoured by this same tick instead of one tick later.
        try:
            self.ui_commands.drain(limit=16)
        except Exception:
            logger.exception("UI command drain failed:")

        try:
            with self._automation_lock:
                captured_at = self._tracking_capture_time
            fresh = captured_at is not None and time.perf_counter() - captured_at <= 0.25
            self.ui.update_performance(
                self.camera.measured_fps,
                getattr(self, "detector_fps", 0.0) if fresh else 0.0,
                self.detector.average_inference_latency if fresh else 0.0,
            )
            if self._expire_tracking():
                import numpy as np
                frame = np.zeros((self.camera.height, self.camera.width, 3), dtype=np.uint8)
                cv2.putText(frame, "WAITING FOR FRESH TRACKING...", (30, self.camera.height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                self.ui.current_hands_data = []
                with self._automation_lock:
                    _is_resuming = self._rearm_state == self._REARM_WAITING
                self.ui.update_dashboard(
                    self.mapper.mode, "Unknown", "Unknown", 0, None, 0,
                    self.cpu_usage, self.ram_usage, self.camera.is_connected,
                    self.mapper.is_sleeping, 0, self.automation_enabled,
                    is_resuming=_is_resuming,
                )
                # Synthetic status frames carry no camera frame id, so the UI
                # is allowed to render them unconditionally (they are rare and
                # they must appear immediately, not after a preview interval).
                self.ui.update_frame(frame, frame_id=None, force=True)
            if not self.frame_queue.empty():
                (
                    frame, hands_data, mode, stable_gesture, raw_gesture,
                    confidence, action, fps, cpu_usage, ram_usage,
                    camera_on, is_sleeping, avg_latency, automation_enabled,
                    is_resuming, frame_id,
                ) = self.frame_queue.get_nowait()
                self.ui.current_hands_data = hands_data
                self.ui.update_dashboard(
                    mode, stable_gesture, raw_gesture, confidence,
                    action, fps, cpu_usage, ram_usage,
                    camera_on, is_sleeping, avg_latency, automation_enabled,
                    is_resuming=is_resuming,
                )
                # update_frame is a no-op while hidden: no cvtColor, no PIL,
                # no ImageTk. Tracking and control continue regardless.
                # The camera's monotonic frame id travels with the payload so
                # the UI can suppress a frame it has already painted.
                self.ui.update_frame(frame, frame_id=frame_id)
                now = time.perf_counter()
                if now - getattr(self, "_last_preview_log_time", 0.0) >= 1.0:
                    landmarks = hands_data[0]["landmarks"] if hands_data else []
                    tip = ((landmarks[8].pixel_x, landmarks[8].pixel_y)
                           if len(landmarks) == 21 else None)
                    pointer = self._pointer_metrics_snapshot()
                    logger.debug(
                        "Preview: camera=%s hands=%d landmarks=%d index_tip=%s "
                        "raw=%s stable=%s fps=%d input_ms=%d inference_ms=%.1f "
                        "pointer_fps=%.1f capture_to_pointer_ms=%s "
                        "pointer_samples=%d pointer_suppressed=%d automation=%s "
                        "dashboard=%s",
                        camera_on, len(hands_data), len(landmarks), tip,
                        raw_gesture, stable_gesture, fps, avg_latency,
                        self.detector.average_inference_latency,
                        pointer.get("pointer_fps", 0.0),
                        (f"{c2p:.1f}" if (c2p := pointer.get("capture_to_pointer_ms")) is not None else "None"),
                        pointer.get("pointer_samples", 0),
                        pointer.get("pointer_suppressed", 0),
                        automation_enabled,
                        "visible" if self.dashboard_visible else "hidden",
                    )
                    self._last_preview_log_time = now
        except Exception:
            logger.exception("Error in UI update loop:")

        if self.running:
            self.ui.after(15, self.update_ui_loop)

    # ── Main ──────────────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self.ui.mainloop()
        except Exception:
            logger.exception("App crashed:")
        finally:
            self.stop_system()


def run_self_check() -> bool:
    """Exercise bundled imports, model loading and one native inference without a camera."""
    import numpy as np

    detector = None
    try:
        detector = GestureDetector()
        if not detector.detector_available:
            logger.error(f"Self-check: detector unavailable: {detector.detector_error}")
            return False
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        result = detector.process_frame(frame, 1)
        if result is None or detector.frames_processed != 1:
            logger.error("Self-check: MediaPipe VIDEO inference failed.")
            return False
        logger.info("Self-check passed: model loaded and VIDEO inference completed.")
        return True
    except Exception:
        logger.exception("Self-check failed:")
        return False
    finally:
        if detector is not None:
            detector.close()


def run_ui_self_check() -> bool:
    """Check bundled Tk themes/fonts and auxiliary windows without a webcam."""
    import numpy as np

    ui = None
    try:
        ui = SmartGestureApp(set_automation_callback=lambda enabled: None)
        ui.withdraw()
        ui.update_idletasks()
        ui.set_hotkey_available(False)
        ui.update_dashboard("GENERAL", "Unknown", "Unknown", 0, None, 0,
                            camera_on=False, automation_enabled=False)
        ui.update_performance(0.0, 0.0, 0.0)
        ui.update_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        if getattr(ui, "current_imgtk", None) is None:
            raise RuntimeError("Tk preview image could not be created")
        for open_window, name in (
            (ui.open_settings, "settings_window"),
            (ui.open_coach, "coach_window"),
            (ui.open_trainer, "trainer_window"),
        ):
            open_window()
            window = getattr(ui, name)
            window.withdraw()
            ui.update_idletasks()
            window.on_closing()
        logger.info("UI self-check passed: dashboard, preview, Settings, Coach and Trainer.")
        return True
    except Exception:
        logger.exception("UI self-check failed:")
        return False
    finally:
        if ui is not None:
            ui.on_closing()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SmartGestureOS desktop application")
    # Automation is PAUSED unless the operator explicitly opts in. The flag
    # is kept for compatibility; --start-active is the intentional override.
    parser.add_argument("--start-paused", action="store_true", default=True,
                        help="Show live tracking with desktop automation initially paused (default)")
    parser.add_argument("--start-active", dest="start_paused", action="store_false",
                        help="Developer override: arm automation immediately on launch "
                             "(no neutral re-arm). Not for normal use.")
    parser.add_argument("--telemetry", action="store_true",
                        help="Log per-interaction pinch/scroll telemetry (rate-limited, "
                             "for diagnosing physical click and scroll failures)")
    parser.add_argument("--self-check", action="store_true",
                        help="Check bundled model and native inference without opening the camera or UI")
    parser.add_argument("--ui-self-check", action="store_true",
                        help="Check dashboard and auxiliary UI resources without opening the camera")
    args = parser.parse_args()
    if args.self_check:
        raise SystemExit(0 if run_self_check() else 1)
    if args.ui_self_check:
        raise SystemExit(0 if run_ui_self_check() else 1)
    app = MainApp(start_paused=args.start_paused)
    app.classifier.set_telemetry(args.telemetry)
    app.run()
