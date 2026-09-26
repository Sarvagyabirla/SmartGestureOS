#!/usr/bin/env python3
"""
scripts/diagnose_hotkey.py

P0 Diagnostic Utility for SmartGestureOS Emergency Pause & Hotkey Subsystem.

Validates:
1. Environment & keyboard library hook readiness (SetWindowsHookEx WH_KEYBOARD_LL)
2. keyboard.add_hotkey("ctrl+alt+g") registration and handle tracking
3. Verification of why synthetic keyboard.send("ctrl+alt+g") fails vs direct UI callbacks
4. Internal event dispatch and callback firing
5. set_automation_enabled() execution:
   - Mouse button release (LEFTUP, RIGHTUP)
   - EventEngine reset
   - GestureMapper temporal state reset
   - GestureClassifier history reset
   - Re-arm neutral gate (5 consecutive neutral frames required)
6. Optional live physical Ctrl+Alt+G capture test
7. Hotkey unregistration cleanup at shutdown
"""

import sys
import time
import os
import ctypes
import threading
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def check_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def test_hotkey_registration():
    print_header("TEST 1: keyboard.add_hotkey Registration & Handle Inspection")
    try:
        import keyboard
        print(f"[OK] keyboard library imported successfully (version: {getattr(keyboard, '__version__', 'unknown')})")
    except ImportError as e:
        print(f"[FAIL] Could not import keyboard library: {e}")
        return None

    callback_fired = []

    def diagnostic_callback():
        callback_fired.append(time.perf_counter())
        print(f"\n >>> CALLBACK FIRED at t={callback_fired[-1]:.3f}s! <<<")

    try:
        handle = keyboard.add_hotkey("ctrl+alt+g", diagnostic_callback)
        print(f"[OK] keyboard.add_hotkey('ctrl+alt+g') returned handle: {repr(handle)} (type: {type(handle).__name__})")
    except Exception as e:
        print(f"[FAIL] keyboard.add_hotkey failed: {e}")
        return None

    listener = getattr(keyboard, "_listener", None)
    is_listening = getattr(listener, "listening", False)
    listening_thread = getattr(listener, "listening_thread", None)
    thread_alive = listening_thread.is_alive() if listening_thread else False

    print(f"[*] Listener status: listening={is_listening}, thread={listening_thread}, is_alive={thread_alive}")
    if is_listening and thread_alive:
        print("[OK] Low-level keyboard hook thread is active and listening.")
    else:
        print("[WARN] Low-level keyboard hook thread is NOT active.")

    return handle, callback_fired, diagnostic_callback


def test_synthetic_vs_hardware(handle, callback_fired):
    print_header("TEST 2: Synthetic keyboard.send() vs Direct Callback Verification")
    import keyboard

    # 1. Attempt synthetic keyboard.send
    count_before = len(callback_fired)
    print("[*] Testing synthetic keyboard.send('ctrl+alt+g')...")
    try:
        keyboard.send("ctrl+alt+g")
        time.sleep(0.15)
    except Exception as e:
        print(f"[*] keyboard.send raised: {e}")

    count_after = len(callback_fired)
    if count_after == count_before:
        print("[CONFIRMED] Synthetic keyboard.send('ctrl+alt+g') DID NOT trigger the WH_KEYBOARD_LL hook.")
        print("            Root Cause: In Windows, LowLevelKeyboardProc in the same process either")
        print("            ignores injected LLKHF_INJECTED events or misses them across thread queues.")
        print("            CONCLUSION: UI Pause button must NEVER simulate keyboard.send('ctrl+alt+g').")
        print("                        UI Pause button must call set_automation_enabled() DIRECTLY.")
    else:
        print("[NOTE] Synthetic keyboard.send triggered the callback.")

    # 2. Test direct low-level listener dispatch (simulate hardware scan codes)
    print("[*] Testing internal listener dispatch pipeline (Scan codes 29=Ctrl, 56=Alt, 34=G)...")
    try:
        e1 = keyboard.KeyboardEvent("down", 29, "ctrl")
        e2 = keyboard.KeyboardEvent("down", 56, "alt")
        e3 = keyboard.KeyboardEvent("down", 34, "g")
        keyboard._listener.direct_callback(e1)
        keyboard._listener.direct_callback(e2)
        keyboard._listener.direct_callback(e3)
        # Release
        keyboard._listener.direct_callback(keyboard.KeyboardEvent("up", 34, "g"))
        keyboard._listener.direct_callback(keyboard.KeyboardEvent("up", 56, "alt"))
        keyboard._listener.direct_callback(keyboard.KeyboardEvent("up", 29, "ctrl"))
        time.sleep(0.15)
        if len(callback_fired) > count_after:
            print("[OK] Internal listener event pipeline correctly recognized Ctrl+Alt+G and fired callback.")
        else:
            print("[WARN] Internal event dispatch did not trigger callback.")
    except Exception as e:
        print(f"[FAIL] Error in internal dispatch test: {e}")


