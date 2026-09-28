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
    """
    Simplified main dashboard — PHYSICAL RECOVERY redesign.

    REMOVED from main screen (moved to Settings/Advanced or deleted):
      - Large CPU / RAM panels (moved to status bar, updated at 2 Hz)
      - Recent-action textbox (replaced by single last-action label)
      - Confidence progress bar (replaced by numeric badge)
      - Train Custom Gesture button
      - Gesture Coach button (accessible via Settings → Advanced)
      - Developer/debug controls

    ADDED / RETAINED:
      - Camera preview (large, full right panel)
      - Large status indicator: PAUSED / RESUMING / ACTIVE / CAMERA DISCONNECTED
      - Current mode chip: GENERAL | MEDIA | DRAW
      - Current gesture label
      - ONE primary action button: Resume / Pause
      - Run in Background
      - Settings
      - Exit
      - Small manual mode selector (fallback while learning gestures)
    """
    # Class-level defaults for the render-budget / background-mode state.
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
    _configured = None

    accent_color = "#00E5FF"
    muted_text = "#8a9aa8"
    danger_color = "#d64545"
    warning_color = "#e38b29"
    success_color = "#2fa572"
    conf_badge = None
    confidence_bar = None
    conf_label = None
    raw_gesture_label = None
    gesture_label = None
    mode_label = None
    camera_state_label = None
    automation_state_label = None
    pause_btn = None
    stats_label = None
    cpu_ram_label = None
    camera_fps_label = None
    detector_fps_label = None
    inference_label = None
    fps_label = None
    latency_label = None
    cpu_label = None
    ram_label = None
    last_action_label = None
    last_action_textbox = None
    history_textbox = None
    background_status_label = None
    hotkey_status_label = None
    status_message_label = None
    hotkey_available = True
    automation_enabled = False
    _is_resuming = False
    last_stat_update = 0.0

    def __getattr__(self, name):
        # Prevent infinite recursion when uninitialized (e.g. in unit tests using object.__new__)
        if "tk" not in self.__dict__ and "_tk" not in self.__dict__:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return super().__getattr__(name)

    def __init__(self, close_callback=None, toggle_pause_callback=None,
                 set_automation_callback=None, initial_automation_enabled=False,
                 set_mode_callback=None, get_state_callback=None,
                 get_latest_preview_callback=None, show_dashboard_callback=None,
                 hide_dashboard_callback=None, quit_callback=None):
        super().__init__()

        self.title("SmartGestureOS")
        self.geometry("1000x640")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        from src.ui_theme import BG_COLOR, CARD_COLOR, SECONDARY_SURFACE, ACCENT_COLOR, TEXT_COLOR, MUTED_TEXT

        self.bg_color = BG_COLOR
        self.card_color = CARD_COLOR
        self.secondary_surface = SECONDARY_SURFACE
        self.accent_color = ACCENT_COLOR
        self.text_color = TEXT_COLOR
        self.muted_text = MUTED_TEXT

        self.configure(fg_color=self.bg_color)

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
        self.set_mode_callback = set_mode_callback
        self.get_state_callback = get_state_callback
        self.get_latest_preview_callback = get_latest_preview_callback
        self.show_dashboard_callback = show_dashboard_callback
        self.hide_dashboard_callback = hide_dashboard_callback
        self.quit_callback = quit_callback
        self.automation_enabled = bool(initial_automation_enabled)
        self._is_resuming = False
        self.hotkey_available = True
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.settings_window = None
        self.trainer_window = None
        self.last_stat_update = 0
        # Gesture test window handle
        self.gesture_test_window = None

        # ── Typography ─────────────────────────────────────────────────────────
        self._title_font  = ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        self._header_font = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self._value_font  = ctk.CTkFont(family="Segoe UI", size=18, weight="bold")
        self._normal_font = ctk.CTkFont(family="Segoe UI", size=12)
        self._small_font  = ctk.CTkFont(family="Segoe UI", size=11)
        self._status_font = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")

        # ── Left sidebar ───────────────────────────────────────────────────────
        self.sidebar_container = ctk.CTkFrame(
            self, width=270, corner_radius=0, fg_color=self.card_color
        )
        self.sidebar_container.grid(row=0, column=0, sticky="nsew")
        self.sidebar_container.grid_rowconfigure(0, weight=1)
        self.sidebar_container.grid_columnconfigure(0, weight=1)
        self.sidebar_container.grid_propagate(False)

        self.sidebar = ctk.CTkScrollableFrame(
            self.sidebar_container, width=270, corner_radius=0, fg_color=self.card_color
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)

        # App title
        ctk.CTkLabel(
            self.sidebar, text="SmartGestureOS",
            font=self._title_font, text_color=self.accent_color
        ).grid(row=0, column=0, padx=20, pady=(24, 4), sticky="w")

        ctk.CTkLabel(
            self.sidebar, text="Gesture Desktop Control",
            font=self._small_font, text_color=self.muted_text
        ).grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        # ── Big status badge ───────────────────────────────────────────────────
        self.status_badge = ctk.CTkFrame(
            self.sidebar, fg_color="#1a1a2e", corner_radius=10
        )
        self.status_badge.grid(row=2, column=0, padx=16, pady=4, sticky="ew")
        self.status_badge.grid_columnconfigure(0, weight=1)
        self.automation_state_label = ctk.CTkLabel(
            self.status_badge, text="● PAUSED",
            font=self._status_font, text_color="#d64545"
        )
        self.automation_state_label.grid(row=0, column=0, padx=16, pady=12)

        # ── Mode display ───────────────────────────────────────────────────────
        self._build_card(row=3, title="MODE")
        self.mode_label = ctk.CTkLabel(
            self._last_card, text="GENERAL",
            font=self._value_font, text_color=self.accent_color
        )
        self.mode_label.pack(anchor="w", padx=14, pady=(0, 10))

        # ── Gesture display ────────────────────────────────────────────────────
        self._build_card(row=4, title="GESTURE")
        gesture_row = ctk.CTkFrame(self._last_card, fg_color="transparent")
        gesture_row.pack(fill="x", padx=14, pady=(0, 10))
        gesture_row.grid_columnconfigure(0, weight=1)
        self.gesture_label = ctk.CTkLabel(
            gesture_row, text="None",
            font=self._value_font, text_color=self.text_color
        )
        self.gesture_label.grid(row=0, column=0, sticky="w")
        self.conf_badge = ctk.CTkLabel(
            gesture_row, text="0%",
            font=self._small_font, text_color=self.muted_text
        )
        self.conf_badge.grid(row=0, column=1, sticky="e")

        # ── Last action (compact, single line) ────────────────────────────────
        self._build_card(row=5, title="LAST ACTION")
        self.last_action_label = ctk.CTkLabel(
            self._last_card, text="—",
            font=self._normal_font, text_color=self.muted_text, anchor="w"
        )
        self.last_action_label.pack(anchor="w", padx=14, pady=(0, 10))

        # ── Manual mode selector ───────────────────────────────────────────────
        self._build_card(row=6, title="SWITCH MODE")
        mode_frame = ctk.CTkFrame(self._last_card, fg_color="transparent")
        mode_frame.pack(fill="x", padx=10, pady=(0, 10))
        mode_frame.grid_columnconfigure((0, 1, 2), weight=1)

        mode_colors = {"GENERAL": "#3a7ebf", "MEDIA": "#e38b29", "DRAW": "#2fa572"}
        for i, m in enumerate(["GENERAL", "MEDIA", "DRAW"]):
            btn = ctk.CTkButton(
                mode_frame, text=m, width=70, height=28,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                fg_color=mode_colors[m], hover_color=self._darken(mode_colors[m]),
                corner_radius=6,
                command=lambda mode=m: self._on_manual_mode(mode),
            )
            btn.grid(row=0, column=i, padx=3, pady=2, sticky="ew")

        # ── Compact perf stats (kept initialized for headless/tests/diagnostics) ──
        self.stats_label = ctk.CTkLabel(
            self.sidebar, text="Camera: — fps  |  Detector: — fps",
            font=self._small_font, text_color=self.muted_text
        )
        self.cpu_ram_label = ctk.CTkLabel(
            self.sidebar, text="CPU: —%  RAM: — MB",
            font=self._small_font, text_color=self.muted_text
        )

        # ── Camera status ──────────────────────────────────────────────────────
        self.camera_state_label = ctk.CTkLabel(
            self.sidebar, text="● CAMERA ACTIVE",
            font=self._small_font, text_color=self.accent_color
        )
        self.camera_state_label.grid(row=7, column=0, padx=20, pady=(0, 16), sticky="w")

        # ── Action buttons in sidebar bottom ───────────────────────────────────
        btn_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        btn_frame.grid(row=8, column=0, padx=16, pady=4, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)

        self.settings_btn = ctk.CTkButton(
            btn_frame, text="⚙ Settings",
            font=self._normal_font,
            command=self.open_settings,
            fg_color=self.bg_color, hover_color="#2a2a3e", corner_radius=8
        )
        self.settings_btn.pack(fill="x", pady=3)

        self.background_btn = ctk.CTkButton(
            btn_frame, text="⬚ Run in Background",
            font=self._normal_font,
            command=self.request_hide,
            fg_color=self.bg_color, hover_color="#2a2a3e", corner_radius=8
        )
        self.background_btn.pack(fill="x", pady=3)

        exit_btn = ctk.CTkButton(
            btn_frame, text="✕ Exit",
            font=self._normal_font,
            command=self.force_quit,
            fg_color="#3a1a1a", hover_color="#5a2a2a", corner_radius=8
        )
        exit_btn.pack(fill="x", pady=3)

        # ── Primary Pause/Resume button pinned at bottom of sidebar ───────────
        self.pause_btn = ctk.CTkButton(
            self.sidebar_container,
            text="▶ Resume (Ctrl+Alt+G)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self.toggle_pause,
            fg_color="#2fa572", hover_color="#26855c",
            height=44, corner_radius=0
        )
        self.pause_btn.grid(row=1, column=0, padx=0, pady=0, sticky="ew")

        self.hotkey_status_label = ctk.CTkLabel(
            self.sidebar_container,
            text="Ctrl+Alt+G pauses or resumes automation.",
            font=self._small_font, wraplength=260, text_color=self.muted_text
        )
        self.hotkey_status_label.grid(row=2, column=0, padx=16, pady=(4, 6), sticky="ew")

        self.background_status_label = ctk.CTkLabel(
            self.sidebar_container,
            text="Dashboard visible. Ctrl+Alt+Shift+G restores it.",
            font=self._small_font, wraplength=260, text_color=self.muted_text
        )
        self.background_status_label.grid(row=3, column=0, padx=16, pady=(0, 4), sticky="ew")

        self.status_message_label = ctk.CTkLabel(
            self.sidebar_container, text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            wraplength=260, text_color=self.accent_color
        )
        self.status_message_label.grid(row=4, column=0, padx=16, pady=(0, 6), sticky="ew")

        # ── Right panel: camera preview ────────────────────────────────────────
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.video_container = ctk.CTkFrame(
            self.main_frame, fg_color=self.card_color, corner_radius=14
        )
        self.video_container.grid(row=0, column=0, sticky="nsew")
        self.video_container.grid_rowconfigure(0, weight=1)
        self.video_container.grid_columnconfigure(0, weight=1)

        self.video_label = ctk.CTkLabel(self.video_container, text="")
        self.video_label.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # Welcome instructions (shown briefly, always dismissible)
        self.welcome_label = ctk.CTkLabel(
            self.main_frame,
            text=(
                "① Place one hand 30–50 cm from webcam  "
                "② Press Resume  "
                "③ Lower hand briefly  "
                "④ Point to move  •  Pinch to click"
            ),
            font=self._small_font, text_color=self.muted_text,
            justify="left", wraplength=600,
        )
        self.welcome_label.grid(row=1, column=0, padx=8, pady=(8, 0), sticky="w")

        self.current_imgtk = None
        self.frame_width = 700
        self.frame_height = 480

        # ── Render budget / background mode ───────────────────────────────────
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
        self.protocol("WM_DELETE_WINDOW", self.on_window_close)

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _darken(hex_color: str, factor: float = 0.75) -> str:
        """Return a slightly darker shade of a hex color."""
        try:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return "#{:02x}{:02x}{:02x}".format(
                int(r * factor), int(g * factor), int(b * factor)
            )
        except Exception:
            return hex_color

    def _build_card(self, row: int, title: str) -> ctk.CTkFrame:
        """Minimal section card with a muted title label."""
        frame = ctk.CTkFrame(self.sidebar, fg_color=self.bg_color, corner_radius=8)
        frame.grid(row=row, column=0, padx=14, pady=5, sticky="ew")
        ctk.CTkLabel(
            frame, text=title,
            font=self._small_font, text_color=self.muted_text
        ).pack(anchor="w", padx=14, pady=(8, 2))
        self._last_card = frame
        return frame

    def _on_manual_mode(self, mode: str) -> None:
        """Button callback: ask backend to switch to the given mode."""
        if self.set_mode_callback is not None:
            self.set_mode_callback(mode)
        self.set_mode_display(mode)

    def set_mode_display(self, mode: str) -> None:
        """Update mode label text and color in the UI."""
        mode_colors = {
            "GENERAL": "#3a7ebf",
            "DRAW":    "#2fa572",
            "MEDIA":   "#e38b29"
        }
        color = mode_colors.get(mode, "#3a7ebf")
        self._configure_if_changed("mode", getattr(self, "mode_label", None), text=mode, text_color=color)

    # ── Background control mode ────────────────────────────────────────────────

    @property
    def dashboard_visible(self) -> bool:
        return self._dashboard_visible

    @property
    def minimize_to_tray(self) -> bool:
        return self._minimize_to_tray

    def set_minimize_to_tray(self, enabled: bool) -> None:
        self._minimize_to_tray = bool(enabled)

    def set_dashboard_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if visible == self._dashboard_visible:
            return
        self._dashboard_visible = visible
        self._preview_enabled = visible
        if visible:
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
        if self.hide_dashboard_callback is not None:
            self.hide_dashboard_callback()
        else:
            self.set_dashboard_visible(False)

    def request_show(self) -> None:
        if self.show_dashboard_callback is not None:
            self.show_dashboard_callback()
        else:
            self.set_dashboard_visible(True)

    def toggle_dashboard(self) -> None:
        self.set_dashboard_visible(not self._dashboard_visible)

    def _set_background_status(self) -> None:
        if not self._dashboard_visible:
            text = "Running in background. Ctrl+Alt+Shift+G or tray icon restores it."
            color = self.accent_color
        else:
            text = "Dashboard visible. Ctrl+Alt+Shift+G restores it."
            color = self.muted_text
        try:
            self.background_status_label.configure(text=text, text_color=color)
        except Exception:
            pass

    def on_window_close(self):
        if self._minimize_to_tray:
            self.set_dashboard_visible(False)
        else:
            self.force_quit()

    def on_closing(self):
        self.on_window_close()

    def force_quit(self):
        if self.settings_window:
            try:
                self.settings_window.destroy()
            except Exception:
                pass
        if self.trainer_window:
            try:
                self.trainer_window.destroy()
            except Exception:
                pass
        if hasattr(self, 'coach_window') and self.coach_window:
            try:
                self.coach_window.destroy()
            except Exception:
                pass
        if self.gesture_test_window:
            try:
                self.gesture_test_window.destroy()
            except Exception:
                pass
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
        self.hotkey_available = bool(available)
        self.hotkey_status_label.configure(
            text=("Ctrl+Alt+G pauses or resumes automation." if available else
                  "Ctrl+Alt+G is unavailable. Use the Pause / Resume button."),
            text_color=self.muted_text if available else "#e38b29",
        )
        self.pause_btn.configure(text=self._pause_button_text())

    def set_restore_hotkey_available(self, available):
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
        try:
            self.status_message_label.configure(text=message)
            self.after(6000, lambda: self.status_message_label.configure(text=""))
        except Exception:
            logger.debug("Could not display status message.")

    def _pause_button_text(self):
        if not getattr(self, "automation_enabled", False):
            label = "Resume"
        else:
            label = "Pause"
        if getattr(self, "hotkey_available", True):
            label += " (Ctrl+Alt+G)"
        return label

    # ── Stat update ────────────────────────────────────────────────────────────

    def update_performance(self, camera_fps, detector_fps, inference_ms):
        """Display independently measured capture and inference performance."""
        if hasattr(self, 'camera_fps_label') and self.camera_fps_label is not None:
            try:
                self.camera_fps_label.configure(text=f"Camera: {camera_fps:.1f} fps")
            except Exception:
                pass
        if hasattr(self, 'detector_fps_label') and self.detector_fps_label is not None:
            try:
                self.detector_fps_label.configure(text=f"Detector: {detector_fps:.1f} fps")
            except Exception:
                pass
        if hasattr(self, 'inference_label') and self.inference_label is not None:
            try:
                self.inference_label.configure(text=f"Inference: {inference_ms:.1f} ms")
            except Exception:
                pass
        if getattr(self, "stats_label", None) is not None:
            self._configure_if_changed(
                "stats_label", self.stats_label,
                text=f"Camera: {camera_fps:.1f} fps  |  Detector: {detector_fps:.1f} fps"
            )

    def _pause_for_auxiliary_ui(self):
        if self.set_automation_callback is not None:
            self.set_automation_callback(False)
        elif self.toggle_pause_callback is not None and self.automation_enabled:
            self.toggle_pause_callback()

    # ── Auxiliary windows ──────────────────────────────────────────────────────

    def open_coach(self):
        """Coach is now accessible via Settings → Advanced."""
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

    def open_gesture_test(self):
        """Live gesture test screen — no OS actions execute inside it."""
        self._pause_for_auxiliary_ui()
        from src.ui_gesture_test import GestureTestUI
        if self.gesture_test_window is None or not self.gesture_test_window.winfo_exists():
            self.gesture_test_window = GestureTestUI(
                self,
                get_state_callback=self.get_state_callback,
                get_preview_callback=self.get_latest_preview_callback,
                on_close_callback=lambda: setattr(self, 'gesture_test_window', None)
            )
        else:
            self.gesture_test_window.focus()

    # ── History (backward compat — no longer shown in main window) ────────────

    def add_to_history(self, action):
        """Update last-action display. History textbox removed; single line kept."""
        if action:
            self._configure_if_changed(
                "last_action", getattr(self, "last_action_label", None),
                text=str(action)[:60],
                text_color=getattr(self, "accent_color", "#00E5FF"),
            )

    # ── Dashboard update ───────────────────────────────────────────────────────

    def update_dashboard(self, mode, stable_gesture, raw_gesture, confidence, action, fps,
                         cpu_usage=0.0, ram_usage=0.0, camera_on=True, is_sleeping=False,
                         avg_latency=0, automation_enabled=True, is_resuming=False):
        """Refresh all dashboard widgets from the authoritative backend state."""
        mode_colors = {
            "GENERAL": "#3a7ebf",
            "DRAW":    "#2fa572",
            "MEDIA":   "#e38b29"
        }
        color = mode_colors.get(mode, "#3a7ebf")
        self._configure_if_changed("mode", getattr(self, "mode_label", None), text=mode, text_color=color)

        # Gesture + confidence
        conf_text = f"{confidence}%"
        accent = getattr(self, "accent_color", "#00E5FF")
        muted = getattr(self, "muted_text", "#8a9aa8")
        if confidence > 70:
            conf_color = accent
        elif confidence > 40:
            conf_color = "#e38b29"
        else:
            conf_color = muted

        self._configure_if_changed("gesture", getattr(self, "gesture_label", None), text=stable_gesture)
        self._configure_if_changed("conf_badge", getattr(self, "conf_badge", None),
                                   text=conf_text, text_color=conf_color)
        self._configure_if_changed("conf_label", getattr(self, "conf_label", None), text=conf_text)
        self._configure_if_changed("raw_gesture", getattr(self, "raw_gesture_label", None), text=raw_gesture)

        # Confidence bar animation support if present
        conf_bar = getattr(self, "confidence_bar", None)
        if conf_bar is not None:
            try:
                curr_val = conf_bar.get() if hasattr(conf_bar, "get") else 0.0
                target_val = float(confidence) / 100.0
                if abs(curr_val - target_val) < 0.05:
                    conf_bar.set(target_val)
                else:
                    conf_bar.set(curr_val + (target_val - curr_val) * 0.3)
            except Exception:
                pass

        if action and action != getattr(self, "_last_history_action", None):
            self._last_history_action = action
            self.add_to_history(action)

        if camera_on:
            self._configure_if_changed(
                "camera_state", getattr(self, "camera_state_label", None),
                text="● CAMERA ACTIVE", text_color=accent)
        else:
            self._configure_if_changed(
                "camera_state", getattr(self, "camera_state_label", None),
                text="● CAMERA DISCONNECTED", text_color="#d64545")

        # Authoritative automation state
        self.automation_enabled = automation_enabled
        self._is_resuming = is_resuming

        if not automation_enabled:
            self._configure_if_changed(
                "automation_state", getattr(self, "automation_state_label", None),
                text="● AUTOMATION PAUSED", text_color="#d64545")
            self._configure_pause_button("#2fa572", "#26855c")
        elif is_resuming:
            self._configure_if_changed(
                "automation_state", getattr(self, "automation_state_label", None),
                text="● RESUMING — lower hand", text_color="#e38b29")
            self._configure_pause_button("#d64545", "#b33939")
        elif is_sleeping:
            self._configure_if_changed(
                "automation_state", getattr(self, "automation_state_label", None),
                text="● SLEEPING", text_color="#888888")
            self._configure_pause_button("#d64545", "#b33939")
        else:
            self._configure_if_changed(
                "automation_state", getattr(self, "automation_state_label", None),
                text="● AUTOMATION ON", text_color=accent)
            self._configure_pause_button("#d64545", "#b33939")

        # CPU/RAM at 2 Hz
        current_time = time.time()
        last_stat = getattr(self, "last_stat_update", 0.0)
        if current_time - last_stat > 0.5:
            self.last_stat_update = current_time
            if getattr(self, "cpu_ram_label", None) is not None:
                self._configure_if_changed(
                    "cpu_ram", self.cpu_ram_label,
                    text=f"CPU: {cpu_usage:.0f}%  RAM: {ram_usage:.0f} MB"
                )

    def _configure_pause_button(self, fg_color, hover_color):
        self._configure_if_changed(
            "pause_btn", getattr(self, "pause_btn", None),
            text=self._pause_button_text(),
            fg_color=fg_color, hover_color=hover_color)

    def _configure_if_changed(self, key, widget, **kwargs):
        """``widget.configure(**kwargs)`` only when a value really changed."""
        if widget is None:
            return False
        cache = self.__dict__.get("_configured")
        if cache is None:
            cache = {}
            self.__dict__["_configured"] = cache
        previous = cache.get(key)
        if previous is not None and len(previous) == len(kwargs) \
                and all(previous.get(name) == value for name, value in kwargs.items()):
            return False
        cache[key] = dict(kwargs)
        try:
            widget.configure(**kwargs)
        except Exception as exc:
            logger.debug("Widget update skipped for %s: %s", key, exc)
            return False
        return True

    # ── Frame rendering ────────────────────────────────────────────────────────

    def update_frame(self, frame, frame_id=None, force=False):
        """Render one preview frame.

        PERFORMANCE CONTRACT:
        cvtColor + PIL resize + ImageTk.PhotoImage + label.configure cost
        ~12 ms at 1280x720. Guards:
          1. _preview_enabled is False in background mode → zero work.
          2. PreviewBudget rate-limits to ~24 FPS.
          3. Resize after cvtColor is on the small image.
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
            height, width = frame.shape[:2]
            if width != target_w or height != target_h:
                frame = cv2.resize(frame, (target_w, target_h),
                                   interpolation=cv2.INTER_AREA)
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
            self.frame_width = width - (width % 2)
            self.frame_height = height - (height % 2)
        return self.frame_width, self.frame_height
