import os
import time
import subprocess
import keyboard
from .logger import logger

class ShortcutController:
    def __init__(self):
        self.last_open_time = 0
        
    def _open(self, cmd, cooldown=2.0):
        if time.time() - self.last_open_time > cooldown:
            import shutil
            executable = cmd.split()[0]
            if executable.lower() not in ["start", "rundll32.exe"] and not shutil.which(executable):
                raise FileNotFoundError(f"Command '{executable}' not found in PATH.")
                
            p = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            
            time.sleep(0.1) # brief wait to catch immediate failures
            if p.poll() is not None and p.returncode != 0:
                err = p.stderr.read().decode('utf-8', errors='ignore').strip()
                raise Exception(f"Launch failed: {err}")
                
            self.last_open_time = time.time()
            logger.info(f"Executed shortcut: {cmd}")
                
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
        keyboard.send('windows+left')

    def snap_right(self):
        keyboard.send('windows+right')

    def maximize(self):
        keyboard.send('windows+up')

    def minimize(self):
        keyboard.send('windows+down')
