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
            monitors = screeninfo.get_monitors()
            primary = next((m for m in monitors if getattr(m, 'is_primary', False)), monitors[0])
            self.screen = primary
            self.screen_x = getattr(primary, 'x', 0)
            self.screen_y = getattr(primary, 'y', 0)
            self.screen_w = primary.width
            self.screen_h = primary.height
        except Exception as e:
            from .logger import logger
            logger.warning(f"Failed to detect screen size: {e}. Defaulting to 1920x1080.")
            self.screen_x = 0
            self.screen_y = 0
            self.screen_w = 1920
            self.screen_h = 1080
            
        self.last_click_time = 0
        self.is_dragging = False
        self.last_pos = None

        # Pointer-path telemetry. ``updates`` counts accepted cursor updates,
        # ``suppressed`` counts samples the deadzone swallowed while the
        # pointer was live. Together they give a real pointer-update rate
        # instead of an assumed frame rate.
        self.updates = 0
        self.suppressed = 0

        # Pre-load windll to avoid lookup overhead
        self.user32 = ctypes.windll.user32
        
    def map_coordinates(self, x, y, cam_w, cam_h):
        cam_w = max(1, cam_w)
        cam_h = max(1, cam_h)
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
        """Issue one cursor update. Returns True when Windows was asked to move.

        Called from the FAST POINTER PATH on every fresh valid inference
        result while pointer intent is active — never from a hold timer and
        never gated on the discrete-action path.
        """
        screen_x, screen_y = self.map_coordinates(x, y, cam_w, cam_h)

        t = time.perf_counter()
        smooth_x, smooth_y = self.smoother.update(t, screen_x, screen_y)

        offset_x = getattr(self, 'screen_x', 0)
        offset_y = getattr(self, 'screen_y', 0)
        final_x = max(offset_x, min(int(round(smooth_x)) + offset_x, offset_x + self.screen_w - 1))
        final_y = max(offset_y, min(int(round(smooth_y)) + offset_y, offset_y + self.screen_h - 1))

        # Dead zone implementation. Rounding (not truncation) before the
        # comparison keeps sub-pixel drift from stalling a deliberate slow
        # move: truncation biases every filtered value downwards and would
        # discard roughly half of all 1-pixel steps.
        if self.last_pos:
            dist = ((final_x - self.last_pos[0])**2 + (final_y - self.last_pos[1])**2)**0.5
            if dist < self.deadzone:
                self.suppressed += 1
                return False

        self.last_pos = (final_x, final_y)

        try:
            self.user32.SetCursorPos(final_x, final_y)
        except Exception as e:
            from .logger import logger
            logger.error(f"Failed to move mouse: {e}")
            return False
        self.updates += 1
        return True
                
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

    def reset_pointer_filter(self):
        """Drop smoothed pointer history without emitting a mouse event.

        Used when pointer intent ends cleanly (a conflicting gesture, a mode
        change, a pause) so the next pointer session starts from the user's
        current screen position instead of dragging a stale trail. This does
        NOT touch button state — that is :meth:`release_all`'s job.
        """
        self.last_pos = None
        self.smoother.reset()

    def release_all(self):
        """Release mouse buttons and discard coordinates from previous tracking."""
        try:
            self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        except Exception as e:
            from .logger import logger
            logger.error(f"Failed to release mouse buttons: {e}")
        finally:
            self.is_dragging = False
            self.last_pos = None
            self.smoother.reset()
