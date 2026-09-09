"""Shared, persisted options for the companion application lifecycle."""

from ok import ConfigOption


launch_options = ConfigOption(
    'Game and UU Auto Launch',
    {
        'Auto Launch Game and UU': True,
        'Close Game and UU on Exit': True,
        'UU Path': '',
        'Game Path': '',
        'UU Game Name': '战舰世界国际服',
        'Launch Timeout': 120,
    },
    description='Start UU acceleration before launching World of Warships.',
    config_description={
        'Auto Launch Game and UU': 'Launch both apps when starting a task; wait for UU acceleration first.',
        'Close Game and UU on Exit': 'On actual app exit, close World of Warships and UU, including already running instances.',
        'UU Path': 'Optional uu_launcher.exe path; leave empty to detect the UU installation.',
        'Game Path': 'Optional game executable or shortcut; leave empty to use the saved game path (Steam installs launch through Steam).',
        'UU Game Name': 'Exact game name shown in UU. Pin it to the UU home page or My Games first.',
        'Launch Timeout': 'Maximum seconds to wait for UU acceleration and then for the game process.',
    },
    config_type={
        'Launch Timeout': {'min': 15, 'max': 600},
        'UU Path': {'type': 'file_selector', 'selector_type': 'file', 'filter': 'Executables (*.exe)'},
        'Game Path': {'type': 'file_selector', 'selector_type': 'file',
                      'filter': 'Game executable or shortcut (*.exe *.lnk *.url)'},
    },
)
