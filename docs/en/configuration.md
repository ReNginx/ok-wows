# App and Runtime Target Configuration

## App Settings

Review at least these settings in `src/config.py`:

- `gui_title`: application window title.
- `gui_icon`: GUI icon path.
- `supported_resolution`: supported aspect ratio and minimum resolution.
- `links`: project, support, and community links.
- `onetime_tasks`, `trigger_tasks`: task registration lists.

## Game and UU Auto Launch

The settings group is enabled by default. When a task starts manually or on schedule, UU opens first;
OCR locates the configured World of Warships card and acceleration button.
The game starts only after acceleration is confirmed. Existing game processes
are reused; Steam installations launch through Steam to survive game updates.
The selected task runs once the game is ready. Opening ok-wows alone does not launch UU or the game.

Leave **UU Path** empty for installation detection and **Game Path** empty to
reuse the saved game path, or select an executable/shortcut. **UU Game Name**
must exactly match the UU label (default: `战舰世界国际服`); add the game to UU's
home page or My Games first. **Launch Timeout** defaults to 120 seconds for each
stage: acceleration, then game startup.

Once Auto PVE Battle starts recognizing the game screen, it allows a separate,
fixed **5 minutes** to reach port through the logo, black screen, login and
reward pages. These stages share one deadline. Unknown screens are polled
without pressing Esc; failure to reach port within 300 seconds stops the task
with a timeout message.

**Close Game and UU on Exit** closes the game, then UU on actual app exit,
including instances already running before startup. Minimizing to the tray or
stopping a task does not close them. Disable this option to leave them running.
Unresponsive/tray processes are terminated after a grace period; failures are
logged with process IDs. Forced termination of this app cannot guarantee cleanup.

Run this app as administrator when UU is elevated, including source/debug runs.
Login, region selection and membership dialogs require manual handling. Failed
recognition or acceleration stops startup; use Start to retry after fixing it.
The latest screenshot and OCR results are in `logs/auto_launch/uu_latest.png`
and `uu_latest.json`. The basic automatic game launch option is disabled during
initialization so saved settings cannot launch the game merely by opening the app.

UU OCR regions and matching text are defined in `assets/uu/coco_annotations.json`,
using the same COCO image/category/bounding-box structure as game resources.
OCR reads the title strip first, then the matching card, scaling coordinates to
the UU window size. It clicks the center of the `click_region` icon above the
matching game title, rather than an OCR text box. Restart the app after editing regions or text rules. Home
regions are calibrated from a real screenshot; detail-page search regions remain
an unverified fallback. See `assets/uu/README.md` for the configuration fields.

## Scheduled Task Startup

Restart the app as administrator and open **Task Schedule** in the sidebar. Choose **Create Task**, select **Auto PVE Battle**, then set the start time and recurrence (once, daily, weekly, monthly or a custom interval). The task uses its saved battle mode, ship and battle count.

Windows Task Scheduler launches ok-wows at the selected time, then the task starts UU acceleration, launches the game and runs battles. Plans can be edited, disabled or deleted, with optional exit after completion.

Exit the current ok-wows instance before the scheduled time to avoid the framework's single-instance handling interfering with a running task. Keep the computer on, the user signed in and the desktop unlocked for foreground recognition and input. This does not power on a shut-down computer or catch up missed runs. Recreate plans after moving the app directory or Python environment.

## Runtime Targets

Configure at least one of `windows`, `adb`, or `browser`. A project may support multiple target types.

### Native Windows Game

Configure these `windows` values:

- `exe`: game executable filenames.
- `hwnd_class`: optional window class for more accurate matching.
- `interaction`: allowed input methods in priority order.
- `capture_method`: allowed capture methods in priority order.
- HDR and background-capture options.

### Android Emulator or Device

Add package names to `adb.packages`. MuMu can use native capture and input; other emulators and devices generally use ADB.

### Browser Game

Uncomment the `browser` example and set:

```python
'browser': {
    'url': 'https://example.com/game',
    'nick': 'Browser',
    'resolution': (1280, 720),
},
```

Browser targets also require `playwright`. Add it to each applicable profile in
`pyproject.toml`, then recompile the corresponding `requirements.txt` or
`requirements-web.txt` so local and GitHub build environments install it.

## Replace Icons

Replace `icons/icon.png` and `icons/icon.ico`. Keeping the filenames avoids extra configuration. If they change, update their paths in `src/config.py` and `pyappify.yml`.

## Update Repositories

Edit the app name, profile names, and `git_url` values in `pyappify.yml`:

- Use a separate lightweight update repository for production.
- The source repository can be used during early testing.
- With a separate update repository, update the sync targets and secrets in `.github/workflows/build.yml`.

After initialization, search for stale `ok-script-app`, `ok-oldking`, repository URLs, installer names, and community links inherited from the template.
