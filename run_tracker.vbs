Set WshShell = CreateObject("WScript.Shell")
' 0 — запускает скрипт полностью в скрытом фоновом режиме
WshShell.Run "cmd /c cd /d """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & """ && .venv\Scripts\python.exe tracker.py", 0, False