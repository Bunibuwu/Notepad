import sys, os, platform, subprocess

target_os = "auto"
if len(sys.argv) > 2 and sys.argv[1] == "--os":
    target_os = sys.argv[2]
else:
    target_os = platform.system().lower()

sep = ";" if target_os == "windows" else ":"

cmd = [
    "pyinstaller",
    "--onefile",
    "--windowed",
    "--name", "NotepadApp",
    f"--add-data=Themes{sep}Themes",
    f"--add-data=*.ui{sep}.",
    f"--add-data=settings.json{sep}.",
    "main.py"
]

subprocess.run(cmd, check=True)
