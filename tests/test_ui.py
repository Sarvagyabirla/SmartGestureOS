import pytest
import customtkinter as ctk

def test_ui_startup_no_crash():
    try:
        from src.ui import SmartGestureApp
        
        # Instantiate the UI
        app = SmartGestureApp(close_callback=lambda: None)
        
        # Run a single update cycle to trigger drawing and layout
        app.update_idletasks()
        app.update()
        
        # Verify basic properties to ensure configuration was successful
        assert app.bg_color is not None
        assert app.card_color is not None
        
        # Gracefully destroy to avoid hanging the test suite
        app.destroy()
    except Exception as e:
        pytest.fail(f"UI initialization failed with exception: {e}")
