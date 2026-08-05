import mouse
import time
from .utils import PointSmoother
import screeninfo

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
        
        t = time.time()
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
            mouse.move(final_x, final_y, absolute=True, duration=0)
        except Exception as e:
            from .logger import logger
            logger.error(f"Failed to move mouse: {e}")
                
    def click(self, button="left"):
        current_time = time.time()
        if current_time - self.last_click_time > 0.3:
            mouse.click(button=button)
            self.last_click_time = current_time
            
    def double_click(self):
        current_time = time.time()
        if current_time - self.last_click_time > 0.5:
            mouse.double_click(button="left")
            self.last_click_time = current_time
            
    def scroll(self, amount):
        mouse.wheel(amount)
        
    def zoom(self, amount):
        import keyboard
        keyboard.press('ctrl')
        mouse.wheel(amount)
        keyboard.release('ctrl')
        
    def drag(self, start=True):
        if start and not self.is_dragging:
            mouse.press(button="left")
            self.is_dragging = True
        elif not start and self.is_dragging:
            mouse.release(button="left")
            self.is_dragging = False
