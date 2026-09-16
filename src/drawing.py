import cv2
import numpy as np
import os
import time
from .utils import PointSmoother, cubic_bezier_interpolation

class DrawingCanvas:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.canvas = np.zeros((height, width, 3), np.uint8)
        
        self.colors = [(255, 0, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 255, 255)]
        self.color_idx = 0
        self.color = self.colors[self.color_idx]
        
        self.brush_size = 8
        self.eraser_size = 50
        self.is_eraser = False
        
        self.smoother = PointSmoother(min_cutoff=0.5, beta=0.8)
        self.hover_smoother = PointSmoother(min_cutoff=0.1, beta=0.1)
        
        self.last_point = None
        self.is_drawing = False
        
        self.undo_stack = []
        self.redo_stack = []
        
        self._save_state()
        
    def _save_state(self):
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)
        self.undo_stack.append(self.canvas.copy())
        
    def draw(self, x, y, draw_mode=True):
        t = time.time()
        if draw_mode:
            self.hover_smoother.reset()
            smooth_x, smooth_y = self.smoother.update(t, x, y)
            sx, sy = int(smooth_x), int(smooth_y)
            
            if not self.is_drawing:
                self.is_drawing = True
                self.last_point = (sx, sy)
                self._save_state()
                self.redo_stack.clear()
                
            if self.last_point:
                if self.is_eraser:
                    cv2.circle(self.canvas, (sx, sy), self.eraser_size // 2, (0, 0, 0), cv2.FILLED)
                    cv2.line(self.canvas, self.last_point, (sx, sy), (0, 0, 0), self.eraser_size)
                else:
                    cv2.line(self.canvas, self.last_point, (sx, sy), self.color, self.brush_size, cv2.LINE_AA)
                    cv2.circle(self.canvas, (sx, sy), self.brush_size // 2, self.color, cv2.FILLED, cv2.LINE_AA)
                self.last_point = (sx, sy)
            return sx, sy
        else:
            self.smoother.reset()
            self.is_drawing = False
            self.last_point = None
            smooth_x, smooth_y = self.hover_smoother.update(t, x, y)
            return int(smooth_x), int(smooth_y)
            
    def toggle_eraser(self):
        self.is_eraser = not self.is_eraser
        
    def cycle_color(self):
        self.is_eraser = False
        self.color_idx = (self.color_idx + 1) % len(self.colors)
        self.color = self.colors[self.color_idx]
        
    def clear(self):
        self._save_state()
        self.canvas = np.zeros((self.height, self.width, 3), np.uint8)
        
    def undo(self):
        if len(self.undo_stack) > 0:
            # We don't want to pop the very first base state if possible, but 
            # if we do, we just keep canvas as empty.
            if len(self.undo_stack) > 1 or (len(self.undo_stack) == 1 and np.count_nonzero(self.canvas) > 0):
                self.redo_stack.append(self.canvas.copy())
                self.canvas = self.undo_stack.pop()
            
    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.canvas.copy())
            self.canvas = self.redo_stack.pop()
            
    def save_image(self) -> 'ActionResult':
        from src.paths import DRAWINGS_DIR
        from src.models import ActionResult
        filename = DRAWINGS_DIR / f"drawing_{int(time.time())}.png"
        success = cv2.imwrite(str(filename), self.canvas)
        if success and os.path.exists(str(filename)):
            return ActionResult(True, "save_drawing", f"Saved {filename.name}", None, time.time())
        else:
            return ActionResult(False, "save_drawing", "Failed to save drawing", "cv2.imwrite failed or file missing", time.time())
        
    def get_overlay(self, frame):
        gray = cv2.cvtColor(self.canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
        mask_inv = cv2.bitwise_not(mask)
        
        frame_bg = cv2.bitwise_and(frame, frame, mask=mask_inv)
        canvas_fg = cv2.bitwise_and(self.canvas, self.canvas, mask=mask)
        return cv2.add(frame_bg, canvas_fg)
