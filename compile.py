import sys
import os
import platform
import subprocess

# Determine target OS
target_os = platform.system().lower()
if len(sys.argv) > 2 and sys.argv[1] == "--os":
    target_os = sys.argv[2]

sep = ";" if target_os == "windows" else ":"

# PyInstaller command
cmd = [
    "pyinstaller",
    "--onefile",
    "--windowed",
    "--name", "NotepadApp",
    f"--add-data=Themes{sep}Themes",
    f"--add-data=*.ui{sep}.",
    f"--add-data=settings.json{sep}.",
    # Critical: Properly include qt_themes package data
    "--collect-data=qt_themes",
    # Alternative manual approach if above doesn't work:
    # f"--add-data={os.path.join(sys.prefix, 'lib', 'site-packages', 'qt_themes')}{sep}qt_themes",
    "main.py"
]

print("Running PyInstaller with command:")
print(" ".join(cmd))
subprocess.run(cmd, check=True)