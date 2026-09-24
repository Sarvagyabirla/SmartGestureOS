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
                
    def _find_and_open(self, executable_name, env_paths, fallback_command):
        import shutil
        import os
        from .logger import logger
        
        # 1. Check PATH
        path_exe = shutil.which(executable_name)
        if path_exe:
            self._open(f'"{path_exe}"')
            return True
            
        # 2. Check common env paths
        for env_var, subpath in env_paths:
            base_dir = os.environ.get(env_var)
            if base_dir:
                full_path = os.path.join(base_dir, subpath)
                if os.path.exists(full_path):
                    self._open(f'"{full_path}"')
                    return True
                    
        # 3. Fallback
        try:
            self._open(fallback_command)
            return True
        except Exception as e:
            logger.error(f"Failed to find or launch {executable_name}: {e}")
            raise

    def open_chrome(self):
        env_paths = [
            ("ProgramFiles", r"Google\Chrome\Application\chrome.exe"),
            ("ProgramFiles(x86)", r"Google\Chrome\Application\chrome.exe"),
            ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe")
        ]
        self._find_and_open("chrome.exe", env_paths, "start chrome")
        
    def open_vscode(self):
        env_paths = [
            ("LOCALAPPDATA", r"Programs\Microsoft VS Code\Code.exe"),
            ("ProgramFiles", r"Microsoft VS Code\Code.exe")
        ]
        self._find_and_open("code.cmd", env_paths, "code")
        
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