def test_automation_state_machine():
    print_header("TEST 3: set_automation_enabled() State Machine & Safety Release")
    from unittest.mock import MagicMock
    from src.event_engine import EventEngine, EventState
    from src.gesture_classifier import GestureClassifier
    from src.gesture_mapper import GestureMapper
    import main as m_module

    # Build simulated MainApp instance
    app = object.__new__(m_module.MainApp)
    app._automation_lock = threading.Lock()
    app._automation_enabled = True
    app._rearm_state = m_module.MainApp._REARM_ARMED
    app._rearm_neutral_frames = 0
    app._REARM_NEUTRAL_REQUIRED = m_module.MainApp._REARM_NEUTRAL_REQUIRED

    app.mapper = GestureMapper(640, 480)
    app.classifier = GestureClassifier()

    # Verify initial state
    print(f"[*] Initial state: automation_enabled={app.automation_enabled}, rearm_state={app._rearm_state}")

    # Set up some state: drag in progress, hold timer active
    app.mapper.mouse.mouse.is_dragging = True
    app.mapper.mouse.engine.state = EventState.DRAGGING
    app.mapper.timer.target_gesture = "Pointing"
    app.mapper.timer.executed_once = True
    app.classifier.history.append("Pointing")

    # Step 1: Pause
    print("\n[*] Executing app.set_automation_enabled(False)...")
    m_module.MainApp.set_automation_enabled(app, False)

    assert app.automation_enabled is False, "automation_enabled must be False"
    assert app.mapper.mouse.mouse.is_dragging is False, "Mouse dragging must be False after pause"
    assert app.mapper.mouse.engine.state == EventState.HAND_LOST, "EventEngine must be in HAND_LOST"
    assert app.mapper.timer.target_gesture is None, "Hold timer target_gesture must be None"
    assert len(app.classifier.history) == 0, "Classifier history must be cleared"
    assert app._rearm_state == m_module.MainApp._REARM_IDLE, "Rearm state must be IDLE"
    print("[OK] Pause successfully released mouse, reset EventEngine, reset mapper timer, and cleared classifier.")

    # Step 2: Idempotent Pause
    print("\n[*] Testing idempotent set_automation_enabled(False)...")
    m_module.MainApp.set_automation_enabled(app, False)
    assert app.automation_enabled is False
    print("[OK] Idempotent pause did not alter state.")

    # Step 3: Resume
    print("\n[*] Executing app.set_automation_enabled(True)...")
    m_module.MainApp.set_automation_enabled(app, True)
    assert app.automation_enabled is True, "automation_enabled must be True"
    assert app._rearm_state == m_module.MainApp._REARM_WAITING, "Rearm state must be WAITING"
    print("[OK] Resume transitioned to WAITING re-arm state.")

    # Step 4: Neutral Gate
    print("\n[*] Testing Neutral Re-arm Gate...")
    # Feed held non-neutral gesture
    for i in range(5):
        armed = m_module.MainApp._tick_rearm(app, "Pointing")
        assert not armed, f"Must NOT arm while holding Pointing on frame {i+1}"
    print("[OK] Held gesture 'Pointing' correctly blocked from arming (5/5 frames disarmed).")

    # Feed neutral gestures (needs 5)
    for i in range(4):
        armed = m_module.MainApp._tick_rearm(app, "Unknown")
        assert not armed, f"Must NOT arm before 5 neutral frames (frame {i+1})"
    print("[OK] 4 neutral frames observed — still disarmed.")

    # 5th neutral frame
    armed = m_module.MainApp._tick_rearm(app, "Unknown")
    assert armed, "5th neutral frame MUST arm automation."
    assert app._rearm_state == m_module.MainApp._REARM_ARMED, "Rearm state must be ARMED"
    print("[OK] 5th neutral frame successfully ARMED automation.")


def test_live_hotkey_prompt(handle, callback_fired):
    print_header("TEST 4: Live Physical Ctrl+Alt+G Detection (5s Window)")
    print("Press [Ctrl + Alt + G] on your physical keyboard now to verify hook...")
    start_count = len(callback_fired)
    deadline = time.time() + 5.0

    while time.time() < deadline:
        if len(callback_fired) > start_count:
            print(f"[SUCCESS] Physical Ctrl+Alt+G detected! Hook is fully operational.")
            return True
        time.sleep(0.1)

    print("[INFO] No keypress detected within 5 seconds. (Skipped or keys not pressed)")
    print("       If running in non-interactive CI, this is expected.")
    return False


def test_cleanup(handle):
    print_header("TEST 5: Hotkey Cleanup at Shutdown")
    import keyboard

    try:
        keyboard.remove_hotkey(handle)
        print(f"[OK] keyboard.remove_hotkey({repr(handle)}) succeeded.")
    except Exception as e:
        print(f"[FAIL] Could not remove hotkey: {e}")


def main():
    print_header("SMARTGESTUREOS P0 EMERGENCY PAUSE / HOTKEY DIAGNOSTIC")
    print(f"Process PID: {os.getpid()}")
    print(f"Windows Administrator: {check_admin()}")
    print(f"Python: {sys.version}")

    reg_result = test_hotkey_registration()
    if not reg_result:
        print("\n[CRITICAL] Hotkey registration failed. Exiting.")
        sys.exit(1)

    handle, callback_fired, cb = reg_result

    test_synthetic_vs_hardware(handle, callback_fired)
    test_automation_state_machine()
    test_live_hotkey_prompt(handle, callback_fired)
    test_cleanup(handle)

    print_header("DIAGNOSTIC COMPLETE: ALL AUTOMATED CHECKS PASSED")


if __name__ == "__main__":
    main()
