import time
import cv2
import threading
import queue
import psutil
import os
import collections
from config import SETTINGS
from src.camera import Camera
from src.gesture_detector import GestureDetector
from src.gesture_classifier import GestureClassifier
from src.gesture_mapper import GestureMapper
from src.ui import SmartGestureApp
from src.logger import logger


class MainApp:
    # ── Re-arm states (§7) ────────────────────────────────────────────────────
    _REARM_IDLE     = "idle"        # automation off (just paused)
    _REARM_WAITING  = "waiting"     # waiting for neutral before arming
    _REARM_ARMED    = "armed"       # full automation active
    _REARM_NEUTRAL_REQUIRED: int = 5  # frames of neutral required to arm

    def __init__(self):
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

        self.ui = SmartGestureApp(
            close_callback=self.stop_system,
            toggle_pause_callback=self.toggle_automation,
            set_automation_callback=self.set_automation_enabled,
        )

        # Pipeline state
        self.running: bool = False
        self.frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self.process_thread: threading.Thread | None = None
        self.stats_thread: threading.Thread | None = None

        self.cpu_usage: float = 0.0
        self.ram_usage: float = 0.0

        self._was_camera_connected: bool = False

        # ── Automation state (§5) ─────────────────────────────────────────────
        # Thread-safe: protected by _automation_lock.
        # Only set_automation_enabled() mutates _automation_enabled.
        self._automation_lock: threading.Lock = threading.Lock()
        self._automation_enabled: bool = True
        self._rearm_state: str = self._REARM_ARMED
        self._rearm_neutral_frames: int = 0

        # Shutdown guard (§47)
        self._shutdown_started: bool = False
        self._shutdown_lock: threading.Lock = threading.Lock()

        # Global hotkey (§5) — store handle for cleanup
        self._hotkey_handle = None
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

        self.start_system()

    # ── Automation state management (§5) ─────────────────────────────────────

    def set_automation_enabled(self, enabled: bool) -> None:
        """
        Single authoritative method to enable/disable automation.
        Thread-safe — can be called from the keyboard callback thread or Tk.
        Both the UI button and the global hotkey call this.
        """
        with self._automation_lock:
            if enabled == self._automation_enabled:
                logger.debug(f"set_automation_enabled({enabled}) ignored: already {enabled}")
                return
            self._automation_enabled = enabled

        logger.info(f"set_automation_enabled executing: enabled={enabled}")
        if not enabled:
            # ── Pause: release everything (§6) ────────────────────────────
            self.mapper.mouse.release_all()
            if hasattr(self.mapper.mouse, "engine"):
                self.mapper.mouse.engine.reset()
            self.mapper.reset_temporal_state()
            self.classifier.reset()
            self._rearm_state = self._REARM_IDLE
            self._rearm_neutral_frames = 0
            logger.info("Automation PAUSED — all state released.")
        else:
            # ── Resume: enter re-arm waiting state (§7) ───────────────────
            self._rearm_state = self._REARM_WAITING
            self._rearm_neutral_frames = 0
            logger.info("Automation RESUMED — waiting for neutral gesture before arming.")

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

    def _tick_rearm(self, stable_gesture: str) -> bool:
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
        neutral = stable_gesture in ("Unknown", "None", None, "")
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
            target=self.processing_loop, daemon=True, name="process"
        )
        self.process_thread.start()

        self.stats_thread = threading.Thread(
            target=self.monitoring_loop, daemon=True, name="stats"
        )
        self.stats_thread.start()

        self.update_ui_loop()

    # ── Monitoring ────────────────────────────────────────────────────────────

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

        self.running = False

        # Unblock queues to prevent thread deadlock
        try:
            while not self.frame_queue.empty():
                self.frame_queue.get_nowait()
        except queue.Empty:
            pass

        # Safety: release all desktop automation before shutdown
        if hasattr(self, "mapper"):
            self.mapper.cleanup()

        self.camera.stop()

        if hasattr(self, "detector"):
            self.detector.close()

        # Unregister global hotkey (§5)
        if self._hotkey_handle is not None:
            try:
                import keyboard
                keyboard.remove_hotkey(self._hotkey_handle)
                logger.info(f"Ctrl+Alt+G hotkey unregistered. Handle={repr(self._hotkey_handle)}")
                self._hotkey_handle = None
            except Exception as e:
                logger.warning(f"Could not unregister hotkey: {e}")

        if self.process_thread and self.process_thread.is_alive():
            self.process_thread.join(timeout=2.0)
        if self.stats_thread and self.stats_thread.is_alive():
            self.stats_thread.join(timeout=1.0)

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
        last_frame_id: int = -1
        last_inference_time: float = 0.0
        last_timestamp_ms: int = -1
        inference_interval: float = 1.0 / 30.0

        # Stale result invalidation (§9)
        min_accepted_timestamp_ms: int = 0

        self.fps_history = collections.deque(maxlen=30)
        self.latency_history = collections.deque(maxlen=30)

        latest_hands_data = None
        latest_stable_gesture = "Unknown"
        latest_raw_gesture = "Unknown"
        latest_confidence = 0
        latest_action = None
        latest_progress = 0.0

        last_result_receive_time = time.perf_counter()
        last_input_log_time = 0.0

        while self.running:
            loop_start = time.perf_counter()
            try:
                frame, frame_id, captured_at = self.camera.read_with_timestamp()
                is_connected = self.camera.is_connected

                # ── Camera disconnect branch ──────────────────────────────────
                if not is_connected:
                    if self._was_camera_connected:
                        logger.warning("Camera disconnected — releasing automation state.")
                        self.mapper.mouse.release_all()
                        self.mapper.reset_temporal_state()
                        self.classifier.reset()
                        # Invalidate prior queued results (§9)
                        min_accepted_timestamp_ms = (
                            self.detector.last_submitted_timestamp_ms + 1
                            if hasattr(self.detector, "last_submitted_timestamp_ms")
                            and self.detector.last_submitted_timestamp_ms > 0
                            else int(time.perf_counter() * 1000)
                        )
                        self.detector.clear_results()
                        latest_hands_data = None
                        latest_stable_gesture = "Unknown"
                        latest_raw_gesture = "Unknown"
                        latest_confidence = 0
                        latest_action = None
                        latest_progress = 0.0
                    self._was_camera_connected = False

                    import numpy as np
                    err_frame = np.zeros(
                        (self.camera.height, self.camera.width, 3), dtype=np.uint8
                    )
                    cv2.putText(
                        err_frame,
                        "CAMERA DISCONNECTED - RECOVERING...",
                        (50, self.camera.height // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2,
                    )
                    try:
                        if self.frame_queue.full():
                            self.frame_queue.get_nowait()
                        mode     = getattr(self.mapper, "mode", "GENERAL")
                        sleeping = getattr(self.mapper, "is_sleeping", False)
                        self.frame_queue.put_nowait((
                            err_frame, [], mode, "Unknown", "Unknown", 0,
                            None, 0, self.cpu_usage, self.ram_usage,
                            False, sleeping, 0, self.automation_enabled,
                        ))
                    except (queue.Empty, queue.Full):
                        pass
                    time.sleep(0.1)
                    continue

                # Camera is connected
                self._was_camera_connected = True

                if frame is not None and frame_id != last_frame_id:
                    last_frame_id = frame_id
                    current_time = time.perf_counter()

                    # ── Propagate actual frame dimensions to mapper (§10) ─────
                    actual_h, actual_w = frame.shape[:2]
                    self.mapper.update_frame_dimensions(actual_w, actual_h)

                    inference_interval = 1.0 / 5.0 if self.mapper.is_sleeping else 1.0 / 30.0

                    # 1. Run inference synchronously if interval passed
                    has_new_result = False
                    if current_time - last_inference_time >= inference_interval:
                        timestamp_ms = int(current_time * 1000)
                        if timestamp_ms <= last_timestamp_ms:
                            timestamp_ms = last_timestamp_ms + 1
                        last_timestamp_ms = timestamp_ms

                        small_frame = cv2.resize(frame, (640, 360))

                        results = self.detector.process_frame(small_frame, timestamp_ms)
                        if results is not None:
                            last_result_receive_time = time.perf_counter()
                            has_new_result = True

                        last_inference_time = current_time

                        if results is not None:
                            latest_hands_data = self.detector.get_all_hands_data(
                                results, frame.shape
                            )
                            result_obj = self.classifier.classify(latest_hands_data)
                            latest_stable_gesture = result_obj.gesture
                            latest_raw_gesture    = result_obj.raw_gesture
                            latest_confidence     = int(result_obj.confidence)

                    # 2. TTL Check (§9)
                    if not has_new_result and current_time - last_result_receive_time > 0.25:
                        # Stale ML TTL — clear and reset (§9)
                        if latest_hands_data is not None:
                            logger.warning("Stale MediaPipe TTL — releasing automation state.")
                            self.mapper.mouse.release_all()
                            self.mapper.reset_temporal_state()
                            self.classifier.reset()
                            self.detector.clear_results()
                        latest_hands_data = None
                        latest_stable_gesture = "Unknown"
                        latest_raw_gesture    = "Unknown"
                        latest_confidence     = 0

                    # 3. Apply mapper using current ML result
                    display_frame = frame.copy()

                    # Report detector availability clearly (Phase B)
                    if not self.detector.available:
                        cv2.putText(
                            display_frame,
                            f"HAND TRACKING UNAVAILABLE: {self.detector.error or 'Init failed'}",
                            (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
                        )

                    # Draw landmarks whenever hand data exists (Phase G)
                    if latest_hands_data:
                        for hand_data in latest_hands_data:
                            self.detector.draw_landmarks(display_frame, hand_data["landmarks"])

                    if not self.automation_enabled:
                        cv2.putText(
                            display_frame, "AUTOMATION PAUSED",
                            (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2,
                        )
                        latest_action = "Paused"
                        latest_progress = 0.0

                    elif not self._tick_rearm(latest_stable_gesture):
                        # Re-arm waiting — show camera but don't act
                        cv2.putText(
                            display_frame, "RESUMING - WAITING FOR NEUTRAL",
                            (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2,
                        )
                        latest_action = "Re-arming"
                        latest_progress = 0.0

                    elif latest_hands_data:
                        display_frame, latest_action, latest_progress = self.mapper.process(
                            latest_hands_data, latest_stable_gesture,
                            latest_raw_gesture, display_frame,
                        )
                        display_frame = self.draw_overlays(
                            display_frame, latest_hands_data, latest_progress
                        )
                    else:
                        # Hand lost — mapper calls on_hand_lost internally
                        display_frame, latest_action, latest_progress = self.mapper.process(
                            [], "None", "None", display_frame
                        )

                    # Camera capture through gesture routing; detector-only time is
                    # tracked separately by GestureDetector.average_inference_latency.
                    if has_new_result and captured_at is not None:
                        self.latency_history.append(
                            int((time.perf_counter() - captured_at) * 1000)
                        )

                    # Rate-limited input pipeline diagnostics (every 1.0s)
                    if latest_hands_data and current_time - last_input_log_time >= 1.0:
                        h1 = latest_hands_data[0]["landmarks"]
                        engine_state = (
                            self.mapper.mouse.engine.state.name
                            if hasattr(self.mapper, "mouse") and hasattr(self.mapper.mouse, "engine")
                            else "N/A"
                        )
                        logger.debug(
                            f"InputPipeline: raw='{latest_raw_gesture}', "
                            f"stable='{latest_stable_gesture}', conf={latest_confidence}%, "
                            f"engine_state={engine_state}, action='{latest_action}', "
                            f"index_tip=({h1[8].pixel_x}, {h1[8].pixel_y})"
                        )
                        last_input_log_time = current_time

                    # Telemetry
                    time_diff = time.perf_counter() - loop_start
                    current_fps = (1.0 / time_diff) if time_diff > 0 else 60.0
                    self.fps_history.append(current_fps)
                    fps = int(sum(self.fps_history) / len(self.fps_history))
                    avg_latency = (
                        int(sum(self.latency_history) / len(self.latency_history))
                        if self.latency_history else 0
                    )

                    try:
                        if self.frame_queue.full():
                            self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait((
                            display_frame, latest_hands_data,
                            self.mapper.mode, latest_stable_gesture,
                            latest_raw_gesture, latest_confidence,
                            latest_action, fps,
                            self.cpu_usage, self.ram_usage,
                            is_connected, self.mapper.is_sleeping,
                            avg_latency, self.automation_enabled,
                        ))
                    except (queue.Empty, queue.Full):
                        pass

            except Exception:
                logger.exception("Error in processing loop:")

            elapsed = time.perf_counter() - loop_start
            sleep_time = (1.0 / 60.0) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    # ── UI update ─────────────────────────────────────────────────────────────

    def update_ui_loop(self) -> None:
        try:
            if not self.frame_queue.empty():
                (
                    frame, hands_data, mode, stable_gesture, raw_gesture,
                    confidence, action, fps, cpu_usage, ram_usage,
                    camera_on, is_sleeping, avg_latency, automation_enabled,
                ) = self.frame_queue.get_nowait()
                self.ui.current_hands_data = hands_data
                self.ui.update_dashboard(
                    mode, stable_gesture, raw_gesture, confidence,
                    action, fps, cpu_usage, ram_usage,
                    camera_on, is_sleeping, avg_latency, automation_enabled,
                )
                self.ui.update_frame(frame)
        except Exception:
            logger.exception("Error in UI update loop:")

        self.ui.after(15, self.update_ui_loop)

    # ── Main ──────────────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self.ui.mainloop()
        except Exception:
            logger.exception("App crashed:")
        finally:
            self.stop_system()


if __name__ == "__main__":
    app = MainApp()
    app.run()
