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
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_columnconfigure(0, weight=1)
        
        self.title_label = ctk.CTkLabel(self, text="Train Custom Gesture", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=20)
        
        # Name Entry
        self.name_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.name_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.name_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.name_frame, text="Gesture Name:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.name_entry = ctk.CTkEntry(self.name_frame, placeholder_text="e.g. Peace Sign")
        self.name_entry.grid(row=1, column=0, sticky="ew")
        
        # Recording Status
        self.status_label = ctk.CTkLabel(self, text="Status: Ready", font=ctk.CTkFont(size=14))
        self.status_label.grid(row=2, column=0, padx=20, pady=10)
        
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.progress_bar.set(0)
        
        # Action Buttons
        self.record_btn = ctk.CTkButton(self, text="Start Recording", command=self.start_recording)
        self.record_btn.grid(row=4, column=0, padx=20, pady=20)
        
        self.instructions = ctk.CTkLabel(self, text="1. Enter a unique name for your gesture.\n2. Hold your hand in the desired pose.\n3. Click Start Recording and hold still for 3 seconds.", justify="left", text_color="gray")
        self.instructions.grid(row=5, column=0, padx=20, pady=10)
        
        # Gestures List
        self.list_frame = ctk.CTkFrame(self)
        self.list_frame.grid(row=6, column=0, padx=20, pady=10, sticky="nsew")
        self.list_frame.grid_rowconfigure(1, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.list_frame, text="Saved Gestures:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.list_text = ctk.CTkTextbox(self.list_frame, height=100)
        self.list_text.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.update_list()
        
        self.is_recording = False
        self.samples_collected = 0
        self.target_samples = 30
        
    def start_recording(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Error", "Please enter a gesture name.")
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
            success = gesture_trainer.add_sample(name, landmarks)
            if success:
                self.samples_collected += 1
                progress = self.samples_collected / self.target_samples
                self.progress_bar.set(progress)
                
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
