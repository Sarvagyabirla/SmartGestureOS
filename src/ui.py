import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
from collections import deque
import warnings
from src.logger import logger

# Suppress the CustomTkinter warning about using PhotoImage instead of CTkImage
# We intentionally use PhotoImage to prevent memory leaks in the fast render loop.
warnings.filterwarnings("ignore", message=".*Given image is not CTkImage.*")

class SmartGestureApp(ctk.CTk):
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

    def on_closing(self):
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
        self.mode_label.configure(text=mode, text_color=color)
        
        # Dynamic confidence colors
        if confidence > 80:
            bar_color = self.accent_color
        elif confidence > 50:
            bar_color = "#e38b29" # Orange
        else:
            bar_color = "#d64545" # Red
            
        self.confidence_bar.configure(progress_color=bar_color)
        
        self.gesture_label.configure(text=stable_gesture)
        self.raw_gesture_label.configure(text=raw_gesture)
        self.conf_label.configure(text=f"Confidence: {confidence}%")
        
        # Smooth confidence bar animation
        current_progress = self.confidence_bar.get()
        target_progress = confidence / 100.0
        smooth_progress = current_progress + (target_progress - current_progress) * 0.15
        self.confidence_bar.set(smooth_progress)
        
        import time
        current_time = time.time()
        if current_time - self.last_stat_update > 0.5:
            self.fps_label.configure(text=f"Processing: {fps} fps")
            self.latency_label.configure(text=f"Input: {avg_latency}ms")
            self.cpu_label.configure(text=f"CPU: {cpu_usage:.1f}%")
            self.ram_label.configure(text=f"RAM: {ram_usage:.1f} MB")
            self.last_stat_update = current_time
        
        if action:
            self.add_to_history(action)
            
        if camera_on:
            self.camera_state_label.configure(text="● CAMERA ACTIVE", text_color=self.accent_color)
        else:
            self.camera_state_label.configure(text="● CAMERA DISCONNECTED", text_color="#d64545")

        # Update the UI cache ONLY from the authoritative backend value.
        self.automation_enabled = automation_enabled
        self._is_resuming = is_resuming
        if not automation_enabled:
            self.automation_state_label.configure(text="● AUTOMATION PAUSED", text_color="#d64545")
            self.pause_btn.configure(text=self._pause_button_text(), fg_color="#2fa572", hover_color="#26855c")
        elif is_resuming:
            # Distinct RESUMING state: automation enabled but awaiting neutral
            self.automation_state_label.configure(
                text="● RESUMING — LOWER HAND BRIEFLY", text_color="#e38b29"
            )
            self.pause_btn.configure(text=self._pause_button_text(), fg_color="#d64545", hover_color="#b33939")
        elif is_sleeping:
            self.automation_state_label.configure(text="● AUTOMATION SLEEPING", text_color="#d64545")
            self.pause_btn.configure(text=self._pause_button_text(), fg_color="#d64545", hover_color="#b33939")
        else:
            self.automation_state_label.configure(text="● AUTOMATION ON", text_color=self.accent_color)
            self.pause_btn.configure(text=self._pause_button_text(), fg_color="#d64545", hover_color="#b33939")

    def update_frame(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        label_w = self.video_label.winfo_width()
        label_h = self.video_label.winfo_height()
        
        if label_w > 10 and label_h > 10:
            self.frame_width = label_w
            self.frame_height = label_h
            
        try:
            image = Image.fromarray(rgb_frame)
            image = image.resize((self.frame_width, self.frame_height))
            self.current_imgtk = ImageTk.PhotoImage(image=image)
            
            self.video_label.configure(image=self.current_imgtk)
        except Exception as e:
            from src.logger import logger
            logger.debug(f"Frame update skipped during resize: {e}")
