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
        now = time.perf_counter()
        progress = (now - self.start_time) / self.duration
        return max(0.0, min(1.0, progress))
        
    def check(self, gesture, is_repeatable=False):
        if not gesture or gesture == "None" or gesture == "Unknown":
            self.target_gesture = None
            self.executed_once = False
            return False
            
        if gesture != self.target_gesture:
            self.target_gesture = gesture
            self.start_time = time.perf_counter()
            self.last_executed = 0
            self.executed_once = False
            return False
            
        if not is_repeatable and self.executed_once:
            return False
            
        now = time.perf_counter()
        
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
        self.sleep_timer = GestureHoldTimer(duration=3.0, repeat_cooldown=3.0)
        self.is_sleeping = False
        
        self.action_registry = {
            "open_vscode": {"func": self.shortcut.open_vscode, "repeatable": False},
            "open_chrome": {"func": self.shortcut.open_chrome, "repeatable": False},
            "open_calculator": {"func": self.shortcut.open_calculator, "repeatable": False},
            "open_explorer": {"func": self.shortcut.open_explorer, "repeatable": False},
            "open_notepad": {"func": self.shortcut.open_notepad, "repeatable": False},
            "lock_pc": {"func": self.shortcut.lock_pc, "repeatable": False},
            "screenshot": {"func": self.desktop.take_screenshot, "repeatable": False},
            "task_view": {"func": self.desktop.task_view, "repeatable": False},
            "show_desktop": {"func": self.desktop.show_desktop, "repeatable": False},
            "snap_left": {"func": self.shortcut.snap_left, "repeatable": False},
            "snap_right": {"func": self.shortcut.snap_right, "repeatable": False},
            "maximize": {"func": self.shortcut.maximize, "repeatable": False},
            "minimize": {"func": self.shortcut.minimize, "repeatable": False},
            "play_pause": {"func": self.media.play_pause, "repeatable": False},
            "next_track": {"func": self.media.next_track, "repeatable": False},
            "prev_track": {"func": self.media.prev_track, "repeatable": False},
            "mute": {"func": self.media.mute, "repeatable": False},
            "volume_up": {"func": self.volume.volume_up, "repeatable": True},
            "volume_down": {"func": self.volume.volume_down, "repeatable": True},
            "switch_mode": {"func": self.cycle_mode, "repeatable": False},
            "switch_to_draw": {"func": lambda: self.set_mode("DRAW"), "repeatable": False},
            "undo": {"func": self.canvas.undo, "repeatable": True},
            "redo": {"func": self.canvas.redo, "repeatable": True},
            "save_drawing": {"func": self.canvas.save_image, "repeatable": False},
            "cycle_color": {"func": self.canvas.cycle_color, "repeatable": False},
            "toggle_eraser": {"func": self.canvas.toggle_eraser, "repeatable": False},
            "clear_canvas": {"func": self.canvas.clear, "repeatable": False},
            "toggle_sleep": {"func": lambda: None, "repeatable": False} # Handled explicitly in process()
        }
        
        from src.settings_manager import settings_manager
        settings_manager.register_callback(self.on_settings_changed)
        self.on_settings_changed()
        
    def on_settings_changed(self):
        from config import SETTINGS
        hold_time_ms = SETTINGS.get("gestures", {}).get("hold_time_ms", 300)
        cooldown_ms = SETTINGS.get("gestures", {}).get("cooldown_ms", 500)
        self.timer.duration = hold_time_ms / 1000.0
        self.timer.repeat_cooldown = cooldown_ms / 1000.0
        
    def execute_action(self, action_name):
        if action_name in self.action_registry:
            try:
                # Safety: release all mouse input before lock_pc to prevent stuck buttons
                if action_name == "lock_pc":
                    self.mouse.release_all()
                res = self.action_registry[action_name]["func"]()
                self.feedback.speak(action_name.replace("_", " "))
                if hasattr(res, "success"): # Support for ActionResult
                    if res.success:
                        return f"Executed: {action_name}"
                    else:
                        return f"Failed: {action_name}"
                return f"Executed: {action_name}"
            except Exception as e:
                from .logger import logger
                logger.error(f"Action '{action_name}' failed: {e}")
                return f"Failed: {action_name}"
        return None
        
    def set_mode(self, mode):
        if mode in self.modes:
            self.mode = mode
            self.mouse.release_all()
            self.brightness_gesture_active = False
            logger.info(f"Switched Mode: {self.mode}")
            
    def cycle_mode(self):
        idx = self.modes.index(self.mode)
        self.set_mode(self.modes[(idx + 1) % len(self.modes)])

    def get_sleep_gesture(self, mappings):
        for g, action_name in mappings.items():
            if action_name == "toggle_sleep":
                return g
        return None

    def process(self, hands_data, stable_gesture, raw_gesture, frame):
        import cv2
        action = None
        progress = self.timer.get_progress()
        gesture = stable_gesture
        
        if not hands_data:
            self.mouse.engine.on_hand_lost()
            return frame, action, progress
            
        h1 = hands_data[0]['landmarks']
        index_x, index_y = h1[8].pixel_x, h1[8].pixel_y
        
        mappings = SETTINGS.get("mappings", {}).get(self.mode, {})
        sleep_gesture = self.get_sleep_gesture(mappings)
        
        # Check sleep/wake toggle
        gesture = stable_gesture
        if sleep_gesture and gesture == sleep_gesture:
            if self.sleep_timer.check(sleep_gesture):
                self.is_sleeping = not self.is_sleeping
                self.feedback.speak("Sleeping" if self.is_sleeping else "Waking up")
                self.mouse.release_all()
                return frame, "System Sleeping" if self.is_sleeping else "System Woke Up", 1.0
        else:
            self.sleep_timer.check(None)
            
        if self.is_sleeping:
            msg = f"Zzz... (Hold {sleep_gesture} to Wake)" if sleep_gesture else "Zzz... (No Wake Gesture Mapped)"
            cv2.putText(frame, msg, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            sleep_prog = self.sleep_timer.get_progress() if (sleep_gesture and gesture == sleep_gesture) else 0.0
            return frame, "Sleeping", sleep_prog

        # Identify if current gesture maps to a continuous/movement action
        mapped_action = mappings.get(gesture)
        raw_mapped_action = mappings.get(raw_gesture)
        
        continuous_actions = ["click", "drag", "scroll", "move"] # concept for general mode
        
        # Mode specific execution (Continuous)
        if self.mode == "GENERAL":
            # Pass raw_gesture to mouse controller so it can move cursor immediately
            self.mouse.process_landmarks(h1, stable_gesture, raw_gesture, self.frame_w, self.frame_h)
                
            if gesture == "Middle Finger":
                current_y = h1[12].y
                self.brightness.set_brightness_from_y(current_y)
                action = "Adjusting Brightness"
                
            if gesture != "Middle Finger":
                self.brightness_gesture_active = False

        elif self.mode == "DRAW":
            draw_mode = (raw_gesture == "Pointing") or (gesture == "Pointing")
            sx, sy = self.canvas.draw(index_x, index_y, draw_mode=draw_mode)
            
            if not draw_mode:
                import cv2
                cv2.circle(frame, (sx, sy), 8, self.canvas.color, 2)
                
            frame = self.canvas.get_overlay(frame)

        # Discrete Actions
        if mapped_action == "toggle_sleep":
            self.timer.check(None)
            progress = self.sleep_timer.get_progress()
        elif mapped_action:
            action_info = self.action_registry.get(mapped_action, {})
            is_repeatable = action_info.get("repeatable", False)
            if self.timer.check(gesture, is_repeatable=is_repeatable):
                action = self.execute_action(mapped_action)
                if action:
                    return frame, action, 1.0
            progress = self.timer.get_progress()
        else:
            self.timer.check(None)

        return frame, action, progress

    def cleanup(self):
        if hasattr(self, 'mouse'):
            self.mouse.release_all()
        if hasattr(self, 'feedback'):
            self.feedback.stop()
