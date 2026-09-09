import atexit
import threading

from ok import Logger, og
from ok.core.events import communicate
from ok.util.GlobalConfig import basic_options

from src.app_lifecycle import AppLifecycle
from src.companion_apps import WindowsCompanions, resolve_game_target
from src.launch_config import launch_options

logger = Logger.get_logger(__name__)


class Globals:

    def __init__(self, exit_event):
        # Disable the framework's app-open launcher, including previously saved settings.
        og.global_config.get_config(basic_options)['Auto Start Game When App Starts'] = False
        settings = og.global_config.get_config(launch_options)
        folder = og.config.get('config_folder', 'configs')
        self.lifecycle = AppLifecycle(
            settings, exit_event,
            WindowsCompanions(settings, folder, lambda: og.executor.ocr_lib()),
            lambda: resolve_game_target(settings.get('Game Path', ''), folder),
            lambda message: communicate.notification.emit(message, '游戏与 UU 自动启动', True, True),
        )
        # This hook also covers the built-in Start button and command-line tasks.
        controller = og.app.start_controller
        original_start_device = controller.start_device

        def start_device(*args, **kwargs):
            if not settings.get('Auto Launch Game and UU'):
                return original_start_device(*args, **kwargs)
            if not self.lifecycle.ensure_started():
                communicate.starting_emulator.emit(True, '游戏与 UU 自动启动失败，请查看日志。', 0)
                return False
            # The game is already launched. Refresh discovery and wait for capture;
            # the original launcher could otherwise use a stale disconnected device
            # and start the old executable a second time during Steam startup.
            if not controller._wait_until_device_ready(refresh_first=True):
                return False
            ready = controller._wait_until_started_window_stable()
            if ready:
                communicate.starting_emulator.emit(True, None, 0)
            return ready

        controller.start_device = start_device
        atexit.register(self.lifecycle.shutdown)

        def watch_exit():
            exit_event.wait()
            self.lifecycle.shutdown()

        threading.Thread(target=watch_exit, name='GameUUExit', daemon=True).start()

