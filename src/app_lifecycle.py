"""Cancellable, serialized startup and idempotent shutdown."""

import threading
import time

from ok import Logger


logger = Logger.get_logger(__name__)


class AppLifecycle:
    def __init__(self, settings, exit_event, desktop, resolve_game, notify):
        self.settings = settings
        self.exit_event = exit_event
        self.desktop = desktop
        self.resolve_game = resolve_game
        self.notify = notify
        self.cancel = threading.Event()
        self.lock = threading.RLock()
        self.closed = False
        self.managed = False
        self.ready = False

    def cancelled(self):
        return self.cancel.is_set() or self.exit_event.is_set()

    def ensure_started(self):
        with self.lock:
            if self.cancelled():
                return False
            if not self.settings.get('Auto Launch Game and UU'):
                return True
            if self.ready and self.desktop.game_running() and self.desktop.uu_running():
                return True
            self.managed = True
            self.ready = False
            try:
                timeout = max(15, min(600, int(self.settings.get('Launch Timeout', 120))))
                target = None if self.desktop.game_running() else self.resolve_game()
                if not self.desktop.accelerate(self.cancelled, timeout) or self.cancelled():
                    return False
                if not self.desktop.game_running():
                    self.desktop.launch(target or self.resolve_game())
                deadline = time.monotonic() + timeout
                while not self.cancelled():
                    if self.desktop.game_running():
                        self.ready = True
                        logger.info('战舰世界和 UU 已启动，加速状态已确认。')
                        return True
                    if time.monotonic() >= deadline:
                        raise TimeoutError('战舰世界启动超时，请检查 Steam/游戏启动器是否需要登录或更新。')
                    self.cancel.wait(0.4)
                return False
            except Exception as error:
                logger.error(f'自动启动失败：{error}', error)
                if not self.cancelled():
                    self.notify(str(error))
                return False

    def shutdown(self):
        # Cancel before acquiring the lock so startup cannot launch after cleanup.
        self.cancel.set()
        with self.lock:
            if self.closed:
                return
            self.closed = True
            if self.managed and self.settings.get('Close Game and UU on Exit'):
                try:
                    self.desktop.close()
                except Exception as error:
                    logger.error(f'联动退出失败：{error}', error)
                    self.notify(str(error))
