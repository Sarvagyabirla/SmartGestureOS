import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
import time
from collections import deque
import warnings
from src.logger import logger
from src.ui_commands import PreviewBudget, DEFAULT_PREVIEW_FPS

# Suppress the CustomTkinter warning about using PhotoImage instead of CTkImage
# We intentionally use PhotoImage to prevent memory leaks in the fast render loop.
warnings.filterwarnings("ignore", message=".*Given image is not CTkImage.*")

class SmartGestureApp(ctk.CTk):
    # Class-level defaults for the render-budget / background-mode state.
    # Partially constructed instances (tests use ``object.__new__``) must stay
    # usable, and Tkinter's ``__getattr__`` would otherwise recurse into
    # ``self.tk`` and raise RecursionError instead of a clear AttributeError.
    preview_budget = None
    _preview_enabled = True
    _dashboard_visible = True
    _minimize_to_tray = True
    _last_size_probe = 0.0
    _displayed_progress = 0.0
    _last_history_action = None
    current_frame_id = None
    frames_rendered = 0
    frames_suppressed_hidden = 0
    _auto_frame_id = 0
    #: Per-instance cache of last-configured widget values. Declared at
    #: class scope only so a partially constructed instance still resolves the
    #: attribute; ``_configure_if_changed`` rebinds it per instance on first
    #: use, which keeps two instances from sharing state.
    _configured = None

    def __init__(self, close_callback=None, toggle_pause_callback=None,
                 set_automation_callback=None, initial_automation_enabled=False):
        super().__init__()
        
        self.title("SmartGestureOS")
        self.geometry("1100x700")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        from src.ui_theme import BG_COLOR, CARD_COLOR, SECONDARY_SURFACE, ACCENT_COLOR, TEXT_COLOR, MUTED_TEXT
        
        # Premium Colors
        self.bg_color = BG_COLOR
        self.card_color = CARD_COLOR
        self.secondary_surface = SECONDARY_SURFACE
        self.accent_color = ACCENT_COLOR
        self.text_color = TEXT_COLOR
        self.muted_text = MUTED_TEXT
        
        self.configure(fg_color=self.bg_color)
        
        # Pywinstyles can still apply mica effect without transparent background
        try:
            import pywinstyles
            pywinstyles.apply_style(self, "mica")
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Optional Windows window styling unavailable: %s", exc)
        
        self.close_callback = close_callback
        self.toggle_pause_callback = toggle_pause_callback
        self.set_automation_callback = set_automation_callback
        # IMPORTANT: initialise to match the authoritative backend state, NOT True.
        # Production starts PAUSED, so this must default to False.
        # A stale True here causes toggle_pause() to compute (not True) = False
        # and send set_automation_enabled(False) to a backend already paused,
        # silently doing nothing (the P0 Resume-does-nothing bug).
        self.automation_enabled = bool(initial_automation_enabled)
        self._is_resuming = False  # True while waiting for neutral re-arm
        self.hotkey_available = True
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        self.settings_window = None
        self.trainer_window = None
        self.last_stat_update = 0
        
        self.sidebar_container = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color=self.card_color)
        self.sidebar_container.grid(row=0, column=0, sticky="nsew")
        self.sidebar_container.grid_rowconfigure(0, weight=1)
        self.sidebar_container.grid_columnconfigure(0, weight=1)
        # Keep the pause control visible even on small screens or at high DPI.
        self.sidebar = ctk.CTkScrollableFrame(self.sidebar_container, width=300, corner_radius=0, fg_color=self.card_color)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        
        # Typography
        title_font = ctk.CTkFont(family="Segoe UI", size=26, weight="bold")
        header_font = ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        value_font = ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        normal_font = ctk.CTkFont(family="Segoe UI", size=13)
        small_font = ctk.CTkFont(family="Segoe UI", size=11)
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="SmartGestureOS", font=title_font, text_color=self.accent_color)
        self.logo_label.grid(row=0, column=0, padx=24, pady=(30, 20), sticky="w")
        
        # Elevated cards for sections
        def create_card(row, title, default_val, val_font, val_color):
            frame = ctk.CTkFrame(self.sidebar, fg_color=self.bg_color, corner_radius=8)
            frame.grid(row=row, column=0, padx=20, pady=8, sticky="ew")
            lbl_title = ctk.CTkLabel(frame, text=title, font=small_font, text_color=self.muted_text)
            lbl_title.pack(anchor="w", padx=15, pady=(10, 0))
            lbl_val = ctk.CTkLabel(frame, text=default_val, font=val_font, text_color=val_color)
            lbl_val.pack(anchor="w", padx=15, pady=(0, 10))
            return frame, lbl_val
            
        _, self.mode_label = create_card(1, "CURRENT MODE", "INITIALIZING...", value_font, self.accent_color)
        _, self.raw_gesture_label = create_card(2, "RAW GESTURE", "None", value_font, self.muted_text)
        _, self.gesture_label = create_card(3, "STABLE GESTURE", "None", value_font, self.text_color)
        
        self.conf_frame = ctk.CTkFrame(self.sidebar, fg_color=self.bg_color, corner_radius=8)
        self.conf_frame.grid(row=4, column=0, padx=20, pady=8, sticky="ew")
        self.conf_label = ctk.CTkLabel(self.conf_frame, text="Confidence: 0%", font=small_font, text_color=self.muted_text)
        self.conf_label.pack(anchor="w", padx=15, pady=(10, 0))
        self.confidence_bar = ctk.CTkProgressBar(self.conf_frame, height=8, corner_radius=4, fg_color=self.card_color)
        self.confidence_bar.pack(fill="x", padx=15, pady=(5, 15))
        self.confidence_bar.set(0)
        
        # Stats panel
        self.stats_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.stats_frame.grid(row=5, column=0, padx=20, pady=10, sticky="ew")
        self.stats_frame.grid_columnconfigure((0, 1), weight=1)
        self.fps_label = ctk.CTkLabel(self.stats_frame, text="Processing: 0 fps", font=normal_font, text_color=self.muted_text)
        self.fps_label.grid(row=0, column=0, sticky="w")
        self.latency_label = ctk.CTkLabel(self.stats_frame, text="Input: 0 ms", font=normal_font, text_color=self.muted_text)
        self.latency_label.grid(row=0, column=1, sticky="e")
        self.cpu_label = ctk.CTkLabel(self.stats_frame, text="CPU: 0%", font=normal_font, text_color=self.muted_text)
        self.cpu_label.grid(row=1, column=0, sticky="w")
        self.ram_label = ctk.CTkLabel(self.stats_frame, text="RAM: 0 MB", font=normal_font, text_color=self.muted_text)
        self.ram_label.grid(row=1, column=1, sticky="e")
        self.camera_fps_label = ctk.CTkLabel(self.stats_frame, text="Camera: 0 fps", font=normal_font, text_color=self.muted_text)
        self.camera_fps_label.grid(row=2, column=0, sticky="w")
        self.detector_fps_label = ctk.CTkLabel(self.stats_frame, text="Detector: 0 fps", font=normal_font, text_color=self.muted_text)
        self.detector_fps_label.grid(row=2, column=1, sticky="e")
        self.inference_label = ctk.CTkLabel(self.stats_frame, text="Inference: 0 ms", font=normal_font, text_color=self.muted_text)
        self.inference_label.grid(row=3, column=0, columnspan=2, sticky="w")
        
        # Action Buttons
        self.btn_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.btn_frame.grid(row=8, column=0, padx=20, pady=10, sticky="ew")
        self.settings_btn = ctk.CTkButton(self.btn_frame, text="Settings", command=self.open_settings, fg_color=self.bg_color, hover_color="#333333")
        self.settings_btn.pack(fill="x", pady=4)
        self.train_btn = ctk.CTkButton(self.btn_frame, text="Train Custom Gesture", command=self.open_trainer, fg_color=self.bg_color, hover_color="#333333")
        self.train_btn.pack(fill="x", pady=4)
        self.coach_btn = ctk.CTkButton(self.btn_frame, text="Gesture Coach", command=self.open_coach, fg_color=self.accent_color, text_color="#000000", hover_color="#00B8D4")
        self.coach_btn.pack(fill="x", pady=4)
        
        self.pause_btn = ctk.CTkButton(self.sidebar_container, text="Pause (Ctrl+Alt+G)", command=self.toggle_pause, fg_color="#d64545", hover_color="#b33939")
        self.pause_btn.grid(row=1, column=0, padx=20, pady=(8, 4), sticky="ew")
        self.hotkey_status_label = ctk.CTkLabel(self.sidebar_container, text="Ctrl+Alt+G pauses or resumes automation.", font=small_font, wraplength=280, text_color=self.muted_text)
        self.hotkey_status_label.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        # Status indicators
        self.camera_state_label = ctk.CTkLabel(self.sidebar, text="● CAMERA ACTIVE", font=small_font, text_color=self.accent_color)
        self.camera_state_label.grid(row=12, column=0, padx=24, pady=(10, 2), sticky="w")
        self.automation_state_label = ctk.CTkLabel(self.sidebar, text="● AUTOMATION ON", font=small_font, text_color=self.accent_color)
        self.automation_state_label.grid(row=13, column=0, padx=24, pady=2, sticky="w")
        
        self.history_label_title = ctk.CTkLabel(self.sidebar, text="RECENT ACTIONS", font=small_font, text_color=self.muted_text)
        self.history_label_title.grid(row=14, column=0, padx=24, pady=(15, 0), sticky="w")
        self.history_textbox = ctk.CTkTextbox(self.sidebar, height=100, state="disabled", font=small_font, fg_color=self.bg_color, corner_radius=8)
        self.history_textbox.grid(row=15, column=0, padx=20, pady=(5, 20), sticky="ew")
        
        self.action_history = deque(maxlen=8)
        
        # Main video frame (right panel)
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        # The video container looks like a massive elevated screen
        self.video_container = ctk.CTkFrame(self.main_frame, fg_color=self.card_color, corner_radius=16)
        self.video_container.grid(row=0, column=0, sticky="nsew")
        self.video_container.grid_rowconfigure(0, weight=1)
        self.video_container.grid_columnconfigure(0, weight=1)
        
        self.video_label = ctk.CTkLabel(self.video_container, text="")
        self.video_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.welcome_label = ctk.CTkLabel(
            self.main_frame,
            text="WELCOME TO SMARTGESTUREOS\n"
                 "Place one hand 30–50 cm from the webcam. Point to move; pinch to click.\n"
                 "Use Call Me to change mode. Use Pause or Ctrl+Alt+G to stop automation.\n"
                 "After resuming, lower your hand briefly before continuing.",
            font=normal_font, text_color=self.muted_text, justify="left", wraplength=620,
        )
        self.welcome_label.grid(row=1, column=0, padx=10, pady=(12, 0), sticky="w")
        
        self.current_imgtk = None
        self.frame_width = 750
        self.frame_height = 500

        # ── Render budget / background mode ──────────────────────────────────
        # ``_preview_enabled`` is the single switch that makes background mode
        # cheap: when the dashboard is hidden it is False, so update_frame()
        # returns immediately without cvtColor, PIL or ImageTk work at all.
        self.preview_budget = PreviewBudget(max_fps=DEFAULT_PREVIEW_FPS)
        self._preview_enabled = True
        self._dashboard_visible = True
        self._minimize_to_tray = True
        self._last_size_probe = 0.0
        self._displayed_progress = 0.0
        self._last_history_action = None
        self.current_frame_id = None
        self.frames_rendered = 0
        self.frames_suppressed_hidden = 0
        self._init_background_controls()
        self.protocol("WM_DELETE_WINDOW", self.on_window_close)

    # ── Background control mode ────────────────────────────────────────────────

    def _init_background_controls(self):
        """Build the 'Run in Background' control and its status line."""
        self.background_btn = ctk.CTkButton(
            self.btn_frame, text="Run in Background",
            command=self.request_hide,
            fg_color=self.accent_color, text_color="#000000", hover_color="#00B8D4",
        )
        self.background_btn.pack(fill="x", pady=4)

        self.background_status_label = ctk.CTkLabel(
            self.sidebar_container,
            text="Dashboard visible. Ctrl+Alt+Shift+G restores it.",
            font=small_font if False else ctk.CTkFont(family="Segoe UI", size=11),
            wraplength=280, text_color=self.muted_text,
        )
        self.background_status_label.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")

        # Transient status line (tray "Show Status" and similar notices).
        self.status_message_label = ctk.CTkLabel(
            self.sidebar_container, text="", font=ctk.CTkFont(family="Segoe UI", size=11),
            wraplength=280, text_color=self.accent_color,
        )
        self.status_message_label.grid(row=4, column=0, padx=20, pady=(0, 6), sticky="ew")

    @property
    def dashboard_visible(self) -> bool:
        """True when the user can see the dashboard."""
        return self._dashboard_visible

    @property
    def minimize_to_tray(self) -> bool:
        """Whether the window's X button means 'background' rather than 'exit'."""
        return self._minimize_to_tray

    def set_minimize_to_tray(self, enabled: bool) -> None:
        """Settings hook: X means background (True) or exit (False)."""
        self._minimize_to_tray = bool(enabled)

    def set_dashboard_visible(self, visible: bool) -> None:
        """Show or hide the dashboard. **Tk thread only.**

        Hiding does three things, in order:
          1. ``withdraw()`` removes the window from the desktop;
          2. preview rendering is switched OFF, so cv2/PIL/ImageTk stop
             burning CPU for an image nobody can see;
          3. any queued preview frame is invalidated, so restoring the window
             cannot flash a stale frame.

        The control engine, camera, detector, pointer and hotkeys are all
        untouched: this is a VIEW change, never a control-pipeline change.
        """
        visible = bool(visible)
        if visible == self._dashboard_visible:
            return
        self._dashboard_visible = visible
        self._preview_enabled = visible
        if visible:
            # Drop whatever was queued while hidden: showing it would be a
            # visible jump back to a stale image.
            self.preview_budget.invalidate()
            try:
                self.deiconify()
                self.lift()
                self.focus_force()
            except Exception as exc:
                logger.debug("Could not raise dashboard: %s", exc)
        else:
            try:
                self.withdraw()
            except Exception as exc:
                logger.debug("Could not hide dashboard: %s", exc)
        self._set_background_status()
        logger.info("Dashboard %s (preview rendering %s).",
                    "shown" if visible else "hidden",
                    "enabled" if self._preview_enabled else "disabled")

    def request_hide(self) -> None:
        """'Run in Background' button. Tk thread only."""
        self.set_dashboard_visible(False)

    def request_show(self) -> None:
        """Restore the dashboard. Tk thread only."""
        self.set_dashboard_visible(True)

    def toggle_dashboard(self) -> None:
        self.set_dashboard_visible(not self._dashboard_visible)

    def _set_background_status(self) -> None:
        if not self._dashboard_visible:
            text = ("Running in background. Press Ctrl+Alt+Shift+G or use the "
                    "tray icon to reopen this dashboard.")
            color = self.accent_color
        else:
            text = "Dashboard visible. Ctrl+Alt+Shift+G restores it."
            color = self.muted_text
        try:
            self.background_status_label.configure(text=text, text_color=color)
        except Exception:
            pass

    def on_window_close(self):
        """The window's X button.

        Predictable by design (never a surprise): if "minimize to tray on
        close" is enabled the X means "run in background", otherwise it means
        "exit". A user can therefore never hide the UI and be unable to get
        it back.
        """
        if self._minimize_to_tray:
            self.set_dashboard_visible(False)
        else:
            self.force_quit()

    def on_closing(self):
        """Back-compatible alias for the window's X button behaviour.

        Historically this hid the window unconditionally, which meant that a
        tray failure left the user with no window and no way back. It now
        delegates to :meth:`on_window_close`, which honours the
        minimize-to-tray setting and otherwise exits.
        """
        self.on_window_close()

    def force_quit(self):
        """Actually destroy the UI and trigger shutdown callbacks."""
        if self.settings_window:
            self.settings_window.destroy()
        if self.trainer_window:
            self.trainer_window.destroy()
        if hasattr(self, 'coach_window') and self.coach_window:
            self.coach_window.destroy()
        if self.close_callback:
            self.close_callback()
        self.destroy()
        
    def toggle_pause(self):
        logger.info("UI Pause/Resume button clicked.")
        if self.set_automation_callback is not None:
            self.set_automation_callback(not self.automation_enabled)
        elif self.toggle_pause_callback is not None:
            self.toggle_pause_callback()
        else:
            logger.warning("No toggle_pause_callback or set_automation_callback configured on UI.")

    def set_hotkey_available(self, available):
        """Show a registration failure without disabling the UI pause control."""
        self.hotkey_available = bool(available)
        self.hotkey_status_label.configure(
            text=("Ctrl+Alt+G pauses or resumes automation." if available else
                  "Ctrl+Alt+G is unavailable. Use the Pause / Resume button."),
            text_color=self.muted_text if available else "#e38b29",
        )
        self.pause_btn.configure(text=self._pause_button_text())

    def set_restore_hotkey_available(self, available):
        """Report whether Ctrl+Alt+Shift+G could be registered."""
        self.restore_hotkey_available = bool(available)
        try:
            if available:
                self.background_status_label.configure(
                    text="Ctrl+Alt+Shift+G restores this dashboard.",
                    text_color=self.muted_text)
            else:
                self.background_status_label.configure(
                    text=("Ctrl+Alt+Shift+G unavailable — use the tray icon or "
                          "the taskbar to restore the dashboard."),
                    text_color="#e38b29")
        except Exception:
            pass

    def show_status_message(self, message: str) -> None:
        """Transient in-dashboard status line. Tk thread only."""
        try:
            self.status_message_label.configure(text=message)
            self.after(6000, lambda: self.status_message_label.configure(text=""))
        except Exception:
            logger.debug("Could not display status message.")

    def _pause_button_text(self):
        label = "Pause" if self.automation_enabled else "Resume"
        return label + (" (Ctrl+Alt+G)" if self.__dict__.get("hotkey_available", True) else "")

    def update_performance(self, camera_fps, detector_fps, inference_ms):
        """Display independently measured capture and inference performance."""
        self.camera_fps_label.configure(text=f"Camera: {camera_fps:.1f} fps")
        self.detector_fps_label.configure(text=f"Detector: {detector_fps:.1f} fps")
        self.inference_label.configure(text=f"Inference: {inference_ms:.1f} ms")

    def _pause_for_auxiliary_ui(self):
        """Practicing/configuring gestures must not trigger desktop actions.

        Calls the authoritative backend callback only — does NOT locally mutate
        ``automation_enabled`` because the UI cache must only be updated by the
        backend via ``update_dashboard``.  Double-calling the callback is safe
        because ``set_automation_enabled`` is idempotent when already paused.
        """
        if self.set_automation_callback is not None:
            self.set_automation_callback(False)
        elif self.toggle_pause_callback is not None and self.automation_enabled:
            self.toggle_pause_callback()
        # Do NOT set self.automation_enabled = False here.
        # The next update_dashboard call will reflect the true backend state.

    def open_coach(self):
        self._pause_for_auxiliary_ui()
        from src.ui_coach import CoachUI
        if not hasattr(self, 'coach_window') or self.coach_window is None or not self.coach_window.winfo_exists():
            self.coach_window = CoachUI(self, on_close_callback=lambda: setattr(self, 'coach_window', None))
        else:
            self.coach_window.focus()
        
    def open_settings(self):
        self._pause_for_auxiliary_ui()
        from src.ui_settings import SettingsUI
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = SettingsUI(self, on_close_callback=lambda: setattr(self, 'settings_window', None))
        else:
            self.settings_window.focus()
            
    def open_trainer(self):
        self._pause_for_auxiliary_ui()
        from src.ui_trainer import TrainerUI
        if self.trainer_window is None or not self.trainer_window.winfo_exists():
            self.trainer_window = TrainerUI(self, on_close_callback=lambda: setattr(self, 'trainer_window', None))
        else:
            self.trainer_window.focus()

    def add_to_history(self, action):
        self.action_history.append(action)
        self.history_textbox.configure(state="normal")
        self.history_textbox.delete("0.0", "end")
        self.history_textbox.insert("0.0", "\n".join(reversed(self.action_history)))
        self.history_textbox.configure(state="disabled")
        
    def update_dashboard(self, mode, stable_gesture, raw_gesture, confidence, action, fps,
                         cpu_usage=0.0, ram_usage=0.0, camera_on=True, is_sleeping=False,
                         avg_latency=0, automation_enabled=True, is_resuming=False):
        """Refresh all dashboard widgets from the authoritative backend state.

        ``is_resuming`` is True while the backend is in REARM_WAITING state:
        automation is logically on but actions are blocked until the user
        removes their hand briefly.  This must display as a distinct state.
        """
        # Dynamic mode colors
        mode_colors = {
            "GENERAL": "#3a7ebf", # Blue
            "DRAW": "#2fa572",    # Green
            "MEDIA": "#e38b29"    # Orange
        }
        color = mode_colors.get(mode, "#3a7ebf")
        self._configure_if_changed("mode", self.mode_label, text=mode, text_color=color)
        
        # Dynamic confidence colors
        if confidence > 80:
            bar_color = self.accent_color
        elif confidence > 50:
            bar_color = "#e38b29" # Orange
        else:
            bar_color = "#d64545" # Red
            
        self._configure_if_changed("conf_bar_color", self.confidence_bar,
                                   progress_color=bar_color)

        self._configure_if_changed("gesture", self.gesture_label, text=stable_gesture)
        self._configure_if_changed("raw_gesture", self.raw_gesture_label, text=raw_gesture)
        self._configure_if_changed("conf", self.conf_label, text=f"Confidence: {confidence}%")

        # Smooth confidence bar animation. Driven from the cached progress
        # instead of confidence_bar.get(): a steady value then costs no Tcl
        # round trip, and it snaps to the target once the remaining step is
        # imperceptible, so an idle bar performs exactly zero set() calls.
        target_progress = confidence / 100.0
        current_progress = self._displayed_progress
        if abs(target_progress - current_progress) <= 0.01:
            smooth_progress = target_progress
        else:
            smooth_progress = current_progress + (target_progress - current_progress) * 0.35
        if smooth_progress != current_progress:
            self.confidence_bar.set(smooth_progress)
            self._displayed_progress = smooth_progress

        current_time = time.time()
        if current_time - self.last_stat_update > 0.5:
            self.last_stat_update = current_time
            self._configure_if_changed("fps", self.fps_label, text=f"Processing: {fps} fps")
            self._configure_if_changed("latency", self.latency_label, text=f"Input: {avg_latency}ms")
            self._configure_if_changed("cpu", self.cpu_label, text=f"CPU: {cpu_usage:.1f}%")
            self._configure_if_changed("ram", self.ram_label, text=f"RAM: {ram_usage:.1f} MB")

        if action and action != self._last_history_action:
            self._last_history_action = action
            self.add_to_history(action)
            
        if camera_on:
            self._configure_if_changed(
                "camera_state", self.camera_state_label,
                text="● CAMERA ACTIVE", text_color=self.accent_color)
        else:
            self._configure_if_changed(
                "camera_state", self.camera_state_label,
                text="● CAMERA DISCONNECTED", text_color="#d64545")

        # Update the UI cache ONLY from the authoritative backend value.
        self.automation_enabled = automation_enabled
        self._is_resuming = is_resuming
        if not automation_enabled:
            self._configure_if_changed(
                "automation_state", self.automation_state_label,
                text="● AUTOMATION PAUSED", text_color="#d64545")
            self._configure_pause_button("#2fa572", "#26855c")
        elif is_resuming:
            # Distinct RESUMING state: automation enabled but awaiting neutral
            self._configure_if_changed(
                "automation_state", self.automation_state_label,
                text="● RESUMING — LOWER HAND BRIEFLY", text_color="#e38b29")
            self._configure_pause_button("#d64545", "#b33939")
        elif is_sleeping:
            self._configure_if_changed(
                "automation_state", self.automation_state_label,
                text="● AUTOMATION SLEEPING", text_color="#d64545")
            self._configure_pause_button("#d64545", "#b33939")
        else:
            self._configure_if_changed(
                "automation_state", self.automation_state_label,
                text="● AUTOMATION ON", text_color=self.accent_color)
            self._configure_pause_button("#d64545", "#b33939")

    def _configure_pause_button(self, fg_color, hover_color):
        """Recolour the Pause/Resume button only when it actually changes."""
        self._configure_if_changed(
            "pause_btn", self.pause_btn, text=self._pause_button_text(),
            fg_color=fg_color, hover_color=hover_color)

    def _configure_if_changed(self, key, widget, **kwargs):
        """``widget.configure(**kwargs)`` only when a value really changed.

        This is the single most important performance guard in the UI. A
        CustomTkinter ``configure()`` is a Tcl round trip costing roughly a
        millisecond, so the previous unconditional dozen-per-tick cost 14.7 ms
        and left the Tk event loop with no idle time at all — which is exactly
        how a Tk window comes to be reported as "not responding".

        The cache is keyed per call site, so distinct widgets never share an
        entry, and a fresh key always renders (first paint is never skipped).
        """
        cache = self.__dict__.get("_configured")
        if cache is None:
            cache = {}
            self.__dict__["_configured"] = cache
        previous = cache.get(key)
        if previous is not None and len(previous) == len(kwargs) \
                and all(previous[name] == value for name, value in kwargs.items()):
            return False
        cache[key] = dict(kwargs)
        try:
            widget.configure(**kwargs)
        except Exception as exc:
            logger.debug("Widget update skipped for %s: %s", key, exc)
            return False
        return True

    def update_frame(self, frame, frame_id=None, force=False):
        """Render one preview frame.

        PERFORMANCE CONTRACT (measured, see scripts/diagnose_ui_freeze.py):
        cvtColor + PIL resize + ImageTk.PhotoImage + label.configure cost
        ~12 ms at 1280x720 on the development machine. The Tk thread runs on a
        15 ms budget, so doing that on every tick starved the Tk event loop
        and Windows reported the window as "not responding".

        Guards that make this cheap:

        1. ``self._preview_enabled`` is False while the dashboard is hidden,
           so background mode does zero conversion work.
        2. ``PreviewBudget`` rate-limits to ~24 FPS and refuses a frame that is
           already on screen, so a backlog can never be rendered.
        3. The image is resized with a single cv2 INTER_AREA pass instead of
           a full-size cvtColor followed by a PIL resize, ~3x cheaper.

        ``force`` bypasses only the *rate limit* (never the hidden check) and is
        used for synthetic status frames such as "CAMERA DISCONNECTED", which
        must appear immediately. ``frame_id`` should be the camera's own
        monotonic frame counter; ``id(frame)`` is deliberately NOT used as a
        fallback because CPython recycles ``id()`` for freed objects.
        """
        if not self._preview_enabled:
            self.frames_suppressed_hidden += 1
            return

        if frame_id is None:
            self._auto_frame_id += 1
            frame_id = self._auto_frame_id
        if not force and not self.preview_budget.should_render(True, frame_id):
            return

        target_w, target_h = self._target_size()
        if target_w is None:
            return

        try:
            # INTER_AREA is the correct filter for downscaling and avoids the
            # extra full-resolution cvtColor + PIL resize entirely.
            height, width = frame.shape[:2]
            if width != target_w or height != target_h:
                frame = cv2.resize(frame, (target_w, target_h),
                                   interpolation=cv2.INTER_AREA)
            # cv2 gives BGR; PIL wants RGB. Converting AFTER the resize means
            # the per-pixel work happens on the small image, not the 1280x720.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.current_imgtk = ImageTk.PhotoImage(image=Image.fromarray(rgb))
            self.video_label.configure(image=self.current_imgtk)
            self.current_frame_id = frame_id
            self.preview_budget.mark_rendered(frame_id, force=force)
            self.frames_rendered += 1
        except Exception as e:
            logger.debug("Frame update skipped during resize: %s", e)

    def _target_size(self):
        """Cached label size. Querying Tk geometry per frame is itself a cost."""
        now = time.perf_counter()
        if now - self._last_size_probe < 0.5:
            return self.frame_width, self.frame_height
        self._last_size_probe = now
        try:
            width = self.video_label.winfo_width()
            height = self.video_label.winfo_height()
        except Exception:
            return None
        if width > 10 and height > 10:
            # Keep even dimensions; some Tk builds handle odd ones poorly.
            self.frame_width = width - (width % 2)
            self.frame_height = height - (height % 2)
        return self.frame_width, self.frame_height
