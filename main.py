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

    def __init__(self, start_paused: bool = False):
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
        self._automation_lock = threading.RLock()
        self._automation_enabled: bool = not start_paused
        self._rearm_state: str = self._REARM_IDLE if start_paused else self._REARM_ARMED
        self._rearm_neutral_frames: int = 0
        self._tracking_generation: int = 0
        self._tracking_capture_time: float | None = None

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
            # Release first, even if resetting a downstream controller fails.
            self.mapper.mouse.release_all()
            self.mapper.reset_temporal_state()
            self.classifier.reset()

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
            target=self._run_processing, daemon=True, name="process"
        )
        self.process_thread.start()

        self.stats_thread = threading.Thread(
            target=self.monitoring_loop, daemon=True, name="stats"
        )
        self.stats_thread.start()

        self.update_ui_loop()

    # ── Monitoring ────────────────────────────────────────────────────────────

    def _run_processing(self) -> None:
        try:
            self.processing_loop()
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
        if not self.process_thread or not self.process_thread.is_alive():
            self.detector.close()
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

        def clear_observation():
            nonlocal latest_hands_data, latest_stable_gesture, latest_raw_gesture
            nonlocal latest_confidence, latest_action, latest_progress, tracking_valid
            latest_hands_data = []
            latest_stable_gesture = latest_raw_gesture = "Unknown"
            latest_confidence = 0
            latest_action = None
            latest_progress = 0.0
            tracking_valid = False

        def invalidate(reason):
            nonlocal observed_generation
            if tracking_valid:
                logger.info("Tracking reset: %s", reason)
            self._invalidate_tracking()
            observed_generation = self._tracking_generation
            clear_observation()

        def publish(frame, connected, fps=0):
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
                    self.automation_enabled,
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
                        small_frame = cv2.resize(frame, (640, 360))
                        results = self.detector.process_frame(small_frame, int(now * 1000))
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

                    display_frame = frame.copy()
                    if not self.detector.available:
                        cv2.putText(display_frame,
                                    f"HAND TRACKING UNAVAILABLE: {self.detector.error or 'Init failed'}",
                                    (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    for hand in latest_hands_data:
                        self.detector.draw_landmarks(display_frame, hand["landmarks"])

                    # No action may start after pause/reset completes. Never
                    # count the same inference twice toward re-arm or a hold.
                    with self._automation_lock:
                        if not self.running:
                            break
                        if observed_generation != self._tracking_generation:
                            clear_observation()
                            observed_generation = self._tracking_generation
                            has_new_result = False
                        if not self._automation_enabled:
                            latest_action, latest_progress = "Paused", 0.0
                            cv2.putText(display_frame, "AUTOMATION PAUSED", (50, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                        elif has_new_result:
                            if not self._tick_rearm(latest_stable_gesture):
                                latest_action, latest_progress = "Re-arming", 0.0
                                cv2.putText(display_frame, "RESUMING - WAITING FOR NEUTRAL",
                                            (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
                            else:
                                display_frame, latest_action, latest_progress = self.mapper.process(
                                    latest_hands_data, latest_stable_gesture,
                                    latest_raw_gesture, display_frame,
                                )
                                display_frame = self.draw_overlays(
                                    display_frame, latest_hands_data, latest_progress,
                                )

                    if has_new_result:
                        self.latency_history.append(int((time.perf_counter() - capture_time) * 1000))
                    preview_time = time.perf_counter()
                    if last_preview_time is not None:
                        self.fps_history.append(preview_time - last_preview_time)
                    last_preview_time = preview_time
                    # Actual preview cadence, including capture/inference waits.
                    fps = int(len(self.fps_history) / sum(self.fps_history)) if self.fps_history else 0
                    publish(display_frame, True, fps)

            except Exception:
                logger.exception("Error in processing loop:")
                invalidate("processing error")
                publish(status_frame("TRACKING ERROR - RETRYING..."), self.camera.is_connected)

            elapsed = time.perf_counter() - loop_start
            if elapsed < 1.0 / 60.0:
                time.sleep(1.0 / 60.0 - elapsed)

    def update_ui_loop(self) -> None:
        try:
            if self._expire_tracking():
                import numpy as np
                frame = np.zeros((self.camera.height, self.camera.width, 3), dtype=np.uint8)
                cv2.putText(frame, "WAITING FOR FRESH TRACKING...", (30, self.camera.height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                self.ui.current_hands_data = []
                self.ui.update_dashboard(
                    self.mapper.mode, "Unknown", "Unknown", 0, None, 0,
                    self.cpu_usage, self.ram_usage, self.camera.is_connected,
                    self.mapper.is_sleeping, 0, self.automation_enabled,
                )
                self.ui.update_frame(frame)
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
                now = time.perf_counter()
                if now - getattr(self, "_last_preview_log_time", 0.0) >= 1.0:
                    landmarks = hands_data[0]["landmarks"] if hands_data else []
                    tip = ((landmarks[8].pixel_x, landmarks[8].pixel_y)
                           if len(landmarks) == 21 else None)
                    logger.debug(
                        "Preview: camera=%s hands=%d landmarks=%d index_tip=%s "
                        "raw=%s stable=%s fps=%d input_ms=%d inference_ms=%.1f automation=%s",
                        camera_on, len(hands_data), len(landmarks), tip,
                        raw_gesture, stable_gesture, fps, avg_latency,
                        self.detector.average_inference_latency, automation_enabled,
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SmartGestureOS desktop application")
    parser.add_argument("--start-paused", action="store_true",
                        help="Show live tracking with desktop automation initially paused")
    args = parser.parse_args()
    app = MainApp(start_paused=args.start_paused)
    app.run()
