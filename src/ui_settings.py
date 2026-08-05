import customtkinter as ctk
from .settings_manager import settings_manager
from config import save_settings
import tkinter.messagebox as messagebox

class SettingsUI(ctk.CTkToplevel):
    def __init__(self, master, on_close_callback=None):
        super().__init__(master)
        
        self.title("Smart Gesture OS - Settings")
        self.geometry("600x500")
        self.attributes("-topmost", True)
        self.on_close_callback = on_close_callback
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Profile Section
        self.profile_frame = ctk.CTkFrame(self)
        self.profile_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.profile_frame.grid_columnconfigure(1, weight=1)
        
        self.profile_label = ctk.CTkLabel(self.profile_frame, text="Current Profile:", font=ctk.CTkFont(weight="bold"))
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
        
        # Tab View for organized settings
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        
        self.tab_sensitivity = self.tabview.add("Sensitivity")
        self.tab_mappings = self.tabview.add("Mappings")
        
        self.build_sensitivity_tab()
        self.build_mappings_tab()
        
        # Save Button
        self.save_btn = ctk.CTkButton(self, text="Save & Close", command=self.save_and_close)
        self.save_btn.grid(row=2, column=0, padx=20, pady=20)
        
    def build_sensitivity_tab(self):
        self.tab_sensitivity.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.tab_sensitivity, text="Pointer Smoothing:").grid(row=0, column=0, padx=10, pady=15, sticky="w")
        self.smoothing_slider = ctk.CTkSlider(self.tab_sensitivity, from_=1, to=20, number_of_steps=19)
        self.smoothing_slider.set(settings_manager.settings["gestures"]["smoothing"])
        self.smoothing_slider.grid(row=0, column=1, padx=10, pady=15, sticky="ew")
        
        ctk.CTkLabel(self.tab_sensitivity, text="Gesture Hold Time (ms):").grid(row=1, column=0, padx=10, pady=15, sticky="w")
        self.hold_slider = ctk.CTkSlider(self.tab_sensitivity, from_=100, to=1000, number_of_steps=90)
        self.hold_slider.set(settings_manager.settings["gestures"]["hold_time_ms"])
        self.hold_slider.grid(row=1, column=1, padx=10, pady=15, sticky="ew")
        
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
        self.smoothing_slider.set(settings_manager.settings["gestures"]["smoothing"])
        self.hold_slider.set(settings_manager.settings["gestures"]["hold_time_ms"])
        
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
        settings_manager.settings["gestures"]["smoothing"] = self.smoothing_slider.get()
        settings_manager.settings["gestures"]["hold_time_ms"] = self.hold_slider.get()
        
        if "GENERAL" not in settings_manager.settings["mappings"]:
            settings_manager.settings["mappings"]["GENERAL"] = {}
            
        settings_manager.settings["mappings"]["GENERAL"]["Rock On"] = self.rock_on_var.get()
        settings_manager.settings["mappings"]["GENERAL"]["Call Me"] = self.call_me_var.get()
        
        save_settings()
            
    def save_and_close(self):
        self.apply_settings()
        self.on_closing()
        
    def on_closing(self):
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()
