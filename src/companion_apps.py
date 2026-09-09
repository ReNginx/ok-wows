"""Windows process and screenshot adapter for the game/UU lifecycle."""

import ctypes
import json
import os
from pathlib import Path
import time

import cv2
import numpy as np
from PIL import ImageGrab
import psutil
import win32api
import win32con
import win32gui
import win32process
import win32security

from ok import Logger
from src.uu_annotations import default_annotations
from src.uu_recognition import decide, navigation_target
from src.window_focus import focus_window, is_window_focused
from src.uu_input import click_uu


logger = Logger.get_logger(__name__)
GAME_NAMES = {'worldofwarships64.exe'}
# Explicit names: do not stop Steam, Wargaming Center, unrelated games or services.
UU_NAMES = {'uu.exe', 'uu_launcher.exe', 'uu_ball.exe', 'uu_cloudsyn.exe'}


def processes(names):
    return [p for p in psutil.process_iter(['pid', 'name'])
            if (p.info['name'] or '').casefold() in names]


def resolve_uu_path(configured=''):
    if configured.strip():
        path = Path(os.path.expandvars(configured.strip().strip('"')))
        if not path.is_file():
            raise FileNotFoundError(f'UU 路径不存在：{path}')
        return path
    candidates = [Path(os.environ.get(key, root)) / 'Netease/UU/uu_launcher.exe'
                  for key, root in [('ProgramFiles(x86)', 'C:/Program Files (x86)'),
                                    ('ProgramFiles', 'C:/Program Files')]]
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                                    0, winreg.KEY_READ | view) as root:
                    for i in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            with winreg.OpenKey(root, winreg.EnumKey(root, i)) as key:
                                name = winreg.QueryValueEx(key, 'DisplayName')[0]
                                if 'UU' in name.upper() and '加速' in name:
                                    location = winreg.QueryValueEx(key, 'InstallLocation')[0]
                                    candidates.append(Path(location) / 'uu_launcher.exe')
                        except OSError:
                            continue
            except OSError:
                continue
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError('未找到 UU 加速器，请在“游戏与 UU 自动启动”中填写 UU 路径。')


def resolve_game_target(configured, config_folder):
    configured = configured.strip().strip('"')
    if configured:
        path = Path(os.path.expandvars(configured))
        if not path.is_file() or path.suffix.casefold() not in {'.exe', '.lnk', '.url'}:
            raise FileNotFoundError('游戏路径必须是已有的 .exe、.lnk 或 .url 文件。')
        return str(path)
    devices_file = Path(config_folder) / 'devices.json'
    saved = json.loads(devices_file.read_text(encoding='utf-8')) if devices_file.exists() else {}
    path = Path(saved.get('pc_full_path') or '')
    # Steam handles authentication and selects the current version after updates.
    for parent in path.parents:
        manifest = parent / 'appmanifest_552990.acf'
        if parent.name.casefold() == 'steamapps' and manifest.is_file():
            return 'steam://rungameid/552990'
    if path.is_file():
        return str(path)
    raise FileNotFoundError('未找到游戏路径，请先手动启动游戏让应用记录路径，或填写“游戏路径”。')


def windows_for(pids):
    windows = []

    def collect(hwnd, _):
        if win32process.GetWindowThreadProcessId(hwnd)[1] in pids:
            windows.append(hwnd)

    win32gui.EnumWindows(collect, None)
    return windows


