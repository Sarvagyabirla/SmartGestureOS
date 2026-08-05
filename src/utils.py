import math
import numpy as np
from collections import deque

def smoothing_factor(t_e, cutoff):
    r = 2 * math.pi * cutoff * t_e
    return r / (r + 1)

def exponential_smoothing(a, x, x_prev):
    return a * x + (1 - a) * x_prev

class OneEuroFilter:
    def __init__(self, t0, x0, dx0=0.0, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        
        self.x_prev = float(x0)
        self.dx_prev = float(dx0)
        self.t_prev = float(t0)

    def __call__(self, t, x):
        t_e = t - self.t_prev
        if t_e <= 0.0:
            return self.x_prev
            
        a_d = smoothing_factor(t_e, self.d_cutoff)
        dx = (x - self.x_prev) / t_e
        dx_hat = exponential_smoothing(a_d, dx, self.dx_prev)
        
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = smoothing_factor(t_e, cutoff)
        x_hat = exponential_smoothing(a, x, self.x_prev)
        
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        
        return x_hat

class PointSmoother:
    def __init__(self, min_cutoff=1.0, beta=0.0):
        self.filter_x = None
        self.filter_y = None
        self.min_cutoff = min_cutoff
        self.beta = beta

    def update(self, t, x, y):
        if self.filter_x is None:
            self.filter_x = OneEuroFilter(t, x, min_cutoff=self.min_cutoff, beta=self.beta)
            self.filter_y = OneEuroFilter(t, y, min_cutoff=self.min_cutoff, beta=self.beta)
            return x, y
        else:
            nx = self.filter_x(t, x)
            ny = self.filter_y(t, y)
            return nx, ny

    def reset(self):
        self.filter_x = None
        self.filter_y = None

def get_distance(p1, p2):
    """Returns distance between two points"""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def get_angle(p1, p2, p3):
    """Calculate angle between three points (p2 is vertex)"""
    a = get_distance(p1, p2)
    b = get_distance(p2, p3)
    c = get_distance(p1, p3)
    if a == 0 or b == 0:
        return 0
    cos_angle = (a**2 + b**2 - c**2) / (2 * a * b)
    # Clip cos_angle to avoid math domain errors
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))

def cubic_bezier_interpolation(p0, p1, p2, p3, num_points=10):
    """Generates points on a cubic Bezier curve."""
    pts = []
    for i in range(num_points + 1):
        t = i / num_points
        x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
        y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
        pts.append((int(x), int(y)))
    return pts
