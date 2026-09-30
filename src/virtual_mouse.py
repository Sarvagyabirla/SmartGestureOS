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
    # Pointer-path telemetry. ``updates`` counts accepted cursor updates and
    # ``suppressed`` counts samples the dead zone swallowed while the pointer
    # was live; together they give a real pointer-update rate instead of an
    # assumed frame rate.
    #
    # Declared at class scope on purpose: instrumentation must never be able
    # to break cursor movement. Instances built without __init__ (a real
    # construction path used by the test doubles) still get sane counters,
    # and the first += rebinds an instance attribute.
    updates = 0
    suppressed = 0

    def __init__(self, min_cutoff=0.8, beta=0.2, deadzone=1.5):
        self.smoother = PointSmoother(min_cutoff=min_cutoff, beta=beta)
        self.deadzone = deadzone
        self.active_roi_margin = 0.20
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

        # Pre-load windll to avoid lookup overhead
        self.user32 = ctypes.windll.user32

    def get_cursor_pos(self) -> tuple[int, int]:
        """Query current cursor position.

        Prefers self.last_pos if VirtualMouse has an active tracked position;
        otherwise queries OS GetCursorPos or falls back to screen center.
        """
        if self.last_pos is not None:
            return self.last_pos
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        try:
            if self.user32.GetCursorPos(ctypes.byref(pt)):
                return (int(pt.x), int(pt.y))
        except Exception:
            pass
        return (self.screen_w // 2, self.screen_h // 2)

    def seed_smoother(self, screen_x: float, screen_y: float) -> None:
        """Seed the One-Euro filter from a known screen position.

        Section 31: On drag start or transition, primes the filter so that
        the first drag movement starts smoothly from the current cursor position
        or click anchor without any first-frame jump.
        """
        t = time.perf_counter()
        self.smoother.reset()
        self.smoother.update(t, screen_x, screen_y)
        self.last_pos = (int(round(screen_x)), int(round(screen_y)))

    def map_coordinates(self, x, y, cam_w, cam_h):
        """Map camera pixel coordinates to primary monitor screen coordinates.

        Section 14-16: Uses normalized ROI defined by active_roi_margin.
        Inside the central region, coordinates map linearly for precision.
        Near ROI edges, a smooth continuous soft-extension (tanh shaping)
        ensures screen edges are reachable without a harsh clamp cliff.
        """
        import math
        cam_w = max(1, cam_w)
        cam_h = max(1, cam_h)
        margin = getattr(self, "active_roi_margin", 0.20)
        margin = max(0.05, min(0.40, float(margin)))
        active_span = 1.0 - 2.0 * margin

        # Normalized camera coordinates [0, 1]
        nx = max(0.0, min(1.0, x / cam_w))
        ny = max(0.0, min(1.0, y / cam_h))

        # Map to active range [-0.5, 0.5] centered
        cx = (nx - 0.5) / active_span
        cy = (ny - 0.5) / active_span

        # Soft edge shaping: linear in [-0.45, 0.45], smooth gain near edges
        def _soft_edge(v: float) -> float:
            if v > 0.5:
                return 0.5 + 0.05 * math.tanh((v - 0.5) / 0.05)
            elif v < -0.5:
                return -0.5 + 0.05 * math.tanh((v + 0.5) / 0.05)
            return v

        mapped_u = _soft_edge(cx) + 0.5
        mapped_v = _soft_edge(cy) + 0.5

        # Clamp to valid screen bounds [0, 1]
        mapped_u = max(0.0, min(1.0, mapped_u))
        mapped_v = max(0.0, min(1.0, mapped_v))

        screen_x = mapped_u * self.screen_w
        screen_y = mapped_v * self.screen_h
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
        """Emit a Windows mouse click with deterministic down/up interval."""
        if button == "left":
            self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.010)
            self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif button == "right":
            self.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            time.sleep(0.015)
            self.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            
    def double_click(self):
        """Emit two consecutive clicks within Windows double-click timing at exact coordinates."""
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.010)
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.030)
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.010)
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

    def invalidate_interaction(self, reason: str = "reset"):
        """Centralized safety invalidation for VirtualMouse."""
        self.release_all()
