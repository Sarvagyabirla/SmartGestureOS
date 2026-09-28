"""Test gesture validation helper script."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.validate_all_gestures import ALL_GESTURES, GestureValidatorApp


def test_gesture_validator_records_and_saves_report():
    with TemporaryDirectory() as temp_dir:
        report_file = Path(temp_dir) / "test_report.json"
        validator = GestureValidatorApp(output_path=report_file, headless=True)

        assert len(ALL_GESTURES) == 14

        for name, _ in ALL_GESTURES:
            validator.record_attempt(name, True, detected_as=name, confidence=88.5, latency_ms=105.0)

        summary = validator.save_report()

        assert report_file.exists()
        assert summary["total_attempts"] == 14
        assert summary["total_passes"] == 14
        assert summary["overall_accuracy_percent"] == 100.0

        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "Pointing" in data["gestures"]
        assert data["gestures"]["Pointing"]["passes"] == 1
        assert data["gestures"]["Pointing"]["accuracy_percent"] == 100.0
