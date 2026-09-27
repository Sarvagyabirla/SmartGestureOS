import customtkinter as ctk

# The same names are shown by the classifier and used in profile mappings.
GESTURE_INSTRUCTIONS = {
    "Pointing": "Extend your index finger and curl the others. Move the cursor in GENERAL mode or draw in DRAW mode.",
    "Pinch": "Bring your thumb and index fingertips together. Release quickly to click; hold to drag, then release to drop.",
    "Two Fingers": "Extend your index and middle fingers, keeping them close together.",
    "Three Fingers": "Extend your index, middle, and ring fingers.",
    "Middle Finger": "Extend only your middle finger while keeping the others curled into your palm.",
    "Victory": "Extend your index and middle fingers, spreading them wide in a V shape.",
    "Rock On": "Extend your index and pinky fingers while curling the others.",
    "Four Fingers": "Extend your index, middle, ring, and pinky fingers. Fold your thumb into your palm.",
    "Thumb Up": "Curl all four fingers into a fist and extend your thumb straight up.",
    "Thumb Down": "Curl all four fingers into a fist and point your thumb straight down.",
    "Open Palm": "Extend all five fingers out flat and separate them slightly.",
    "Closed Fist": "Curl all your fingers tightly into your palm.",
    "Crossed Fingers": "Cross your middle finger over the back of your index finger.",
    "Call Me": "Extend your thumb and pinky while curling the middle three fingers. Hold to switch mode.",
}

class CoachUI(ctk.CTkToplevel):
    def __init__(self, master, on_close_callback=None):
        super().__init__(master)
        self.title("Gesture Coach")
        self.geometry("500x360")
        self.attributes("-topmost", True)
        self.on_close_callback = on_close_callback
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        from src.ui_theme import BG_COLOR
        self.configure(fg_color=BG_COLOR)
        lbl = ctk.CTkLabel(self, text="Gesture Coach", font=ctk.CTkFont(size=24, weight="bold"))
        lbl.pack(pady=20)
        
        desc = ctk.CTkLabel(self, text="Automation is paused so you can practice safely.\nSelect a gesture to learn its hand pose:", font=ctk.CTkFont(size=14))
        desc.pack(pady=10)
        
        self.gesture_var = ctk.StringVar(value="Pinch")
        self.dropdown = ctk.CTkOptionMenu(
            self, 
            values=list(GESTURE_INSTRUCTIONS),
            variable=self.gesture_var,
            command=self.update_instructions
        )
        self.dropdown.pack(pady=10)
        
        self.instruction_lbl = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=14), wraplength=400)
        self.instruction_lbl.pack(pady=20)
        self.update_instructions(self.gesture_var.get())
        
    def update_instructions(self, g):
        self.instruction_lbl.configure(text=GESTURE_INSTRUCTIONS.get(g, "Practice this gesture to improve accuracy."))
        
    def on_closing(self):
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()
