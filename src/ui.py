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
        
        self.title("Smart Gesture Operating System")
        self.geometry("1100x700")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.close_callback = close_callback
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        self.settings_window = None
        self.trainer_window = None
        
        # Sidebar for monitoring only
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(8, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="Gesture OS", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.mode_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.mode_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.mode_label_title = ctk.CTkLabel(self.mode_frame, text="Current Mode:", font=ctk.CTkFont(size=12))
        self.mode_label_title.pack(anchor="w")
        self.mode_label = ctk.CTkLabel(self.mode_frame, text="INITIALIZING...", font=ctk.CTkFont(size=18, weight="bold"), text_color="#3a7ebf")
        self.mode_label.pack(anchor="w")
        
        self.gesture_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.gesture_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.gesture_label_title = ctk.CTkLabel(self.gesture_frame, text="Detected Gesture:", font=ctk.CTkFont(size=12))
        self.gesture_label_title.pack(anchor="w")
        self.gesture_label = ctk.CTkLabel(self.gesture_frame, text="None", font=ctk.CTkFont(size=16, weight="bold"))
        self.gesture_label.pack(anchor="w")
        
        self.conf_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.conf_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.conf_label = ctk.CTkLabel(self.conf_frame, text="Confidence: 0%", font=ctk.CTkFont(size=12))
        self.conf_label.pack(anchor="w")
        self.confidence_bar = ctk.CTkProgressBar(self.conf_frame)
        self.confidence_bar.pack(fill="x", pady=(5, 0))
        self.confidence_bar.set(0)
        
        self.fps_label = ctk.CTkLabel(self.sidebar, text="FPS: 0", font=ctk.CTkFont(size=12))
        self.fps_label.grid(row=4, column=0, padx=20, pady=(10, 2), sticky="w")
        
        self.cpu_label = ctk.CTkLabel(self.sidebar, text="CPU: 0%", font=ctk.CTkFont(size=12))
        self.cpu_label.grid(row=5, column=0, padx=20, pady=2, sticky="w")
        
        self.ram_label = ctk.CTkLabel(self.sidebar, text="RAM: 0 MB", font=ctk.CTkFont(size=12))
        self.ram_label.grid(row=6, column=0, padx=20, pady=(2, 10), sticky="w")
        
        self.settings_btn = ctk.CTkButton(self.sidebar, text="Settings", command=self.open_settings)
        self.settings_btn.grid(row=7, column=0, padx=20, pady=10)
        
        self.train_btn = ctk.CTkButton(self.sidebar, text="Train Gesture", command=self.open_trainer)
        self.train_btn.grid(row=8, column=0, padx=20, pady=(0, 10))
        
        self.sidebar.grid_rowconfigure(9, weight=1)
        
        self.camera_state_label = ctk.CTkLabel(self.sidebar, text="Camera State: ACTIVE", font=ctk.CTkFont(size=12), text_color="#2fa572")
        self.camera_state_label.grid(row=10, column=0, padx=20, pady=5, sticky="w")
        
        self.automation_state_label = ctk.CTkLabel(self.sidebar, text="Automation State: ON", font=ctk.CTkFont(size=12), text_color="#2fa572")
        self.automation_state_label.grid(row=11, column=0, padx=20, pady=5, sticky="w")
        
        self.voice_feedback_label = ctk.CTkLabel(self.sidebar, text="Voice Feedback: ON", font=ctk.CTkFont(size=12), text_color="#2fa572")
        self.voice_feedback_label.grid(row=12, column=0, padx=20, pady=5, sticky="w")
        
        self.history_label_title = ctk.CTkLabel(self.sidebar, text="Recent Actions:", font=ctk.CTkFont(size=12, weight="bold"))
        self.history_label_title.grid(row=13, column=0, padx=20, pady=(10, 5), sticky="w")
        
        self.history_textbox = ctk.CTkTextbox(self.sidebar, height=120, state="disabled", font=ctk.CTkFont(size=11))
        self.history_textbox.grid(row=14, column=0, padx=20, pady=5, sticky="ew")
        
        self.action_history = deque(maxlen=8)
        
        # Main video frame
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        
        self.video_label = ctk.CTkLabel(self.main_frame, text="")
        self.video_label.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        self.current_imgtk = None
        self.frame_width = 750
        self.frame_height = 500

    def on_closing(self):
        if self.settings_window:
            self.settings_window.destroy()
        if self.trainer_window:
            self.trainer_window.destroy()
        if self.close_callback:
            self.close_callback()
        self.destroy()
        
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
        
    def update_dashboard(self, mode, gesture, confidence, action, fps, cpu_usage=0.0, ram_usage=0.0):
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
            bar_color = "#2fa572" # Green
        elif confidence > 50:
            bar_color = "#e38b29" # Orange
        else:
            bar_color = "#d64545" # Red
            
        self.confidence_bar.configure(progress_color=bar_color)
        
        self.gesture_label.configure(text=gesture)
        self.conf_label.configure(text=f"Confidence: {confidence}%")
        
        # Smooth confidence bar animation
        current_progress = self.confidence_bar.get()
        target_progress = confidence / 100.0
        smooth_progress = current_progress + (target_progress - current_progress) * 0.15
        self.confidence_bar.set(smooth_progress)
        
        self.fps_label.configure(text=f"FPS: {fps}")
        self.cpu_label.configure(text=f"CPU: {cpu_usage:.1f}%")
        self.ram_label.configure(text=f"RAM: {ram_usage:.1f} MB")
        
        if action:
            self.add_to_history(action)

    def update_frame(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        label_w = self.video_label.winfo_width()
        label_h = self.video_label.winfo_height()
        
        if label_w > 10 and label_h > 10:
            self.frame_width = label_w
            self.frame_height = label_h
            
        image = Image.fromarray(rgb_frame)
        image = image.resize((self.frame_width, self.frame_height))
        self.current_imgtk = ImageTk.PhotoImage(image=image)
        
        self.video_label.configure(image=self.current_imgtk)