class WindowsCompanions:
    def __init__(self, settings, config_folder, ocr):
        self.settings = settings
        self.config_folder = config_folder
        self.ocr = ocr
        self.evidence = Path('logs') / 'auto_launch'

    def game_running(self):
        return bool(processes(GAME_NAMES))

    def uu_running(self):
        return bool(processes({'uu.exe'}))

    def launch(self, target):
        if '://' in str(target):
            os.startfile(str(target))
        else:
            path = Path(target).resolve()
            os.startfile(str(path), cwd=str(path.parent))

    def find_uu(self):
        pids = {p.pid for p in processes({'uu.exe'})}
        matches = [h for h in windows_for(pids)
                   if win32gui.GetWindowText(h) in {'UU加速器', '网易UU加速器'}]
        return matches[0] if len(matches) == 1 else None

    def ensure_foreground(self, hwnd):
        self.check_input_access(hwnd)
        for _ in range(3):
            focus_window(hwnd)
            time.sleep(0.2)  # Startup windows can take focus back after activation.
            if is_window_focused(hwnd):
                return
        foreground = win32gui.GetForegroundWindow()
        state = {'uu_handle': hwnd, 'uu_visible': bool(win32gui.IsWindowVisible(hwnd)),
                 'uu_minimized': bool(win32gui.IsIconic(hwnd)),
                 'foreground_handle': foreground,
                 'foreground_title': win32gui.GetWindowText(foreground) if foreground else '',
                 'app_is_admin': bool(ctypes.windll.shell32.IsUserAnAdmin())}
        self.evidence.mkdir(parents=True, exist_ok=True)
        diagnostic = self.evidence / 'uu_focus.json'
        diagnostic.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        raise RuntimeError(f'重试 3 次仍无法将 UU 调到前台，已停止截图和点击。'
                           f'请检查 UU 弹窗并手动恢复窗口后重试；诊断：{diagnostic}')

    def snapshot(self, hwnd):
        self.ensure_foreground(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        frame = cv2.cvtColor(np.asarray(ImageGrab.grab(bbox=rect, all_screens=True)), cv2.COLOR_RGB2BGR)
        if not is_window_focused(hwnd) or rect != win32gui.GetWindowRect(hwnd):
            raise RuntimeError('UU 窗口在截图时发生变化，请重试。')
        self.evidence.mkdir(parents=True, exist_ok=True)
        cv2.imencode('.png', frame)[1].tofile(str(self.evidence / 'uu_latest.png'))
        boxes = default_annotations().recognize(frame, self.ocr(), self.settings['UU Game Name'])
        (self.evidence / 'uu_latest.json').write_text(
            json.dumps([vars(b) for b in boxes], ensure_ascii=False, indent=2), encoding='utf-8')
        return frame, boxes, rect

    @staticmethod
    def check_input_access(hwnd):
        if not ctypes.windll.shell32.IsUserAnAdmin():
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            handle = win32api.OpenProcess(0x1000, False, pid)
            try:
                token = win32security.OpenProcessToken(handle, win32security.TOKEN_QUERY)
                try:
                    if win32security.GetTokenInformation(token, win32security.TokenElevation):
                        raise RuntimeError('UU 正以管理员权限运行，请以管理员身份启动本应用后重试。')
                finally:
                    token.Close()
            finally:
                handle.Close()

    def pointer(self, hwnd, rect, point, click=False):
        self.check_input_access(hwnd)
        # Never send coordinates after a focus, geometry, or modal-window change.
        if not is_window_focused(hwnd) or win32gui.GetWindowRect(hwnd) != rect:
            raise RuntimeError('UU 窗口位置或焦点已变化，已取消本次点击。')
        x, y = round(rect[0] + point[0]), round(rect[1] + point[1])
        hit = win32gui.GetAncestor(win32gui.WindowFromPoint((x, y)), win32con.GA_ROOT)
        if hit != hwnd:
            raise RuntimeError('UU 按钮被其他窗口遮挡，已取消本次点击。')
        if click:
            click_uu(hwnd, rect, point)

    def accelerate(self, cancelled, timeout):
        if not processes({'uu.exe'}):
            self.launch(resolve_uu_path(self.settings.get('UU Path', '')))
        elif not self.find_uu():
            self.launch(resolve_uu_path(self.settings.get('UU Path', '')))
        deadline = time.monotonic() + timeout
        clicked = False
        navigated = False
        last_click = 0
        while not cancelled():
            if time.monotonic() >= deadline:
                raise TimeoutError('UU 加速超时，未启动游戏。请查看 logs/auto_launch 的截图和文字。')
            hwnd = self.find_uu()
            if hwnd:
                frame, boxes, rect = self.snapshot(hwnd)
                decision = decide(boxes, self.settings['UU Game Name'], frame.shape[1], frame.shape[0])
                if cancelled():
                    return False
                if decision.action == 'ready':
                    logger.info('已确认战舰世界 UU 加速成功。')
                    return True
                if decision.action == 'blocked':
                    raise RuntimeError('UU 需要登录、会员处理或加速失败，请手动处理后重新启动。')
                if decision.action == 'unsupported':
                    raise RuntimeError('UU 窗口比例与 JSON 标注不符，请更新 assets/uu/coco_annotations.json。')
                if decision.action == 'click' and not clicked:
                    self.pointer(hwnd, rect, decision.point, click=True)
                    clicked = True  # A submitted acceleration is never blindly toggled again.
                    last_click = time.monotonic()
                elif decision.action == 'missing' and not navigated and not clicked:
                    point = navigation_target(boxes, frame.shape[1], frame.shape[0])
                    if point is not None:
                        self.pointer(hwnd, rect, point, click=True)
                        navigated = True
                # A region/login dialog is left untouched; no guessed selection.
                if clicked and time.monotonic() - last_click > 30 and decision.action == 'click':
                    raise RuntimeError('UU 没有响应加速点击。请以管理员身份运行本应用后重试。')
            time.sleep(0.4)
        return False

    def close(self):
        self._close_groups((GAME_NAMES, UU_NAMES))

    def _close_groups(self, groups):
        # Request normal window closure, then handle tray minimization/non-responsive clients.
        # Game first, so its connection is not dropped while it is still closing.
        failures = []
        for names in groups:
            targets = processes(names)
            for hwnd in windows_for({p.pid for p in targets}):
                try:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                except win32gui.error:
                    pass
            _, remaining = psutil.wait_procs(targets, timeout=3)
            # Also include helpers started during shutdown by the UU launcher.
            remaining = list({p.pid: p for p in remaining + processes(names)}.values())
            for proc in remaining:
                try:
                    proc.terminate()
                except psutil.NoSuchProcess:
                    pass
                except psutil.AccessDenied:
                    failures.append(proc.pid)
            _, alive = psutil.wait_procs(remaining, timeout=3)
            failures.extend(p.pid for p in alive)
        if failures:
            raise RuntimeError(f'部分游戏/UU 进程未能退出（PID {sorted(set(failures))}），请检查管理员权限。')
