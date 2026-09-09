import threading
import unittest
from unittest.mock import Mock, patch

from src.app_lifecycle import AppLifecycle


class TestAppLifecycle(unittest.TestCase):
    def setUp(self):
        self.settings = {'Auto Launch Game and UU': True, 'Close Game and UU on Exit': True}
        self.desktop = Mock()
        self.running = False
        self.desktop.game_running.side_effect = lambda: self.running
        self.desktop.accelerate.return_value = True
        self.desktop.launch.side_effect = lambda _: setattr(self, 'running', True)
        self.resolve = Mock(return_value='game.exe')
        self.notify = Mock()
        self.lifecycle = AppLifecycle(self.settings, threading.Event(), self.desktop, self.resolve, self.notify)

    def test_accelerates_before_launching_game(self):
        self.assertTrue(self.lifecycle.ensure_started())
        names = [c[0] for c in self.desktop.mock_calls]
        self.assertLess(names.index('accelerate'), names.index('launch'))
        self.desktop.launch.assert_called_once_with('game.exe')

    def test_acceleration_failure_never_launches_game(self):
        self.desktop.accelerate.side_effect = TimeoutError('UU failed')
        self.assertFalse(self.lifecycle.ensure_started())
        self.desktop.launch.assert_not_called()
        self.notify.assert_called_once_with('UU failed')

    def test_already_running_game_still_gets_acceleration(self):
        self.running = True
        self.assertTrue(self.lifecycle.ensure_started())
        self.desktop.accelerate.assert_called_once()
        self.desktop.launch.assert_not_called()
        self.resolve.assert_not_called()

    def test_repeated_start_does_not_launch_twice(self):
        self.assertTrue(self.lifecycle.ensure_started())
        self.assertTrue(self.lifecycle.ensure_started())
        self.desktop.launch.assert_called_once()

    def test_exit_during_acceleration_prevents_late_launch(self):
        entered, release = threading.Event(), threading.Event()

        def accelerate(*_):
            entered.set()
            release.wait(2)
            return True

        self.desktop.accelerate.side_effect = accelerate
        worker = threading.Thread(target=self.lifecycle.ensure_started)
        worker.start()
        self.assertTrue(entered.wait(2))
        closer = threading.Thread(target=self.lifecycle.shutdown)
        closer.start()
        self.assertTrue(self.lifecycle.cancel.wait(2))
        release.set()
        closer.join(2)
        worker.join(2)
        self.assertFalse(closer.is_alive())
        self.desktop.launch.assert_not_called()
        self.desktop.close.assert_called_once()

    def test_shutdown_is_idempotent_and_includes_existing_apps(self):
        self.running = True
        self.lifecycle.ensure_started()
        self.lifecycle.shutdown()
        self.lifecycle.shutdown()
        self.desktop.close.assert_called_once()
        self.assertFalse(self.lifecycle.ensure_started())

    def test_disabled_mode_neither_launches_nor_closes(self):
        self.settings['Auto Launch Game and UU'] = False
        self.assertTrue(self.lifecycle.ensure_started())
        self.lifecycle.shutdown()
        self.assertEqual([], self.desktop.mock_calls)

    def test_opening_and_closing_app_without_task_leaves_companions_alone(self):
        self.lifecycle.shutdown()
        self.assertEqual([], self.desktop.mock_calls)

    def test_can_leave_companions_running_on_exit(self):
        self.settings['Close Game and UU on Exit'] = False
        self.lifecycle.ensure_started()
        self.lifecycle.shutdown()
        self.desktop.close.assert_not_called()

    def test_exit_event_before_start_prevents_any_action(self):
        self.lifecycle.exit_event.set()
        self.assertFalse(self.lifecycle.ensure_started())
        self.assertEqual([], self.desktop.mock_calls)

    def test_game_timeout_is_reported_without_relaunching(self):
        self.desktop.launch.side_effect = None
        with patch('src.app_lifecycle.time.monotonic', side_effect=[0, 999]):
            self.assertFalse(self.lifecycle.ensure_started())
        self.desktop.launch.assert_called_once()
        self.assertIn('启动超时', self.notify.call_args.args[0])

    def test_missing_path_is_reported_before_starting_uu(self):
        self.resolve.side_effect = FileNotFoundError('missing game')
        self.assertFalse(self.lifecycle.ensure_started())
        self.desktop.accelerate.assert_not_called()
        self.notify.assert_called_once_with('missing game')


if __name__ == '__main__':
    unittest.main()
