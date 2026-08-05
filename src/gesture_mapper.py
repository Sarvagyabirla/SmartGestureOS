import time
from config import SETTINGS
from .mouse_controller import MouseController
from .keyboard_controller import KeyboardController
from .media_controller import MediaController
from .desktop_controller import DesktopController
from .shortcut_controller import ShortcutController
from .presentation_controller import PresentationController
from .volume_controller import VolumeController
from .brightness_controller import BrightnessController
from .feedback_controller import FeedbackController
from .drawing import DrawingCanvas
from .utils import get_distance
from .logger import logger

class GestureHoldTimer:
    def __init__(self, duration=0.4, repeat_cooldown=0.3):
        self.duration = duration
        self.repeat_cooldown = repeat_cooldown
        self.target_gesture = None
        self.start_time = 0
        self.last_executed = 0
        self.executed_once = False
        
    def get_progress(self):
        if not self.target_gesture or self.target_gesture == "None" or self.target_gesture == "Unknown" or self.executed_once:
            return 0.0
        now = time.time()
        progress = (now - self.start_time) / self.duration
        return max(0.0, min(1.0, progress))
        
    def check(self, gesture, is_repeatable=False):
        if not gesture or gesture == "None" or gesture == "Unknown":
            self.target_gesture = None
            self.executed_once = False
            return False
            
        if gesture != self.target_gesture:
            self.target_gesture = gesture
            self.start_time = time.time()
            self.last_executed = 0
            self.executed_once = False
            return False
            
        if not is_repeatable and self.executed_once:
            return False
            
        now = time.time()
        
        if not self.executed_once:
            if now - self.start_time >= self.duration:
                self.last_executed = now
                self.executed_once = True
                return True
        else:
            if now - self.last_executed >= self.repeat_cooldown:
                self.last_executed = now
                return True
                
        return False

class GestureMapper:
    def __init__(self, frame_w, frame_h):
        self.frame_w = frame_w
        self.frame_h = frame_h
        
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self.media = MediaController()
        self.desktop = DesktopController()
        self.shortcut = ShortcutController()
        self.presentation = PresentationController()
        self.volume = VolumeController()
        self.brightness = BrightnessController()
        self.feedback = FeedbackController()
        self.canvas = DrawingCanvas(frame_w, frame_h)
        
        self.mode = "GENERAL"
        self.modes = ["GENERAL", "MEDIA", "DRAW"]
        self.timer = GestureHoldTimer(duration=0.4, repeat_cooldown=0.3)
        self.last_pinch_time = 0
        self.last_brightness_y = None
        self.brightness_gesture_active = False
        
    def execute_action(self, action_name):
        action_map = {
            "open_vscode": self.shortcut.open_vscode,
            "open_chrome": self.shortcut.open_chrome,
            "open_calculator": self.shortcut.open_calculator,
            "open_explorer": self.shortcut.open_explorer,
            "open_notepad": self.shortcut.open_notepad,
            "lock_pc": self.shortcut.lock_pc,
            "screenshot": lambda: self.keyboard.keyboard.hotkey("win", "print screen"),
            "task_view": self.desktop.task_view,
            "show_desktop": self.desktop.show_desktop,
            "snap_left": self.shortcut.snap_left,
            "snap_right": self.shortcut.snap_right,
            "maximize": self.shortcut.maximize,
            "minimize": self.shortcut.minimize,
            "play_pause": self.media.play_pause,
            "next_track": self.media.next_track,
            "prev_track": self.media.prev_track,
            "mute": self.media.mute,
            "volume_up": self.volume.volume_up,
            "volume_down": self.volume.volume_down,
            "switch_mode": self.cycle_mode,
            "switch_to_draw": lambda: self.set_mode("DRAW"),
            "undo": self.canvas.undo,
            "redo": self.canvas.redo,
            "save_drawing": self.canvas.save_image,
            "cycle_color": self.canvas.cycle_color,
            "toggle_eraser": self.canvas.toggle_eraser
        }
        if action_name in action_map:
            action_map[action_name]()
            self.feedback.speak(action_name.replace("_", " "))
            return f"Executed: {action_name}"
        return None
        
    def set_mode(self, mode):
        if mode in self.modes:
            self.mode = mode
            logger.info(f"Switched Mode: {self.mode}")
            
    def cycle_mode(self):
        idx = self.modes.index(self.mode)
        self.mode = self.modes[(idx + 1) % len(self.modes)]
        logger.info(f"Switched Mode: {self.mode}")

    def process(self, hands_data, gesture, frame):
        action = None
        progress = self.timer.get_progress()
        
        if not hands_data:
            return frame, action, progress
            
        h1 = hands_data[0]['landmarks']
        index_x, index_y = h1[8][1], h1[8][2]
        
        mappings = SETTINGS.get("mappings", {}).get(self.mode, {})
        
        # Check global timed gestures based on mappings
        mapped_action = mappings.get(gesture)
        if mapped_action:
            is_repeatable = mapped_action in ["volume_up", "volume_down"]
            if self.timer.check(gesture, is_repeatable=is_repeatable):
                action = self.execute_action(mapped_action)
                if action:
                    return frame, action, 1.0 # 1.0 progress on execution
            progress = self.timer.get_progress() # Update progress after check
        else:
            self.timer.check(None)
            progress = 0.0

        # Mode specific immediate execution
        if self.mode == "GENERAL":
            if gesture in ["Pinch", "Closed Fist", "Pointing", "Victory", "Two Fingers", "Three Fingers"]:
                self.mouse.process_landmarks(h1, gesture, self.frame_w, self.frame_h)
            elif gesture == "Middle Finger":
                current_y = h1[12][4] # Middle finger tip Y (normalized)
                # Absolute positioning: Y=0 (top) is 100% brightness, Y=1 (bottom) is 0% brightness
                # Clamp Y between 0.2 and 0.8 to allow comfortable arm range
                clamped_y = max(0.2, min(0.8, current_y))
                brightness_perc = 1.0 - ((clamped_y - 0.2) / 0.6) # Invert so UP = 100%
                
                target_brightness = int(brightness_perc * 100)
                self.brightness.set_absolute_brightness(target_brightness)
                action = "Adjusting Brightness"

                
            if gesture != "Middle Finger":
                self.brightness_gesture_active = False
                
        elif self.mode == "DRAW":
            import cv2
            draw_mode = (gesture == "Pointing")
            sx, sy = self.canvas.draw(index_x, index_y, draw_mode=draw_mode)
            
            if not draw_mode:
                cv2.circle(frame, (sx, sy), 8, self.canvas.color, 2)
                
            if gesture == "Closed Fist":
                self.canvas.clear()
                action = "Canvas Cleared"
            frame = self.canvas.get_overlay(frame)
            
        elif self.mode == "MEDIA":
            pass # Volume is mapped globally to Thumb Up/Down now
            
        return frame, action, progress
