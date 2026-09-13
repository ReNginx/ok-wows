# ok-wows

English | [中文](README.md)

Windows client automation for *World of Warships*, built on [ok-script](https://github.com/ok-oldking/ok-script). It currently runs a **PVE battle loop**: prepare the selected ship, join the queue, pick a map waypoint, send combat inputs, and return to port after the configured number of battles.

The app only attaches to `WorldOfWarships64.exe`. Templates are selected by window aspect ratio: `21:9`, `16:10`, or `16:9`. The lowest supported resolution is `1280x720`.

## Features

### Auto PVE Battle

A one-time task. It brings the game to the foreground, uses ESC to return to the port main screen, then runs the loop below.

1. Pick the first ship, open battle mode, and select PVE.
2. Open the addon page and remove all buffs if that option is available, then ESC back to the main screen.
3. Open the equipment page and remove all flags if that option is available, then ESC back to the main screen.
4. Click join battle. Do nothing while queued.
5. On the waiting screen, click start when the button appears.
6. After confirming the battle view, wait 25 seconds for the opening text to disappear, then send `W` ten times and press `M` to open the tactical map for navigation. Repeat this delay for each battle. Ship-Icon recognition searches only the left team list and scores the template's yellow silhouette, excluding its background and filtering gray silhouettes in the current frame.
7. Pick a waypoint inside the main map:
   - When the ship cursor is found, first click its opposite point across the map center and wait 3 seconds to set a fallback waypoint. Then try the capture area or base, so a rejected land target can leave the previous route available.
   - If any gray or red capture area is found, click the one closest to the ship cursor.
   - Otherwise click the enemy base.
   - If both areas and an enemy base match, keep only the higher-scoring type.
   - If neither is found, keep the opposite waypoint without clicking it again.
8. Wait for the route marker to settle, then close the map with ESC. Fall back to `M` if ESC does not close it.
9. In battle, rotate on a one-second cycle: left click at screen center, `R`, `T`, then `F`. After each action, move the mouse to a random central position away from the left team list. Do not move it on map, loading or result screens. Recognition taking longer than a second delays that cycle.
10. On a normal result screen, click continue when more battles remain; click back to port after the last battle.
11. After being sunk, stop firing and press ESC. Click continue if more battles remain; otherwise confirm leaving.
12. After all battles finish, confirm the port main screen and click `Container-Menu`. Repeat `Pick-Container` and `Confirm-Container` until clicking Pick produces no confirmation within 10 seconds. If closing the game after completion is enabled, close it after collection finishes.

Container templates are currently available for `21:9`; other aspect ratios need annotations for these three buttons. Missing templates or a stuck confirmation page stop the task with an error log.

Task settings:

- **Battle Count**: how many battles to finish. Default `1`, minimum `1`.
- **Template Threshold**: matching confidence. Default `0.8`. Map elements are capped at `0.75` to reduce misses on a moving map.

The task stops with a log message if it cannot return to the main screen, preparation fails, a result screen times out, or a required button is missing.

Enable **Capture Battle Dataset** in the task settings to collect screenshots; it is off by default. Capture starts 60 seconds after battle entry is detected and repeats every minute. Each sample contains a full-resolution battle PNG and tactical-map PNG; the task opens and closes the map without changing the waypoint. Files are grouped by battle and timestamp under `dataset/` in the project root. Failed map captures are skipped, and existing images are retained.

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
