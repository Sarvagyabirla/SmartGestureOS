from dataclasses import dataclass
from typing import Optional

@dataclass
class Landmark:
    id: int
    x: float
    y: float
    z: float
    pixel_x: int
    pixel_y: int
    world_x: Optional[float] = None
    world_y: Optional[float] = None
    world_z: Optional[float] = None

@dataclass
class GestureResult:
    gesture: str
    raw_gesture: str
    confidence: float
    stability: float
    reason: str = ""

@dataclass
class ActionResult:
    success: bool
    action: str
    message: str
    error: Optional[str] = None
    timestamp: Optional[float] = None
