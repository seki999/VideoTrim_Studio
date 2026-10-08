"""Windows packaging smoke check: launch hidden and close only our own Qt window.

Usage: python tests/exe_smoke.py dist/VideoTrimStudio/VideoTrimStudio.exe
"""
import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
import psutil

def main():
    startup = subprocess.STARTUPINFO()
    startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    process = subprocess.Popen([str(Path(sys.argv[1]).resolve())], startupinfo=startup)
    user32 = ctypes.windll.user32
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = []
    @callback_type
    def visit(hwnd, context):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == process.pid:
            buffer = ctypes.create_unicode_buffer(1024)
            user32.GetWindowTextW(hwnd, buffer, len(buffer))
            if buffer.value == 'VideoTrim Studio': found.append(hwnd)
        return True
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and process.poll() is None:
            found.clear(); user32.EnumWindows(visit, 0)
            if found: break
            time.sleep(.1)
        if not found: raise RuntimeError('未找到应用自己的 VideoTrim Studio 窗口')
        time.sleep(3)
        while process.poll() is None and time.monotonic() < deadline:
            user32.PostMessageW(found[0], 0x0010, 0, 0)  # WM_CLOSE
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
        if process.poll() != 0: raise RuntimeError(f'启动或关闭异常：{process.poll()}')
        print(json.dumps({'window': 'VideoTrim Studio', 'exit_code': process.returncode}))
    finally:
        if process.poll() is None:
            parent = psutil.Process(process.pid)
            for child in parent.children(recursive=True): child.kill()
            parent.kill(); process.wait()

if __name__ == '__main__': main()
