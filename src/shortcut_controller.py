import os
import time
import subprocess
import pyautogui
from .logger import logger

class ShortcutController:
    def __init__(self):
        self.last_open_time = 0
        
    def _open(self, cmd, cooldown=2.0):
        if time.time() - self.last_open_time > cooldown:
            try:
                subprocess.Popen(cmd, shell=True)
                self.last_open_time = time.time()
                logger.info(f"Executed shortcut: {cmd}")
            except Exception as e:
                logger.error(f"Failed to open shortcut {cmd}: {e}")
                
    def open_chrome(self):
        self._open("start chrome")
        
    def open_vscode(self):
        self._open("code")
        
    def open_explorer(self):
        self._open("explorer")
        
    def open_calculator(self):
        self._open("calc")
        
    def open_notepad(self):
        self._open("notepad")
        
    def lock_pc(self):
        self._open("rundll32.exe user32.dll,LockWorkStation")

    def snap_left(self):
        pyautogui.hotkey('win', 'left')

    def snap_right(self):
        pyautogui.hotkey('win', 'right')

    def maximize(self):
        pyautogui.hotkey('win', 'up')

    def minimize(self):
        pyautogui.hotkey('win', 'down')
