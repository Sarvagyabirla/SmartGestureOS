import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import get_distance, get_angle
import math

def test_distance():
    assert get_distance((0,0), (3,4)) == 5.0
