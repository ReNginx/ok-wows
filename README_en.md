# ok-wows

English | [中文](README.md)

Windows client automation for *World of Warships*, built on [ok-script](https://github.com/ok-oldking/ok-script). It currently runs a **PVE battle loop**: prepare the selected ship, join the queue, pick a map waypoint, send combat inputs, and return to port after the configured number of battles.

The app only attaches to `WorldOfWarships64.exe`. Templates were marked at `5120x2160` (`64:27`). The lowest supported resolution is `1280x720`.

## Features

### Auto PVE Battle

A one-time task. It brings the game to the foreground, uses ESC to return to the port main screen, then runs the loop below.

1. Pick the first ship, open battle mode, and select PVE.
2. Open the addon page and remove all buffs if that option is available, then ESC back to the main screen.
3. Open the equipment page and remove all flags if that option is available, then ESC back to the main screen.
4. Click join battle. Do nothing while queued.
5. On the waiting screen, click start when the button appears.
6. Send `W` ten times, then press `M` to open the tactical map.
7. Pick a waypoint inside the main map:
   - If any gray or red capture area is found, click the one closest to the ship cursor.
   - Otherwise click the enemy base.
   - If both areas and an enemy base match, keep only the higher-scoring type.
   - If neither is found, click the point opposite the ship cursor across the map center.
8. Wait for the route marker to settle, then close the map with ESC. Fall back to `M` if ESC does not close it.
9. In battle, rotate every second: left click at screen center, `R`, then `T`.
10. On a normal result screen, click continue when more battles remain; click back to port after the last battle.
11. After being sunk, stop firing and press ESC. Click continue if more battles remain; otherwise confirm leaving.

Task settings:

- **Battle Count**: how many battles to finish. Default `1`, minimum `1`.
- **Template Threshold**: matching confidence. Default `0.8`. Map elements are capped at `0.75` to reduce misses on a moving map.

The task stops with a log message if it cannot return to the main screen, preparation fails, a result screen times out, or a required button is missing.

### Screen Recognition Test

Read-only diagnostics. Every 3 seconds it captures one frame, scores every official template, and reports the current scene (main, queue, battle, map, result, leave-battle, and so on). It never sends input. Use it to check annotations and thresholds.

## Usage

Requires Windows, Python 3.12, and a running World of Warships client. If the game is running as administrator, start this app with the same privilege or capture and input may fail.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --index-url https://pypi.org/simple/ --upgrade pip
python -m pip install --index-url https://pypi.org/simple/ --no-deps --upgrade -r requirements.txt
python main_debug.py
```

Select the game window, open **Auto PVE Battle**, set the battle count, and start. To verify recognition first, run **Screen Recognition Test**.

## Credits

- [ok-script](https://github.com/ok-oldking/ok-script)
- [OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
