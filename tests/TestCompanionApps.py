import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import psutil

from src.companion_apps import GAME_NAMES, UU_NAMES, WindowsCompanions, resolve_game_target
from src.uu_recognition import TextBox


class TestCompanionApps(unittest.TestCase):
    def test_foreground_retries_when_startup_takes_focus_back(self):
        desktop = WindowsCompanions({}, 'configs', Mock())
        with patch.object(desktop, 'check_input_access'), \
                patch('src.companion_apps.focus_window') as focus, \
                patch('src.companion_apps.is_window_focused', side_effect=[False, True]), \
                patch('src.companion_apps.time.sleep'):
            desktop.ensure_foreground(22)
        self.assertEqual(2, focus.call_count)

    def test_failed_foreground_saves_diagnostic_without_screenshot_or_click(self):
        desktop = WindowsCompanions({}, 'configs', Mock())
        with tempfile.TemporaryDirectory() as directory:
            desktop.evidence = Path(directory)
            with patch.object(desktop, 'check_input_access'), \
                    patch('src.companion_apps.focus_window') as focus, \
                    patch('src.companion_apps.is_window_focused', return_value=False), \
                    patch('src.companion_apps.time.sleep'), \
                    patch('src.companion_apps.win32gui.GetForegroundWindow', return_value=44), \
                    patch('src.companion_apps.win32gui.GetWindowText', return_value='UU dialog'), \
                    patch('src.companion_apps.win32gui.IsWindowVisible', return_value=True), \
                    patch('src.companion_apps.win32gui.IsIconic', return_value=False), \
                    patch('src.companion_apps.ImageGrab.grab') as grab, \
                    patch('src.companion_apps.click_uu') as click:
                with self.assertRaisesRegex(RuntimeError, '重试 3 次'):
                    desktop.snapshot(22)
            self.assertEqual(3, focus.call_count)
            self.assertEqual(44, json.loads((desktop.evidence / 'uu_focus.json').read_text())['foreground_handle'])
            grab.assert_not_called()
            click.assert_not_called()

    def test_permission_mismatch_is_reported_before_attempting_activation(self):
        desktop = WindowsCompanions({}, 'configs', Mock())
        with patch.object(desktop, 'check_input_access', side_effect=RuntimeError('管理员身份')), \
                patch('src.companion_apps.focus_window') as focus:
            with self.assertRaisesRegex(RuntimeError, '管理员身份'):
                desktop.snapshot(22)
        focus.assert_not_called()

    def test_steam_manifest_resolves_url_even_after_game_version_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apps = root / 'steamapps'
            apps.mkdir()
            (apps / 'appmanifest_552990.acf').touch()
            path = apps / 'common/World of Warships/bin/old/bin64/WorldOfWarships64.exe'
            (root / 'devices.json').write_text(json.dumps({'pc_full_path': str(path)}), encoding='utf-8')
            self.assertEqual('steam://rungameid/552990', resolve_game_target('', root))

    def test_explicit_game_path_takes_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'game.exe'
            executable.touch()
            self.assertEqual(str(executable), resolve_game_target(str(executable), directory))

    def test_missing_game_path_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, '游戏路径'):
                resolve_game_target('', directory)

    def test_exit_targets_only_game_and_uu_and_handles_tray_clients(self):
        desktop = WindowsCompanions({}, 'configs', Mock())
        game, uu = Mock(pid=100), Mock(pid=200)
        with patch('src.companion_apps.processes', side_effect=lambda n: [game] if n == GAME_NAMES else [uu]) as scan, \
                patch('src.companion_apps.windows_for', return_value=[22]), \
                patch('src.companion_apps.win32gui.PostMessage') as post, \
                patch('src.companion_apps.psutil.wait_procs', side_effect=[([], [game]), ([game], []), ([], [uu]), ([uu], [])]):
            desktop.close()
        self.assertEqual({frozenset(GAME_NAMES), frozenset(UU_NAMES)},
                         {frozenset(c.args[0]) for c in scan.call_args_list})
        self.assertEqual(2, post.call_count)
        game.terminate.assert_called_once()
        uu.terminate.assert_called_once()

    def test_exit_permission_failure_is_reported(self):
        desktop = WindowsCompanions({}, 'configs', Mock())
        proc = Mock(pid=100)
        proc.terminate.side_effect = psutil.AccessDenied(100)
        with patch('src.companion_apps.processes', return_value=[proc]), \
                patch('src.companion_apps.windows_for', return_value=[]), \
                patch('src.companion_apps.psutil.wait_procs', return_value=([], [proc])):
            with self.assertRaisesRegex(RuntimeError, '管理员权限'):
                desktop.close()

    def test_acceleration_clicks_once_then_waits_for_confirmation(self):
        import numpy as np
        settings = {'UU Game Name': '战舰世界国际服'}
        desktop = WindowsCompanions(settings, 'configs', Mock())
        game = TextBox('战舰世界国际服', 551, 432, 682, 453)
        button = TextBox('立即加速', 580, 310, 654, 336)
        stop = TextBox('停止加速', 580, 310, 654, 336)
        frame, rect = np.zeros((688, 1000, 3), dtype=np.uint8), (0, 0, 1000, 688)
        snapshots = [(frame, [game, button], rect), (frame, [game, button], rect), (frame, [game, stop], rect)]
        with patch('src.companion_apps.processes', return_value=[Mock()]), \
                patch.object(desktop, 'find_uu', return_value=10), \
                patch.object(desktop, 'snapshot', side_effect=snapshots), \
                patch.object(desktop, 'pointer') as pointer, \
                patch('src.companion_apps.win32gui.IsWindowVisible', return_value=True), \
                patch('src.companion_apps.time.sleep'):
            self.assertTrue(desktop.accelerate(lambda: False, 120))
        pointer.assert_called_once_with(10, rect, (617, 254), click=True)

    def test_focus_change_prevents_click(self):
        desktop = WindowsCompanions({}, 'configs', Mock())
        with patch('src.companion_apps.ctypes.windll.shell32.IsUserAnAdmin', return_value=True), \
                patch('src.companion_apps.is_window_focused', return_value=False), \
                patch('src.companion_apps.win32api.mouse_event') as click:
            with self.assertRaisesRegex(RuntimeError, '焦点'):
                desktop.pointer(1, (0, 0, 100, 100), (40, 40), click=True)
        click.assert_not_called()

    def test_elevated_uu_reports_error_before_sending_input(self):
        desktop = WindowsCompanions({}, 'configs', Mock())
        handle, token = Mock(), Mock()
        with patch('src.companion_apps.ctypes.windll.shell32.IsUserAnAdmin', return_value=False), \
                patch('src.companion_apps.win32process.GetWindowThreadProcessId', return_value=(1, 2)), \
                patch('src.companion_apps.win32api.OpenProcess', return_value=handle), \
                patch('src.companion_apps.win32security.OpenProcessToken', return_value=token), \
                patch('src.companion_apps.win32security.GetTokenInformation', return_value=1), \
                patch('src.companion_apps.win32api.mouse_event') as click:
            with self.assertRaisesRegex(RuntimeError, '管理员身份'):
                desktop.pointer(1, (0, 0, 100, 100), (40, 40), click=True)
        click.assert_not_called()
        handle.Close.assert_called_once()
        token.Close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
