import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.keyboard_controller import KeyboardController

@patch('src.keyboard_controller.VirtualKeyboard.press_key')
@patch('src.keyboard_controller.VirtualKeyboard.hotkey')
def test_keyboard_controller(mock_hotkey, mock_press):
    controller = KeyboardController()
    
    # Test enter
    controller.process_gesture("Pinch")
    mock_press.assert_called_with("enter")
    
    # Test debounce
    controller.process_gesture("Pinch")
    assert mock_press.call_count == 1
    
    # Test copy
    controller.process_gesture("Peace")
    mock_hotkey.assert_called_with("ctrl", "c")
    
    # Test space
    controller.process_gesture("Open Palm")
    mock_press.assert_called_with("space")
