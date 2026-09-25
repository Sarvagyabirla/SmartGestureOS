"""
conftest.py — pytest configuration for SmartGestureOS test suite.

Markers:
    unit        — fast, no external dependencies
    integration — may use filesystem / temp directories
    hardware    — requires physical webcam (excluded from CI)

Run:
    pytest -m "not hardware"          # CI (unit + integration)
    pytest -m hardware                # manual hardware validation
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast unit tests with no external deps")
    config.addinivalue_line("markers", "integration: tests using filesystem or temp dirs")
    config.addinivalue_line("markers", "hardware: requires a physical webcam — skip in CI")
