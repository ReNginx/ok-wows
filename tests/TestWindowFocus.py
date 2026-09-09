from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, call, patch

import pywintypes

from src import window_focus
from src.tasks.AutoPveBattleTask import AutoPveBattleTask
from src.tasks.ScreenRecognitionTestTask import ScreenRecognitionTestTask


class TestWindowFocus(unittest.TestCase):
    def setUp(self):
        self.gui = MagicMock()
        self.gui.error = pywintypes.error
        self.gui.IsWindow.return_value = True
        self.gui.IsIconic.return_value = False
        self.gui.IsWindowVisible.return_value = True
        self.foreground = 10
        self.gui.GetForegroundWindow.side_effect = lambda: self.foreground
        self.process = MagicMock()
        self.process.GetWindowThreadProcessId.side_effect = lambda hwnd: (hwnd, 999)
        self.api = MagicMock()
        self.api.GetCurrentThreadId.return_value = 1
        for name, mock in (("win32gui", self.gui), ("win32process", self.process), ("win32api", self.api)):
            patcher = patch.object(window_focus, name, mock)
            patcher.start()
            self.addCleanup(patcher.stop)

    def activate(self, hwnd):
        self.foreground = hwnd

    def test_restores_minimized_window_and_verifies_activation(self):
        minimized = {"value": True}
        self.gui.IsIconic.side_effect = lambda hwnd: minimized["value"]
        self.gui.ShowWindow.side_effect = lambda *args: minimized.update(value=False)
        self.gui.SetForegroundWindow.side_effect = self.activate
        self.assertTrue(window_focus.focus_window(20))
        self.gui.ShowWindow.assert_called_once_with(20, window_focus.win32con.SW_RESTORE)
        self.process.AttachThreadInput.assert_not_called()

    def test_native_activation_failure_uses_thread_input_fallback(self):
        attempts = []

        def activate_on_retry(hwnd):
            attempts.append(hwnd)
            if len(attempts) == 1:
                raise pywintypes.error(0, "SetForegroundWindow", "Denied")
            self.activate(hwnd)

        self.gui.SetForegroundWindow.side_effect = activate_on_retry
        self.assertTrue(window_focus.focus_window(20))
        self.assertEqual([call(1, 10, True), call(1, 20, True), call(1, 20, False), call(1, 10, False)],
                         self.process.AttachThreadInput.call_args_list)
        self.gui.SetFocus.assert_called_once_with(20)

    def test_restores_hidden_tray_window_before_activation(self):
        visible = {'value': False}
        self.gui.IsWindowVisible.side_effect = lambda hwnd: visible['value']
        self.gui.ShowWindow.side_effect = lambda *args: visible.update(value=True)
        self.gui.SetForegroundWindow.side_effect = self.activate
        self.assertTrue(window_focus.focus_window(20))
        self.gui.ShowWindow.assert_called_once_with(20, window_focus.win32con.SW_SHOW)

    def test_silent_activation_failure_is_not_reported_as_success(self):
        self.assertFalse(window_focus.focus_window(20))
        self.assertEqual(4, self.process.AttachThreadInput.call_count)

    def test_attachment_failure_detaches_any_thread_already_attached(self):
        self.process.AttachThreadInput.side_effect = [None, pywintypes.error(5, "AttachThreadInput", "Denied"), None]
        self.assertFalse(window_focus.focus_window(20))
        self.assertEqual([call(1, 10, True), call(1, 20, True), call(1, 10, False)],
                         self.process.AttachThreadInput.call_args_list)

    def test_invalid_handle_never_activates_a_window(self):
        self.gui.IsWindow.return_value = False
        self.assertFalse(window_focus.focus_window(20))
        self.gui.SetForegroundWindow.assert_not_called()

    def task(self, cls=AutoPveBattleTask):
        executor = MagicMock()
        executor.scene = None
        executor.device_manager.hwnd_window = SimpleNamespace(top_hwnd=20, hwnd=21)
        task = cls(executor, None)
        task.config = dict(task.default_config)
        return task

    def test_task_retries_if_startup_ui_steals_focus_back(self):
        task = self.task()
        with patch("src.tasks.MyBaseTask.focus_window", return_value=True) as focus, \
                patch("src.tasks.MyBaseTask.is_window_focused", side_effect=[False, True]), \
                patch.object(task, "sleep"):
            self.assertTrue(task.ensure_in_front())
        self.assertEqual([call(20), call(20)], focus.call_args_list)

    def test_focus_retries_are_bounded(self):
        task = self.task()
        with patch("src.tasks.MyBaseTask.focus_window", return_value=False) as focus, patch.object(task, "sleep"):
            self.assertFalse(task.ensure_in_front())
        self.assertEqual(3, focus.call_count)

    def test_missing_game_window_fails_without_input(self):
        task = self.task()
        task.executor.device_manager.hwnd_window = None
        with patch("src.tasks.MyBaseTask.focus_window") as focus:
            self.assertFalse(task.ensure_in_front())
        focus.assert_not_called()

    def test_battle_start_stops_before_recognition_when_focus_fails(self):
        task = self.task()
        with patch.object(task, "ensure_in_front", return_value=False), \
                patch.object(task, "_return_to_main") as recognize, \
                patch.object(task, "_prepare_and_join_first_battle") as prepare, \
                patch.object(task, "log_error") as error:
            task.run()
        recognize.assert_not_called()
        prepare.assert_not_called()
        error.assert_called_once()

    def test_recognition_test_also_requires_startup_focus(self):
        task = self.task(ScreenRecognitionTestTask)
        with patch.object(task, "ensure_in_front", return_value=False), \
                patch.object(task, "_inspect_once") as inspect, patch.object(task, "log_error"):
            task.run()
        inspect.assert_not_called()

    def test_recognition_focus_happens_before_first_inspection(self):
        task = self.task(ScreenRecognitionTestTask)
        events = []
        with patch.object(task, "ensure_in_front", side_effect=lambda: events.append("focus") or True), \
                patch.object(task, "_inspect_once", side_effect=lambda: events.append("inspect")), \
                patch.object(task, "sleep", side_effect=RuntimeError("stop")):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                task.run()
        self.assertEqual(["focus", "inspect"], events)


if __name__ == "__main__":
    unittest.main()
