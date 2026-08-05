import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import get_distance, get_angle, Smoother
import math

def test_distance():
    assert get_distance((0,0), (3,4)) == 5.0
    
def test_smoother():
    s = Smoother(size=3, alpha=0.5)
    s.add((10, 10))
    s.get_smoothed() # Initialize
    s.add((20, 20))
    assert s.get_smoothed() == [15, 15]
    s.add((30, 30))
    assert s.get_smoothed() == [22, 22]
