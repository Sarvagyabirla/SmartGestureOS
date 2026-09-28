"""
tests/test_interaction_engine_quality.py
Deterministic regressions for the final interaction quality engine (Section 76):
- Canonical settings consistency across config, safe defaults, and controllers
- Active profile effective values and safe migration
- Pointer confidence-aware immediate entry & guarded entry
- No-hand immediate exit vs Unknown bounded grace
- Pointing -> Pinch transition & click anchor
- Immediate single click on pinch release
- Two single events producing natural double click (no triple click)
- Drag transition continuity (no smoother-reset jump) & adaptive drag intent
- Scroll bounds & velocity scaling
- Right-click release gate
- Action-specific hold times
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call
import pytest

from src.settings_manager import SettingsManager, _SAFE_DEFAULTS
from src.pointer_path import PointerIntent
from src.event_engine import EventEngine, EventState
from src.virtual_mouse import VirtualMouse
from src.gesture_classifier import GestureClassifier
from src.gesture_mapper import GestureMapper


# ---------------------------------------------------------------------------
# 1. Canonical Settings Consistency
# ---------------------------------------------------------------------------

def test_canonical_settings_consistency():
    defaults_path = Path(__file__).resolve().parent.parent / "config" / "defaults.json"
    with open(defaults_path, "r", encoding="utf-8") as f:
        file_defaults = json.load(f)

    # Check gestures section
    for k in ["sensitivity", "smoothing", "pointer_enter_samples", "pointer_grace_ms"]:
        assert file_defaults["gestures"][k] == _SAFE_DEFAULTS["gestures"][k], (
            f"Drift in gestures.{k}: {file_defaults['gestures'][k]} vs {_SAFE_DEFAULTS['gestures'][k]}"
        )

    # Check calibration section
    for k in [
        "confidence_threshold",
        "pinch_enter_threshold",
        "pinch_release_threshold",
        "two_finger_max_spacing",
        "victory_min_spacing",
        "active_roi_margin",
        "pointer_extension_ratio",
    ]:
        assert file_defaults["calibration"][k] == _SAFE_DEFAULTS["calibration"][k], (
            f"Drift in calibration.{k}: {file_defaults['calibration'][k]} vs {_SAFE_DEFAULTS['calibration'][k]}"
        )


def test_active_profile_safe_migration():
    stale_profile = {
        "calibration": {
            "confidence_threshold": 50.0,
            "two_finger_max_spacing": 0.2,
            "victory_min_spacing": 0.35,
        },
        "gestures": {
            "sensitivity": 0.75,
            "smoothing": 2,
        },
        "camera": {"index": 1},
        "mappings": {"CUSTOM_POSE": "action_test"},
    }

    changed = SettingsManager._migrate_profile_data(stale_profile)
    assert changed is True
    assert stale_profile["calibration"]["confidence_threshold"] == 35.0
    assert stale_profile["calibration"]["two_finger_max_spacing"] == 0.22
    assert stale_profile["calibration"]["victory_min_spacing"] == 0.30
    assert stale_profile["gestures"]["pointer_enter_samples"] == 2
    assert stale_profile["gestures"]["pointer_grace_ms"] == 100.0
    # Preserves user choices:
    assert stale_profile["camera"]["index"] == 1
    assert stale_profile["mappings"]["CUSTOM_POSE"] == "action_test"


# ---------------------------------------------------------------------------
# 2. Pointer Confidence-Aware Entry & Exit
# ---------------------------------------------------------------------------

def test_pointer_strong_confidence_immediate_entry():
    p = PointerIntent(enter_samples=2, grace_ms=100.0)
    # High confidence (>= 60%) activates immediately on first frame
    active = p.update("Pointing", now=1.0, confidence=75.0)
    assert active is True
    assert p.active is True


def test_pointer_weak_confidence_guarded_entry():
    p = PointerIntent(enter_samples=2, grace_ms=100.0)
    # Moderate confidence (< 60%) requires 2 consecutive samples
    active1 = p.update("Pointing", now=1.0, confidence=50.0)
    assert active1 is False
    assert p.active is False

    active2 = p.update("Pointing", now=1.033, confidence=50.0)
    assert active2 is True
    assert p.active is True


def test_pointer_no_hand_immediate_exit():
    p = PointerIntent(enter_samples=2, grace_ms=100.0)
    p.update("Pointing", now=1.0, confidence=80.0)
    assert p.active is True

    # Real hand loss has NO grace period
    active = p.update("", now=1.033, confidence=0.0)
    assert active is False
    assert p.active is False


def test_pointer_unknown_bounded_grace():
    p = PointerIntent(enter_samples=2, grace_ms=100.0)
    p.update("Pointing", now=1.0, confidence=80.0)
    assert p.active is True

    # Unknown with fresh hand gets up to 100ms grace
    active_in_grace = p.update("Unknown", now=1.050, confidence=20.0)
    assert active_in_grace is True

    # After grace period expires, it exits
    active_expired = p.update("Unknown", now=1.150, confidence=20.0)
    assert active_expired is False


# ---------------------------------------------------------------------------
# 3. Pinch, Immediate Single Click, Double Click, and Click Anchor
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_engine_pipeline():
    clock = SimpleNamespace(now=10.0)
    mouse = MagicMock()
    mouse.get_cursor_pos.return_value = (500, 400)
    mouse.map_coordinates.return_value = (500, 400)
    engine = EventEngine(SimpleNamespace(mouse=mouse))

    with patch("src.event_engine.time.perf_counter", side_effect=lambda: clock.now):
        def tick(elapsed, raw, stable=None, x=500, y=400):
            clock.now = 10.0 + elapsed
            landmarks = [SimpleNamespace(y=y / 720.0) for _ in range(21)]
            engine.process(
                stable if stable is not None else raw,
                raw,
                x,
                y,
                1280,
                720,
                landmarks,
                confidence=70.0,
            )

        yield engine, mouse, tick, clock


def test_click_anchor_captured_on_pinch(mock_engine_pipeline):
    engine, mouse, tick, _ = mock_engine_pipeline
    tick(0.0, "Pointing")
    tick(0.033, "Pinch")
    assert engine.state == EventState.PINCH_DOWN
    assert engine.click_anchor == (500, 400)


def test_immediate_single_click_emission(mock_engine_pipeline):
    engine, mouse, tick, clock = mock_engine_pipeline
    tick(0.0, "Pinch")
    assert engine.state == EventState.PINCH_DOWN

    # Short pinch release -> click emitted immediately!
    tick(0.066, "Pointing")
    mouse.click.assert_called_once_with(button="left")
    assert engine.state == EventState.PINCH_RELEASE_WAIT

    # Advance past double-click window -> no extra click emitted
    tick(0.066 + engine.double_click_window_ms + 0.05, "Pointing")
    assert engine.state == EventState.HOVER
    assert mouse.click.call_count == 1


def test_two_pinches_produce_natural_double_click_no_triple(mock_engine_pipeline):
    engine, mouse, tick, _ = mock_engine_pipeline
    # First pinch & release
    tick(0.0, "Pinch")
    tick(0.066, "Pointing")
    assert mouse.click.call_count == 1
    assert engine.state == EventState.PINCH_RELEASE_WAIT

    # Second pinch & release within window
    tick(0.150, "Pinch")
    assert engine.state == EventState.PINCH_DOWN
    tick(0.200, "Pointing")
    # Emits second click immediately, creating a natural OS double-click
    assert mouse.click.call_count == 2
    assert engine.state == EventState.COOLDOWN

    # Wait past cooldown
    tick(0.500, "Pointing")
    assert engine.state == EventState.HOVER
    # Verify no triple-click
    assert mouse.click.call_count == 2


# ---------------------------------------------------------------------------
# 4. Drag Continuity & Adaptive Drag Intent
# ---------------------------------------------------------------------------

def test_adaptive_drag_intent_with_motion(mock_engine_pipeline):
    engine, mouse, tick, _ = mock_engine_pipeline
    # Start pinch at (500, 400)
    tick(0.0, "Pinch", x=500, y=400)
    mouse.map_coordinates.return_value = (500, 400)

    # 130 ms later, hand moves to (530, 430) -> displacement ~42px >= 16px
    mouse.map_coordinates.return_value = (530, 430)
    tick(0.130, "Pinch", x=530, y=430)

    assert engine.state == EventState.DRAGGING
    mouse.seed_smoother.assert_called_once_with(500, 400)
    mouse.drag.assert_called_once_with(start=True)


def test_adaptive_drag_intent_with_hold_duration(mock_engine_pipeline):
    engine, mouse, tick, _ = mock_engine_pipeline
    tick(0.0, "Pinch", x=500, y=400)
    # Stationary hold past drag_hold_ms (350ms)
    tick(0.360, "Pinch", x=500, y=400)
    assert engine.state == EventState.DRAGGING
    mouse.drag.assert_called_once_with(start=True)


# ---------------------------------------------------------------------------
# 5. Scroll Bounds & Right Click Gate
# ---------------------------------------------------------------------------

def test_scroll_bounds_clamped(mock_engine_pipeline):
    engine, mouse, tick, _ = mock_engine_pipeline
    tick(0.0, "Two Fingers", y=100)
    assert engine.state == EventState.SCROLLING

    # Large sudden jump
    tick(0.05, "Two Fingers", y=700)
    assert mouse.scroll.call_count == 1
    # Clamped to -3 <= ticks <= 3
    amount = mouse.scroll.call_args[0][0]
    assert -3 <= amount <= 3


def test_right_click_release_gate(mock_engine_pipeline):
    engine, mouse, tick, _ = mock_engine_pipeline
    tick(0.0, "Three Fingers")
    assert engine.state == EventState.COOLDOWN
    mouse.click.assert_called_once_with(button="right")

    # While held across frames, no repeat
    tick(0.2, "Three Fingers")
    tick(0.4, "Three Fingers")
    assert mouse.click.call_count == 1


# ---------------------------------------------------------------------------
# 6. Action-Specific Hold Times
# ---------------------------------------------------------------------------

def test_action_specific_hold_times():
    mapper = GestureMapper(1280, 720)
    # Continuous volume actions require 200ms initial confirmation
    assert mapper.get_hold_time("volume_up") == 0.200
    assert mapper.get_hold_time("volume_down") == 0.200

    # High-impact and discrete actions maintain 300ms base hold
    assert mapper.get_hold_time("screenshot") == 0.300
    assert mapper.get_hold_time("launch_app:notepad") == 0.300


# ---------------------------------------------------------------------------
# 7. Section 10: Canonical Mappings Consistency Across Config, Docs, and UI
# ---------------------------------------------------------------------------

def test_canonical_mappings_consistency():
    repo_root = Path(__file__).resolve().parent.parent
    defaults_path = repo_root / "config" / "defaults.json"
    with open(defaults_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    mappings = config.get("mappings", {})

    # 1. GENERAL Mode Mappings
    general = mappings.get("GENERAL", {})
    assert general.get("Victory") == "open_vscode"
    assert general.get("Rock On") == "open_chrome"
    assert general.get("Four Fingers") == "screenshot"
    assert general.get("Thumb Up") == "volume_up"
    assert general.get("Thumb Down") == "volume_down"
    assert general.get("Open Palm") == "task_view"
    assert general.get("Closed Fist") == "show_desktop"
    assert general.get("Crossed Fingers") == "lock_pc"
    assert general.get("Call Me") == "switch_mode"

    # 2. MEDIA Mode Mappings
    media = mappings.get("MEDIA", {})
    assert media.get("Pinch") == "play_pause"
    assert media.get("Victory") == "next_track"
    assert media.get("Three Fingers") == "prev_track"
    assert media.get("Closed Fist") == "mute"
    assert media.get("Call Me") == "switch_mode"

    # 3. DRAW Mode Mappings
    draw = mappings.get("DRAW", {})
    assert draw.get("Victory") == "undo"
    assert draw.get("Three Fingers") == "redo"
    assert draw.get("Four Fingers") == "save_drawing"
    assert draw.get("Thumb Up") == "cycle_color"
    assert draw.get("Thumb Down") == "toggle_eraser"
    assert draw.get("Closed Fist") == "clear_canvas"
    assert draw.get("Call Me") == "switch_mode"

    # 4. GestureMapper registry has all mapped actions
    mapper = GestureMapper(1280, 720)
    for mode_map in [general, media, draw]:
        for gesture, action in mode_map.items():
            assert action in mapper.action_registry, f"Action {action} not in GestureMapper registry"
            assert callable(mapper.action_registry[action]["func"]), f"Action {action} func not callable"

    # 5. Coach UI instructions include all 14 canonical gestures
    from src.ui_coach import GESTURE_INSTRUCTIONS
    from src.ui_gesture_test import ALL_GESTURES
    assert len(GESTURE_INSTRUCTIONS) == 14
    assert len(ALL_GESTURES) == 14
    for g in ALL_GESTURES:
        assert g in GESTURE_INSTRUCTIONS, f"Gesture {g} missing from Coach instructions"

    # 6. GESTURES.md and README.md reference the 14 gestures
    gestures_doc = (repo_root / "GESTURES.md").read_text(encoding="utf-8")
    readme_doc = (repo_root / "README.md").read_text(encoding="utf-8")
    for g in ALL_GESTURES:
        assert g in gestures_doc, f"Gesture {g} not found in GESTURES.md"
        assert g in readme_doc, f"Gesture {g} not found in README.md"
