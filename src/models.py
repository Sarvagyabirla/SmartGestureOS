from dataclasses import dataclass

@dataclass
class Landmark:
    id: int
    pixel_x: int
    pixel_y: int
    x: float
    y: float
    z: float
    world_x: float = 0.0
    world_y: float = 0.0
    world_z: float = 0.0

@dataclass
class GestureResult:
    gesture: str
    raw_gesture: str
    confidence: float
    stability: float
    reason: str = ""
