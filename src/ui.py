import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
from collections import deque
import warnings

# Suppress the CustomTkinter warning about using PhotoImage instead of CTkImage
# We intentionally use PhotoImage to prevent memory leaks in the fast render loop.
warnings.filterwarnings("ignore", message=".*Given image is not CTkImage.*")

class SmartGestureApp(ctk.CTk):
    def __init__(self, close_callback):
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
        
        self.close_callback = close_callback
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        self.settings_window = None
        self.trainer_window = None
        self.last_stat_update = 0
        
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color=self.card_color)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(8, weight=1)
        
        # Typography
        title_font = ctk.CTkFont(family="Segoe UI", size=26, weight="bold")
        header_font = ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        value_font = ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        normal_font = ctk.CTkFont(family="Segoe UI", size=13)
        small_font = ctk.CTkFont(family="Segoe UI", size=11)
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="Gesture OS", font=title_font, text_color=self.accent_color)
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
        self.fps_label = ctk.CTkLabel(self.stats_frame, text="Rate: 0", font=normal_font, text_color=self.muted_text)
        self.fps_label.pack(side="left", expand=True)
        self.latency_label = ctk.CTkLabel(self.stats_frame, text="LAT: 0ms", font=normal_font, text_color=self.muted_text)
        self.latency_label.pack(side="left", expand=True)
        self.cpu_label = ctk.CTkLabel(self.stats_frame, text="CPU: 0%", font=normal_font, text_color=self.muted_text)
        self.cpu_label.pack(side="left", expand=True)
        self.ram_label = ctk.CTkLabel(self.stats_frame, text="RAM: 0 MB", font=normal_font, text_color=self.muted_text)
        self.ram_label.pack(side="left", expand=True)
        
        # Action Buttons
        self.btn_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.btn_frame.grid(row=8, column=0, padx=20, pady=10, sticky="ew")
        self.settings_btn = ctk.CTkButton(self.btn_frame, text="Settings", command=self.open_settings, fg_color=self.bg_color, hover_color="#333333")
        self.settings_btn.pack(fill="x", pady=4)
        self.train_btn = ctk.CTkButton(self.btn_frame, text="Train Custom Gesture", command=self.open_trainer, fg_color=self.bg_color, hover_color="#333333")
        self.train_btn.pack(fill="x", pady=4)
        self.coach_btn = ctk.CTkButton(self.btn_frame, text="Gesture Coach", command=self.open_coach, fg_color=self.accent_color, text_color="#000000", hover_color="#00B8D4")
        self.coach_btn.pack(fill="x", pady=4)
        
        self.sidebar.grid_rowconfigure(11, weight=1)
        
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
        
    def open_coach(self):
        from src.ui_coach import CoachUI
        if not hasattr(self, 'coach_window') or self.coach_window is None or not self.coach_window.winfo_exists():
            self.coach_window = CoachUI(self, on_close_callback=lambda: setattr(self, 'coach_window', None))
        else:
            self.coach_window.focus()
        
    def open_settings(self):
        from src.ui_settings import SettingsUI
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = SettingsUI(self, on_close_callback=lambda: setattr(self, 'settings_window', None))
        else:
            self.settings_window.focus()
            
    def open_trainer(self):
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
        
    def update_dashboard(self, mode, stable_gesture, raw_gesture, confidence, action, fps, cpu_usage=0.0, ram_usage=0.0, camera_on=True, is_sleeping=False, avg_latency=0):
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
            self.fps_label.configure(text=f"Rate: {fps}")
            self.latency_label.configure(text=f"LAT: {avg_latency}ms")
            self.cpu_label.configure(text=f"CPU: {cpu_usage:.1f}%")
            self.ram_label.configure(text=f"RAM: {ram_usage:.1f} MB")
            self.last_stat_update = current_time
        
        if action:
            self.add_to_history(action)
            
        if camera_on:
            self.camera_state_label.configure(text="● CAMERA ACTIVE", text_color=self.accent_color)
        else:
            self.camera_state_label.configure(text="● CAMERA DISCONNECTED", text_color="#d64545")
            
        if is_sleeping:
            self.automation_state_label.configure(text="● AUTOMATION SLEEPING", text_color="#d64545")
        else:
            self.automation_state_label.configure(text="● AUTOMATION ON", text_color=self.accent_color)

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
