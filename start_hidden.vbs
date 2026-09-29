' Launch WorkTimer minimized (no console window).
Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
ws.Run "pythonw -m worktimer.main", 0, False
