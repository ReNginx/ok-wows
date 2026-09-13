"""验证框架统一错误退出出口和持久截图降级行为。"""

import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from ok import BaseTask, TriggerTask
from ok.task.TaskExecutor import TaskExecutor
from ok.task.exceptions import CaptureException, FinishedException, TaskDisabledException

from src.task_failure_capture import install_failure_capture, save_failure_screenshot


class TestTaskFailureCapture(unittest.TestCase):
    def setUp(self):
        install_failure_capture()
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.directory_patch = patch("src.task_failure_capture.FAILURE_DIRECTORY", self.directory)
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)
        self.executor = MagicMock()
        self.executor.scene = None
        self.executor.paused = False
        self.executor._last_frame_time = time.time()
        self.cached = np.full((12, 24, 3), 30, dtype=np.uint8)
        self.fresh = np.full((12, 24, 3), 180, dtype=np.uint8)
        self.executor._frame = self.cached
        self.executor.nullable_frame.return_value = self.cached
        self.executor.method.get_frame.return_value = self.fresh
        self.executor.is_executor_thread.return_value = True
        self.app = MagicMock()
        self.app.tr.side_effect = lambda text: text
        self.task = BaseTask(self.executor, self.app)
        self.task.name = '测试任务:/?*'
        self.task.config = {}

    def paths(self):
        return list(self.directory.glob("*/*.png"))

    def execute_once(self, action, *, trigger=False):
        self.executor.exit_event.is_set.side_effect = [False, True]
        self.executor.next_task.return_value = (self.task, False, trigger)
        with patch.object(self.task, "run", side_effect=action), \
                patch("ok.task.TaskExecutor.communicate") as events, \
                patch("ok.task.TaskExecutor.prevent_sleeping"):
            TaskExecutor.execute(self.executor)
        self.assertFalse(self.task.running)
        self.assertIsNone(self.executor.current_task)
        return events

    def assert_pixels(self, expected):
        self.assertEqual(1, len(self.paths()))
        image = cv2.imdecode(np.frombuffer(self.paths()[0].read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(expected, image)

    def test_uncaught_exception_saves_current_frame_and_keeps_original_error(self):
        error = RuntimeError("原始任务失败")
        events = self.execute_once(error)
        self.assert_pixels(self.fresh)
        self.assertEqual(str(error), self.task.info["Error"])
        self.executor.remove_onetime_task.assert_called_once_with(self.task)
        events.notification.emit.assert_called_once()
        self.assertEqual(str(error), events.notification.emit.call_args.args[0])
        self.assertNotIn(":", self.paths()[0].name)

    def test_logged_error_then_return_is_also_captured(self):
        self.execute_once(lambda: self.task.log_error("识别失败，任务停止"))
        self.assert_pixels(self.fresh)

    def test_error_before_run_falls_back_to_cached_frame(self):
        self.executor._frame = None
        self.executor.next_frame.side_effect = CaptureException("首次采集失败")
        self.executor.method.get_frame.side_effect = RuntimeError("捕获器失效")
        action = MagicMock()
        self.execute_once(action)
        action.assert_not_called()
        self.assert_pixels(self.cached)
        self.assertEqual("首次采集失败", self.task.info["Error"])

    def test_builtin_and_trigger_tasks_use_same_exception_hook(self):
        self.task = TriggerTask(self.executor, self.app)
        self.task.config = {}
        self.execute_once(RuntimeError("触发任务失败"), trigger=True)
        self.assert_pixels(self.fresh)

    def test_success_and_normal_cancellation_do_not_save_error_images(self):
        for outcome in (None, TaskDisabledException(), FinishedException()):
            with self.subTest(outcome=outcome):
                self.execute_once(outcome)
                self.assertEqual([], self.paths())

    def test_manual_stop_after_nonfatal_error_does_not_capture(self):
        self.executor.current_task = self.task
        self.executor.is_executor_thread.return_value = False
        self.task.running = True
        self.task.info["Error"] = "曾经记录过的错误"
        self.task.disable()
        self.assertEqual([], self.paths())
        self.executor.remove_onetime_task.assert_called_once_with(self.task)

    def test_missing_frames_does_not_mask_task_error(self):
        self.executor.nullable_frame.return_value = None
        self.executor.method.get_frame.return_value = None
        with patch("src.task_failure_capture.logger") as logger:
            self.execute_once(RuntimeError("原始错误"))
        self.assertEqual([], self.paths())
        self.assertEqual("原始错误", self.task.info["Error"])
        self.assertTrue(logger.warning.called)

    def test_encoding_or_write_failure_does_not_mask_task_error(self):
        for failure in (patch("src.task_failure_capture.cv2.imencode", return_value=(False, None)),
                        patch("src.task_failure_capture.Path.open", side_effect=OSError("磁盘不可写"))):
            with failure:
                self.execute_once(RuntimeError("原始错误"))
            self.assertEqual("原始错误", self.task.info["Error"])
            self.assertEqual([], self.paths())

    def test_same_run_deduplicates_existing_capture_but_new_run_gets_new_file(self):
        self.executor.current_task = self.task
        self.task.running = True
        self.task.start_time = 1
        self.task.info["Error"] = "退出错误"
        save_failure_screenshot(self.task, "按钮失败", frame=self.cached)
        self.task.disable()
        self.task.disable()
        self.assert_pixels(self.cached)
        self.task.start_time = 2
        self.task.disable()
        self.assertEqual(2, len(self.paths()))

    def test_installation_is_idempotent(self):
        original = BaseTask.disable
        install_failure_capture()
        install_failure_capture()
        self.assertIs(original, BaseTask.disable)


if __name__ == "__main__":
    unittest.main()
