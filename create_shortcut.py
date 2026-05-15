import os
import sys
import subprocess
import winreg

script_dir = os.path.dirname(os.path.abspath(__file__))

try:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
    desktop = winreg.QueryValueEx(key, "Desktop")[0]
    winreg.CloseKey(key)
except Exception:
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")

shortcut = os.path.join(desktop, "Image Sheet Generator.lnk")
pythonw = sys.executable.replace("python.exe", "pythonw.exe")
if not os.path.exists(pythonw):
    pythonw = sys.executable

target = os.path.join(script_dir, "app.py")

vbs = f"""Set shell = WScript.CreateObject("WScript.Shell")
Set link = shell.CreateShortcut("{shortcut}")
link.TargetPath = "{pythonw}"
link.Arguments = "{target}"
link.WorkingDirectory = "{script_dir}"
link.Description = "Image Sheet Generator"
link.Save
"""

vbs_path = os.path.join(script_dir, "_tmp_shortcut.vbs")
with open(vbs_path, "w") as f:
    f.write(vbs)

subprocess.run(["cscript", "//nologo", vbs_path])
os.remove(vbs_path)

print(f"Shortcut created on Desktop: {shortcut}")
input("Press Enter to close...")
