import time
from .utils import PointSmoother
import screeninfo
import ctypes

# Windows API constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800

class VirtualMouse:
    def __init__(self, min_cutoff=0.8, beta=0.2, deadzone=1.5):
        self.smoother = PointSmoother(min_cutoff=min_cutoff, beta=beta)
        self.deadzone = deadzone
        try:
            self.screen = screeninfo.get_monitors()[0]
            self.screen_w = self.screen.width
            self.screen_h = self.screen.height
        except Exception as e:
            from .logger import logger
            logger.warning(f"Failed to detect screen size: {e}. Defaulting to 1920x1080.")
            self.screen_w = 1920
            self.screen_h = 1080
            
        self.last_click_time = 0
        self.is_dragging = False
        self.last_pos = None
        
        # Pre-load windll to avoid lookup overhead
        self.user32 = ctypes.windll.user32
        
    def map_coordinates(self, x, y, cam_w, cam_h):
        # Screen Coordinate Normalization (Active center area)
        active_w = cam_w * 0.6
        active_h = cam_h * 0.6
        margin_x = (cam_w - active_w) / 2
        margin_y = (cam_h - active_h) / 2
        
        mapped_x = max(0, min(x - margin_x, active_w))
        mapped_y = max(0, min(y - margin_y, active_h))
        
        screen_x = (mapped_x / active_w) * self.screen_w
        screen_y = (mapped_y / active_h) * self.screen_h
        return screen_x, screen_y
        
    def move(self, x, y, cam_w, cam_h):
        screen_x, screen_y = self.map_coordinates(x, y, cam_w, cam_h)
        
        t = time.perf_counter()
        smooth_x, smooth_y = self.smoother.update(t, screen_x, screen_y)
        
        final_x = max(0, min(int(smooth_x), self.screen_w - 1))
        final_y = max(0, min(int(smooth_y), self.screen_h - 1))
        
        # Dead Zone implementation
        if self.last_pos:
            dist = ((final_x - self.last_pos[0])**2 + (final_y - self.last_pos[1])**2)**0.5
            if dist < self.deadzone:
                return
                
        self.last_pos = (final_x, final_y)
        
        try:
            self.user32.SetCursorPos(final_x, final_y)
        except Exception as e:
            from .logger import logger
            logger.error(f"Failed to move mouse: {e}")
                
    def click(self, button="left"):
        if button == "left":
            self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif button == "right":
            self.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            self.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            
    def double_click(self):
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            
    def scroll(self, amount):
        wheel_delta = int(amount * 120) & 0xFFFFFFFF
        self.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, wheel_delta, 0)
        
    def zoom(self, amount):
        import keyboard
        keyboard.press('ctrl')
        self.scroll(amount)
        keyboard.release('ctrl')
        
    def drag(self, start=True):
        if start and not self.is_dragging:
            self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.is_dragging = True
        elif not start and self.is_dragging:
            self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.is_dragging = False

    def release_all(self):
        """Emergency failsafe to release all mouse buttons."""
        try:
            self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        except Exception as e:
            from .logger import logger
            logger.error(f"Failed to release mouse buttons: {e}")
        self.is_dragging = False
