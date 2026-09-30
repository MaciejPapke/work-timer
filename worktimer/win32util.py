"""Win32 window enumeration and input-idle detection."""
import os

import win32api
import win32con
import win32gui
import win32process

_cache = {}  # pid -> exe basename (or None)


def _exe_of_pid(pid):
    if pid in _cache:
        return _cache[pid]
    exe = None
    try:
        flags = win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ
        h = win32api.OpenProcess(flags, False, pid)
        try:
            path = win32process.GetModuleFileNameEx(h, 0)
            exe = os.path.basename(path).lower()
        finally:
            win32api.CloseHandle(h)
    except Exception:
        exe = None
    _cache[pid] = exe
    return exe


def exe_of_hwnd(hwnd):
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return None
    return _exe_of_pid(pid)


def foreground_hwnd():
    return win32gui.GetForegroundWindow()


def foreground_exe():
    hwnd = foreground_hwnd()
    return exe_of_hwnd(hwnd) if hwnd else None


def idle_ms():
    """Milliseconds since the last keyboard/mouse input."""
    return win32api.GetTickCount() - win32api.GetLastInputInfo()


def enumerate_states():
    """Return a list of (exe, state) for every top-level window worth counting."""
    fg = foreground_hwnd()
    out = []

    def cb(hwnd, _extra):
        exe = exe_of_hwnd(hwnd)
        if exe:
            if hwnd == fg:
                state = "focused"
            elif win32gui.IsIconic(hwnd):
                state = "minimized"
            elif win32gui.IsWindowVisible(hwnd):
                state = "visible"
            else:
                return True
            out.append((exe, state))
        return True

    win32gui.EnumWindows(cb, None)
    return out
