import customtkinter as ctk
import time
from .gesture_trainer import gesture_trainer
import tkinter.messagebox as messagebox

class TrainerUI(ctk.CTkToplevel):
    def __init__(self, master, on_close_callback=None):
        super().__init__(master)
        
        self.title("Smart Gesture OS - Train Custom Gesture")
        self.geometry("400x500")
        self.attributes("-topmost", True)
        self.on_close_callback = on_close_callback
        
        # Premium Colors
        from src.ui_theme import BG_COLOR, CARD_COLOR, ACCENT_COLOR
        self.bg_color = BG_COLOR
        self.card_color = CARD_COLOR
        self.accent_color = ACCENT_COLOR
        self.text_color = "#FFFFFF"
        self.muted_text = "#A0A0A0"
        
        self.configure(fg_color=self.bg_color)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_columnconfigure(0, weight=1)
        
        self.title_label = ctk.CTkLabel(self, text="Train Custom Gesture", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color=self.accent_color)
        self.title_label.grid(row=0, column=0, padx=20, pady=20)
        
        # Name Entry
        self.name_frame = ctk.CTkFrame(self, fg_color=self.card_color, corner_radius=8)
        self.name_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.name_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.name_frame, text="Gesture Name:", font=ctk.CTkFont(family="Segoe UI", size=13), text_color=self.muted_text).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))
        self.name_entry = ctk.CTkEntry(self.name_frame, placeholder_text="e.g. Peace Sign", fg_color=self.bg_color, border_width=0)
        self.name_entry.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        
        # Recording Status
        self.status_label = ctk.CTkLabel(self, text="Status: Ready", font=ctk.CTkFont(family="Segoe UI", size=14))
        self.status_label.grid(row=2, column=0, padx=20, pady=10)
        
        self.progress_bar = ctk.CTkProgressBar(self, height=8, fg_color=self.card_color, progress_color=self.accent_color)
        self.progress_bar.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.progress_bar.set(0)
        
        # Action Buttons
        self.record_btn = ctk.CTkButton(self, text="Start Recording", fg_color=self.accent_color, text_color="#000000", hover_color="#00B8D4", command=self.start_recording)
        self.record_btn.grid(row=4, column=0, padx=20, pady=20)
        
        self.instructions = ctk.CTkLabel(self, text="1. Enter a unique name for your gesture.\n2. Hold your hand in the desired pose.\n3. Click Start Recording and hold still for 3 seconds.", justify="left", text_color=self.muted_text, font=ctk.CTkFont(family="Segoe UI", size=12))
        self.instructions.grid(row=5, column=0, padx=20, pady=10)
        
        # Gestures List
        self.list_frame = ctk.CTkFrame(self, fg_color=self.card_color, corner_radius=8)
        self.list_frame.grid(row=6, column=0, padx=20, pady=10, sticky="nsew")
        self.list_frame.grid_rowconfigure(1, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.list_frame, text="Saved Gestures", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), text_color=self.muted_text).grid(row=0, column=0, padx=15, pady=10, sticky="w")
        
        self.list_text = ctk.CTkTextbox(self.list_frame, height=100, fg_color=self.bg_color, font=ctk.CTkFont(family="Segoe UI", size=12))
        self.list_text.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.update_list()
        
        self.is_recording = False
        self.samples_collected = 0
        self.target_samples = 30
        
    def start_recording(self):
        name = self.name_entry.get().strip()
        from .gesture_trainer import validate_gesture_name
        is_valid, msg = validate_gesture_name(name)
        if not is_valid:
            messagebox.showwarning("Error", msg)
            return
            
        self.is_recording = True
        self.samples_collected = 0
        self.record_btn.configure(state="disabled")
        self.status_label.configure(text="Status: Recording... Hold Still!", text_color="orange")
        self.progress_bar.set(0)
        self.record_loop(name)
        
    def record_loop(self, name):
        if not self.is_recording:
            return
            
        hands_data = getattr(self.master, 'current_hands_data', None)
        
        if hands_data and len(hands_data) > 0:
            landmarks = hands_data[0]['landmarks']
            success, msg = gesture_trainer.add_sample(name, landmarks)
            if success:
                self.samples_collected += 1
                progress = self.samples_collected / self.target_samples
                self.progress_bar.set(progress)
            else:
                self.status_label.configure(text=f"Error: {msg}", text_color="red")
                self.is_recording = False
                self.record_btn.configure(state="normal")
                return
                
        if self.samples_collected < self.target_samples:
            self.after(100, lambda: self.record_loop(name)) # Record sample every 100ms
        else:
            self.is_recording = False
            gesture_trainer.save_models()
            self.status_label.configure(text="Status: Saved Successfully!", text_color="green")
            self.record_btn.configure(state="normal")
            self.name_entry.delete(0, "end")
            self.update_list()
            
    def update_list(self):
        self.list_text.configure(state="normal")
        self.list_text.delete("0.0", "end")
        for g_name, samples in gesture_trainer.custom_gestures.items():
            self.list_text.insert("end", f"• {g_name} ({len(samples)} samples)\n")
        self.list_text.configure(state="disabled")
        
    def on_closing(self):
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()
