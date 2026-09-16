import customtkinter as ctk
from .settings_manager import settings_manager
from config import save_settings
import tkinter.messagebox as messagebox

class CalibrationWizard(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Calibration Wizard")
        self.geometry("400x200")
        self.attributes("-topmost", True)
        
        # Premium Colors
        from src.ui_theme import BG_COLOR, CARD_COLOR, ACCENT_COLOR, TEXT_COLOR
        self.bg_color = BG_COLOR
        self.card_color = CARD_COLOR
        self.accent_color = ACCENT_COLOR
        
        self.configure(fg_color=self.bg_color)
        
        self.label = ctk.CTkLabel(self, text="Please show a 'Peace' sign to the camera\nand hold it steady.", font=ctk.CTkFont(family="Segoe UI", size=14))
        self.label.pack(pady=30)
        
        self.cal_btn = ctk.CTkButton(self, text="Calibrate Now", command=self.do_calibrate)
        self.cal_btn.pack(pady=10)
        
    def do_calibrate(self):
        app = self.master.master
        hands_data = getattr(app, 'current_hands_data', None)
        
        if not hands_data:
            messagebox.showerror("Error", "No hand detected. Please make sure the camera can see your hand.")
            return
            
        import numpy as np
        h1 = hands_data[0]
        lms = h1['landmarks']
        wrist = np.array([lms[0].x, lms[0].y, lms[0].z])
        middle_mcp = np.array([lms[9].x, lms[9].y, lms[9].z])
        hand_size = np.linalg.norm(wrist - middle_mcp)
        
        settings_manager.settings["gestures"]["base_hand_size"] = float(hand_size)
        save_settings()
        
        messagebox.showinfo("Success", f"Calibrated! Base hand size: {hand_size:.1f}")
        self.destroy()

class SettingsUI(ctk.CTkToplevel):
    def __init__(self, master, on_close_callback=None):
        super().__init__(master)
        
        self.title("Smart Gesture OS - Settings")
        self.geometry("600x500")
        self.attributes("-topmost", True)
        self.on_close_callback = on_close_callback
        
        # Premium Colors
        self.bg_color = "#121212"
        self.card_color = "#1e1e1e"
        self.accent_color = "#00E5FF"
        self.text_color = "#FFFFFF"
        self.muted_text = "#A0A0A0"
        
        self.configure(fg_color=self.bg_color)
        
        # Typography
        self.title_font = ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        self.normal_font = ctk.CTkFont(family="Segoe UI", size=13)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Profile Section
        self.profile_frame = ctk.CTkFrame(self, fg_color=self.card_color, corner_radius=8)
        self.profile_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.profile_frame.grid_columnconfigure(1, weight=1)
        
        self.profile_label = ctk.CTkLabel(self.profile_frame, text="Current Profile:", font=self.normal_font, text_color=self.muted_text)
        self.profile_label.grid(row=0, column=0, padx=10, pady=10)
        
        self.profile_var = ctk.StringVar(value=settings_manager.current_profile)
        self.profile_dropdown = ctk.CTkOptionMenu(
            self.profile_frame, 
            values=settings_manager.get_all_profiles(), 
            variable=self.profile_var,
            command=self.on_profile_change
        )
        self.profile_dropdown.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        self.new_profile_entry = ctk.CTkEntry(self.profile_frame, placeholder_text="New Profile Name")
        self.new_profile_entry.grid(row=0, column=2, padx=10, pady=10)
        
        self.add_profile_btn = ctk.CTkButton(self.profile_frame, text="Add", width=60, command=self.add_profile)
        self.add_profile_btn.grid(row=0, column=3, padx=10, pady=10)
        
        self.calibrate_btn = ctk.CTkButton(self.profile_frame, text="Calibrate Camera", fg_color=self.bg_color, hover_color="#333333", text_color=self.accent_color, command=self.open_calibration)
        self.calibrate_btn.grid(row=1, column=0, columnspan=4, pady=(0, 10))
        
        # Tab View for organized settings
        self.tabview = ctk.CTkTabview(self, fg_color=self.card_color, segmented_button_selected_color=self.bg_color, segmented_button_selected_hover_color="#333333")
        self.tabview.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        
        self.tab_sensitivity = self.tabview.add("Sensitivity")
        self.tab_mappings = self.tabview.add("Mappings")
        
        self.build_sensitivity_tab()
        self.build_mappings_tab()
        
        # Save Button
        self.save_btn = ctk.CTkButton(self, text="Save & Close", fg_color=self.accent_color, text_color="#000000", hover_color="#00B8D4", command=self.save_and_close)
        self.save_btn.grid(row=2, column=0, padx=20, pady=20)
        
    def build_sensitivity_tab(self):
        self.tab_sensitivity.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.tab_sensitivity, text="Mouse Sensitivity:").grid(row=0, column=0, padx=10, pady=15, sticky="w")
        self.sensitivity_slider = ctk.CTkSlider(self.tab_sensitivity, from_=0.1, to=1.0, number_of_steps=90)
        self.sensitivity_slider.set(settings_manager.settings["gestures"].get("sensitivity", 0.7))
        self.sensitivity_slider.grid(row=0, column=1, padx=10, pady=15, sticky="ew")
        
        ctk.CTkLabel(self.tab_sensitivity, text="Pointer Smoothing:").grid(row=1, column=0, padx=10, pady=15, sticky="w")
        self.smoothing_slider = ctk.CTkSlider(self.tab_sensitivity, from_=1, to=20, number_of_steps=19)
        self.smoothing_slider.set(settings_manager.settings["gestures"].get("smoothing", 10))
        self.smoothing_slider.grid(row=1, column=1, padx=10, pady=15, sticky="ew")
        
        ctk.CTkLabel(self.tab_sensitivity, text="Gesture Hold Time (ms):").grid(row=2, column=0, padx=10, pady=15, sticky="w")
        self.hold_slider = ctk.CTkSlider(self.tab_sensitivity, from_=100, to=1000, number_of_steps=90)
        self.hold_slider.set(settings_manager.settings["gestures"].get("hold_time_ms", 300))
        self.hold_slider.grid(row=2, column=1, padx=10, pady=15, sticky="ew")
        
        ctk.CTkLabel(self.tab_sensitivity, text="Action Cooldown (ms):").grid(row=3, column=0, padx=10, pady=15, sticky="w")
        self.cooldown_slider = ctk.CTkSlider(self.tab_sensitivity, from_=100, to=2000, number_of_steps=190)
        self.cooldown_slider.set(settings_manager.settings["gestures"].get("cooldown_ms", 400))
        self.cooldown_slider.grid(row=3, column=1, padx=10, pady=15, sticky="ew")
        
    def build_mappings_tab(self):
        self.tab_mappings.grid_columnconfigure(1, weight=1)
        
        general_mappings = settings_manager.settings["mappings"].get("GENERAL", {})
        
        # Example editable mapping
        ctk.CTkLabel(self.tab_mappings, text="Rock On Gesture:").grid(row=0, column=0, padx=10, pady=15, sticky="w")
        self.rock_on_var = ctk.StringVar(value=general_mappings.get("Rock On", "None"))
        
        actions = ["None", "open_chrome", "open_vscode", "open_calculator", "open_explorer", "switch_mode", "play_pause"]
        self.rock_on_dropdown = ctk.CTkOptionMenu(self.tab_mappings, values=actions, variable=self.rock_on_var)
        self.rock_on_dropdown.grid(row=0, column=1, padx=10, pady=15, sticky="ew")
        
        ctk.CTkLabel(self.tab_mappings, text="Call Me Gesture:").grid(row=1, column=0, padx=10, pady=15, sticky="w")
        self.call_me_var = ctk.StringVar(value=general_mappings.get("Call Me", "None"))
        self.call_me_dropdown = ctk.CTkOptionMenu(self.tab_mappings, values=actions, variable=self.call_me_var)
        self.call_me_dropdown.grid(row=1, column=1, padx=10, pady=15, sticky="ew")

    def on_profile_change(self, selected_profile):
        settings_manager.load_profile(selected_profile)
        # Refresh UI
        self.sensitivity_slider.set(settings_manager.settings["gestures"].get("sensitivity", 0.7))
        self.smoothing_slider.set(settings_manager.settings["gestures"].get("smoothing", 10))
        self.hold_slider.set(settings_manager.settings["gestures"].get("hold_time_ms", 300))
        self.cooldown_slider.set(settings_manager.settings["gestures"].get("cooldown_ms", 400))
        
        general = settings_manager.settings["mappings"].get("GENERAL", {})
        self.rock_on_var.set(general.get("Rock On", "None"))
        self.call_me_var.set(general.get("Call Me", "None"))
        
    def add_profile(self):
        new_name = self.new_profile_entry.get().strip()
        if new_name and new_name not in settings_manager.get_all_profiles():
            settings_manager.load_profile(new_name)
            self.profile_dropdown.configure(values=settings_manager.get_all_profiles())
            self.profile_var.set(new_name)
            self.new_profile_entry.delete(0, "end")
            
    def apply_settings(self):
        settings_manager.settings["gestures"]["sensitivity"] = float(self.sensitivity_slider.get())
        settings_manager.settings["gestures"]["smoothing"] = int(self.smoothing_slider.get())
        settings_manager.settings["gestures"]["hold_time_ms"] = int(self.hold_slider.get())
        settings_manager.settings["gestures"]["cooldown_ms"] = int(self.cooldown_slider.get())
        
        if "GENERAL" not in settings_manager.settings["mappings"]:
            settings_manager.settings["mappings"]["GENERAL"] = {}
            
        settings_manager.settings["mappings"]["GENERAL"]["Rock On"] = self.rock_on_var.get()
        settings_manager.settings["mappings"]["GENERAL"]["Call Me"] = self.call_me_var.get()
        
        save_settings()
            
    def save_and_close(self):
        self.apply_settings()
        self.on_closing()
        
    def open_calibration(self):
        CalibrationWizard(self)
        
    def on_closing(self):
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()
