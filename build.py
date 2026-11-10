"""Generate the completion sounds and package the app as a Windows executable."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    subprocess.run([sys.executable, "make_slice_sounds.py"], cwd=root, check=True)
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
        "--name", "PomodoroTimer", "--exclude-module", "numpy",
        "--add-data", "slice_sounds:slice_sounds",
    ]
    if (root / "wallpaper.zip").is_file():
        args.extend(["--add-data", "wallpaper.zip:."])
    subprocess.run([*args, "PomodoroTimer.py"], cwd=root, check=True)


if __name__ == "__main__":
    main()
