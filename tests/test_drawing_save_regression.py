"""Drawing exports must work for Windows accounts with Unicode folder names."""

from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src.drawing import DrawingCanvas


def test_drawing_saves_exact_png_under_unicode_directory(tmp_path, monkeypatch):
    drawings = tmp_path / "dessins_\u00e9_\u65e5\u672c"
    drawings.mkdir()
    monkeypatch.setattr("src.paths.DRAWINGS_DIR", drawings)
    canvas = DrawingCanvas(40, 30)
    canvas.draw(20, 15)

    first = canvas.save_image()
    second = canvas.save_image()

    assert first.success, first
    assert second.success, second
    saved = list(drawings.glob("*.png"))
    assert len(saved) == 2
    for path in saved:
        actual = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(actual, canvas.canvas)


def test_drawing_write_failure_returns_action_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("src.paths.DRAWINGS_DIR", tmp_path)
    canvas = DrawingCanvas(40, 30)

    with patch.object(Path, "write_bytes", side_effect=PermissionError("folder is read-only")):
        result = canvas.save_image()

    assert not result.success
    assert result.action == "save_drawing"
    assert "read-only" in result.error


def test_drawing_encode_failure_returns_action_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("src.paths.DRAWINGS_DIR", tmp_path)
    canvas = DrawingCanvas(40, 30)

    with patch("src.drawing.cv2.imencode", side_effect=cv2.error("PNG encoder failed")):
        result = canvas.save_image()

    assert not result.success
    assert result.action == "save_drawing"
    assert "PNG encoder failed" in result.error
