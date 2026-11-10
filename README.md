# Samurai Pomodoro Timer

A Windows focus timer with a full-screen flip clock, local task lists and subtasks, and a floating countdown that follows you when you switch apps.

Hover at the left edge for the sidebar. Hover near the bottom center for Start, Stop, and Reset. Open Tasks from the sidebar, use **+** to add a list, and double-click a tab to rename it. Hover over a task to see its subtasks. Completing a task or subtask plays one of ten generated blade-swipe sounds.

## Run from source

On Windows, use Python 3.12 with Tkinter. Run these commands from the repository folder.

```powershell
python -m pip install -r requirements.txt
python make_slice_sounds.py
python PomodoroTimer.py
```

## Build a standalone EXE

```powershell
python build.py
```

The build generates the sounds and writes `dist\PomodoroTimer.exe`.

## Backgrounds

Choose **Change background** in the sidebar to use a local image. The app saves the image and task data in `%LOCALAPPDATA%\PomodoroTimer`. Those files stay on your PC.

To bundle a looping wallpaper you own or have permission to use, put a `wallpaper.zip` in the repository folder before running or building. The ZIP should contain sequentially named JPEG frames at 24 frames per second. The original downloaded wallpaper is not included in this repository.

With FFmpeg available, these PowerShell commands prepare a ZIP from your own video. Use a new or empty `wallpaper-frames` folder.

```powershell
New-Item -ItemType Directory -Path wallpaper-frames
ffmpeg -i "your-wallpaper.mp4" -an -vf "fps=24,scale=1280:-2" -q:v 5 "wallpaper-frames/%05d.jpg"
Compress-Archive -Path "wallpaper-frames/*.jpg" -DestinationPath "wallpaper.zip"
```
