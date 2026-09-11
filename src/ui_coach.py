import customtkinter as ctk

class CoachUI(ctk.CTkToplevel):
    def __init__(self, master, on_close_callback=None):
        super().__init__(master)
        self.title("Gesture Coach")
        self.geometry("500x300")
        self.attributes("-topmost", True)
        self.on_close_callback = on_close_callback
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        from src.ui_theme import BG_COLOR
        self.configure(fg_color=BG_COLOR)
        lbl = ctk.CTkLabel(self, text="Gesture Coach", font=ctk.CTkFont(size=24, weight="bold"))
        lbl.pack(pady=20)
        
        desc = ctk.CTkLabel(self, text="Select a gesture to see how to perform it properly:", font=ctk.CTkFont(size=14))
        desc.pack(pady=10)
        
        self.gesture_var = ctk.StringVar(value="Pinch")
        self.dropdown = ctk.CTkOptionMenu(
            self, 
            values=["Pinch", "Open Palm", "Closed Fist", "Two Fingers", "Three Fingers", "Victory", "Rock On"], 
            variable=self.gesture_var,
            command=self.update_instructions
        )
        self.dropdown.pack(pady=10)
        
        self.instruction_lbl = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=14), wraplength=400)
        self.instruction_lbl.pack(pady=20)
        self.update_instructions(self.gesture_var.get())
        
    def update_instructions(self, g):
        instructions = {
            "Pinch": "Bring the tips of your thumb and index finger together. Make sure your hand is facing the camera.",
            "Open Palm": "Extend all five fingers out flat and separate them slightly.",
            "Closed Fist": "Curl all your fingers tightly into your palm.",
            "Two Fingers": "Extend your index and middle fingers, keeping them close together.",
            "Three Fingers": "Extend your index, middle, and ring fingers.",
            "Victory": "Extend your index and middle fingers, spreading them wide in a 'V' shape.",
            "Rock On": "Extend your index and pinky fingers while curling the others."
        }
        self.instruction_lbl.configure(text=instructions.get(g, "Practice this gesture to improve accuracy."))
        
    def on_closing(self):
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()
