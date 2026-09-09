from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

from src import globals as app_globals
from src.app_entry import run_app


class TestLaunchIntegration(unittest.TestCase):
    def setUp(self):
        self.settings = {'Auto Launch Game and UU': True}
        self.controller = Mock()
        self.original = self.controller.start_device
        self.og = SimpleNamespace(
            global_config=Mock(), config={}, app=SimpleNamespace(start_controller=self.controller))
        self.basic_settings = {'Auto Start Game When App Starts': True}
        self.og.global_config.get_config.side_effect = lambda option: (
            self.basic_settings if option is app_globals.basic_options else self.settings)
        self.events = Mock()
        self.og.executor = Mock(onetime_tasks=[])
        self.og.ok = SimpleNamespace(args={})
        with patch.object(app_globals, 'og', self.og), \
                patch.object(app_globals, 'communicate', self.events), \
                patch.object(app_globals, 'AppLifecycle') as cls, \
                patch.object(app_globals, 'WindowsCompanions'), \
                patch.object(app_globals.atexit, 'register'), \
                patch.object(app_globals.threading, 'Thread'):
            self.app = app_globals.Globals(threading.Event())
            self.lifecycle = cls.return_value
        self.lifecycle.ensure_started.return_value = True

    def test_managed_start_waits_for_capture_without_relaunching(self):
        with patch.object(app_globals, 'communicate', self.events):
            self.assertTrue(self.controller.start_device(initial_refresh_done=True))
        self.original.assert_not_called()
        self.lifecycle.ensure_started.assert_called_once()
        self.controller._wait_until_device_ready.assert_called_once_with(refresh_first=True)
        self.controller._wait_until_started_window_stable.assert_called_once()

    def test_disabled_mode_preserves_framework_start(self):
        self.settings['Auto Launch Game and UU'] = False
        self.controller.start_device(initial_refresh_done=True)
        self.original.assert_called_once_with(initial_refresh_done=True)
        self.lifecycle.ensure_started.assert_not_called()

    def test_failure_does_not_start_or_capture_game(self):
        self.lifecycle.ensure_started.return_value = False
        with patch.object(app_globals, 'communicate', self.events):
            self.assertFalse(self.controller.start_device())
        self.original.assert_not_called()
        self.controller._wait_until_device_ready.assert_not_called()

    def test_opening_app_does_not_launch_companions(self):
        self.events.start_success.connect.assert_not_called()
        self.lifecycle.ensure_started.assert_not_called()
        self.original.assert_not_called()

    def test_saved_framework_app_open_launcher_is_disabled(self):
        self.assertFalse(self.basic_settings['Auto Start Game When App Starts'])

    def test_scheduled_task_index_uses_managed_start_before_enabling_task(self):
        from ok.core.start_controller import StartController
        task = SimpleNamespace(enabled=False, paused=False, exit_after_task=False)
        self.og.executor.onetime_tasks = [task]
        self.og.executor.current_task = None
        self.og.executor.get_all_tasks.return_value = []
        self.og.device_manager = Mock()
        order = []
        self.lifecycle.ensure_started.side_effect = lambda: order.append('companions') or True
        self.controller._mark_task_enabled.side_effect = lambda _: order.append('task')
        with patch('ok.core.start_controller.og', self.og), \
                patch('ok.core.start_controller.communicate', self.events), \
                patch.object(app_globals, 'communicate', self.events):
            self.assertTrue(StartController._do_start(self.controller, task=0, exit_after=True))
        self.assertEqual(['companions', 'task'], order)
        self.assertTrue(task.exit_after_task)
        self.og.executor.start.assert_called_once()

    def test_entrypoint_cleans_up_even_if_ui_raises(self):
        app, lifecycle = Mock(), Mock()
        app.start.side_effect = RuntimeError('UI closed')
        with patch('ok.OK', return_value=app), \
                patch('ok.og', SimpleNamespace(my_app=SimpleNamespace(lifecycle=lifecycle))):
            with self.assertRaisesRegex(RuntimeError, 'UI closed'):
                run_app({})
        app.exit_event.set.assert_called_once()
        lifecycle.shutdown.assert_called_once()


if __name__ == '__main__':
    unittest.main()
