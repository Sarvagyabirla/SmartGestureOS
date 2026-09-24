"""
ShortcutController — safe Windows application launcher.

Uses shell=False with explicit executable paths wherever possible.
Falls back to os.startfile for simple system apps.
Never passes user-supplied strings to shell commands.
"""

import os
import time
import subprocess
import shutil
import keyboard
from .logger import logger
from .models import ActionResult


_BUILTIN_APP_NAMES = frozenset({
    "calc", "notepad", "explorer", "mspaint",
    "write", "cmd", "powershell",
})


class ShortcutController:
    def __init__(self):
        # Use perf_counter for monotonic rate-limiting (F-03 fix)
        self._last_open_time = 0.0
        self._open_cooldown = 2.0  # seconds between launches

    # ── Internal launcher (shell=False) ──────────────────────────────────────

    def _launch_exe(self, exe_path: str, args: list = None) -> ActionResult:
        """Launch an executable with shell=False. Returns ActionResult."""
        now = time.perf_counter()
        if now - self._last_open_time < self._open_cooldown:
            return ActionResult(False, "launch", "Cooldown active — launch skipped.", None)

        if not os.path.isfile(exe_path):
            msg = f"Executable not found: {exe_path}"
            logger.error(msg)
            return ActionResult(False, "launch", "Application not found.", msg)

        try:
            cmd = [exe_path] + (args or [])
            subprocess.Popen(cmd, shell=False)  # F-07: shell=False
            self._last_open_time = now
            logger.info(f"Launched: {exe_path}")
            return ActionResult(True, "launch", f"Launched {os.path.basename(exe_path)}")
        except OSError as e:
            logger.error(f"Failed to launch {exe_path}: {e}")
            return ActionResult(False, "launch", "Launch failed.", str(e))

    def _launch_system_app(self, name: str) -> ActionResult:
        """Launch a simple Windows system app by name using os.startfile."""
        now = time.perf_counter()
        if now - self._last_open_time < self._open_cooldown:
            return ActionResult(False, "launch", "Cooldown active — launch skipped.", None)
        try:
            os.startfile(name)  # Safe: no shell injection; name is a literal constant
            self._last_open_time = now
            logger.info(f"Launched system app: {name}")
            return ActionResult(True, "launch", f"Launched {name}")
        except OSError as e:
            logger.error(f"Failed to launch system app {name}: {e}")
            return ActionResult(False, "launch", f"Could not launch {name}.", str(e))

    def _find_exe(self, name_in_path: str, env_paths: list) -> str | None:
        """
        Locate an executable.
        1. Check PATH (shutil.which)
        2. Check well-known env-var–relative paths
        Returns absolute path string or None.
        """
        found = shutil.which(name_in_path)
        if found:
            return found
        for env_var, subpath in env_paths:
            base = os.environ.get(env_var, "")
            if base:
                full = os.path.join(base, subpath)
                if os.path.isfile(full):
                    return full
        return None

    # ── Public API ────────────────────────────────────────────────────────────

    def open_chrome(self) -> ActionResult:
        exe = self._find_exe("chrome.exe", [
            ("ProgramFiles",      r"Google\Chrome\Application\chrome.exe"),
            ("ProgramFiles(x86)", r"Google\Chrome\Application\chrome.exe"),
            ("LOCALAPPDATA",      r"Google\Chrome\Application\chrome.exe"),
        ])
        if exe:
            return self._launch_exe(exe)
        return ActionResult(
            False, "open_chrome",
            "Chrome not found. Install it or set it in Settings.",
            "chrome.exe not found in PATH or known install dirs",
        )

    def open_vscode(self) -> ActionResult:
        exe = self._find_exe("code.cmd", [
            ("LOCALAPPDATA", r"Programs\Microsoft VS Code\Code.exe"),
            ("ProgramFiles",  r"Microsoft VS Code\Code.exe"),
        ])
        # Fallback: look for Code.exe directly
        if not exe:
            exe = self._find_exe("Code.exe", [
                ("LOCALAPPDATA", r"Programs\Microsoft VS Code\Code.exe"),
                ("ProgramFiles",  r"Microsoft VS Code\Code.exe"),
            ])
        if exe:
            return self._launch_exe(exe)
        return ActionResult(
            False, "open_vscode",
            "VS Code not found. Install it or add it to PATH.",
            "Code.exe not found",
        )

    def open_explorer(self) -> ActionResult:
        return self._launch_system_app("explorer")

    def open_calculator(self) -> ActionResult:
        return self._launch_system_app("calc")

    def open_notepad(self) -> ActionResult:
        return self._launch_system_app("notepad")

    def lock_pc(self) -> ActionResult:
        """Lock the workstation via Win32 API (no shell)."""
        now = time.perf_counter()
        if now - self._last_open_time < self._open_cooldown:
            return ActionResult(False, "lock_pc", "Cooldown active.", None)
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            self._last_open_time = now
            logger.info("Workstation locked.")
            return ActionResult(True, "lock_pc", "PC locked.")
        except Exception as e:
            logger.error(f"Lock PC failed: {e}")
            return ActionResult(False, "lock_pc", "Failed to lock PC.", str(e))

    # ── Window management (keyboard shortcuts) ────────────────────────────────

    def snap_left(self) -> None:
        keyboard.send("windows+left")

    def snap_right(self) -> None:
        keyboard.send("windows+right")

    def maximize(self) -> None:
        keyboard.send("windows+up")

    def minimize(self) -> None:
        keyboard.send("windows+down")
