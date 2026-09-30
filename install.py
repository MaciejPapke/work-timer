"""Install WorkTimer on Windows: desktop shortcut + autostart + launch.

Usage (from the repo directory):
    python install.py            # stop old copies, (re)install, launch
    python install.py --reset    # ...and clear tracked data first
    python install.py --uninstall
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
APP = "WorkTimer"
PORT = 8765
VBS = REPO / "WorkTimer.vbs"
ICO = REPO / "icon.ico"


def pythonw():
    exe = Path(sys.executable).with_name("pythonw.exe")
    return str(exe) if exe.exists() else (shutil.which("pythonw.exe") or "pythonw.exe")


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def kill_running():
    pids = set()
    for line in _run(["netstat", "-ano"]).stdout.splitlines():
        if f":{PORT}" in line and "LISTENING" in line:
            pids.add(line.split()[-1])
    for pid in pids:
        _run(["taskkill", "/PID", pid, "/F"])
    return pids


def reset_data():
    from worktimer import config
    for suffix in ("", "-wal", "-shm"):
        p = Path(config.DB_PATH + suffix)
        if p.exists():
            p.unlink()


def write_launcher():
    # Quote the exe path inside the VBS string literal with "" escapes, so the
    # autostart script is valid even if the path contains spaces.
    VBS.write_text(
        'Set s = CreateObject("WScript.Shell")\n'
        f's.CurrentDirectory = "{REPO}"\n'
        f's.Run """{pythonw()}"" -m worktimer.main", 0, False\n',
        encoding="ascii",
    )


def make_icon():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 61, 61], radius=14, fill=(37, 99, 235, 255))
    d.ellipse([16, 16, 47, 47], outline=(255, 255, 255, 255), width=3)
    d.line([31, 31, 31, 20], fill=(255, 255, 255, 255), width=3)
    d.line([31, 31, 40, 36], fill=(255, 255, 255, 255), width=3)
    img.save(ICO, format="ICO", sizes=[(64, 64)])
    return ICO


def desktop_dir():
    import win32com.client
    return Path(win32com.client.Dispatch("WScript.Shell").SpecialFolders("Desktop"))


def make_shortcut(desktop, icon):
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    sc = shell.CreateShortCut(str(desktop / f"{APP}.lnk"))
    sc.TargetPath = pythonw()
    sc.Arguments = "-m worktimer.main"
    sc.WorkingDirectory = str(REPO)
    if icon:
        sc.IconLocation = f"{icon},0"
    sc.Save()


def set_autostart(enable):
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    try:
        if enable:
            winreg.SetValueEx(key, APP, 0, winreg.REG_SZ, f'wscript.exe "{VBS}"')
        else:
            try:
                winreg.DeleteValue(key, APP)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def launch():
    subprocess.Popen(
        [pythonw(), "-m", "worktimer.main"],
        cwd=str(REPO),
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )


def main():
    args = sys.argv[1:]
    if "--uninstall" in args:
        kill_running()
        set_autostart(False)
        try:
            (desktop_dir() / f"{APP}.lnk").unlink()
        except FileNotFoundError:
            pass
        print("Uninstalled: stopped, removed autostart and desktop shortcut.")
        return

    killed = kill_running()
    if "--reset" in args:
        reset_data()
    write_launcher()
    icon = make_icon()
    make_shortcut(desktop_dir(), icon)
    set_autostart(True)
    launch()
    print(f"Installed. Stopped {len(killed)} old instance(s), autostart on, "
          f"desktop shortcut created, launched.")


if __name__ == "__main__":
    main()
