"""通过真实框架点击和按键入口验证全局等待，不向游戏发送输入。"""

import gettext
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, call, patch

from ok import Box
from ok.util.GlobalConfig import GlobalConfig, register_basic_options
from ok.util.config import Config
from ok.task.TaskExecutor import TaskExecutor

from src.config import config
from src.interaction_config import BUTTON_WAIT, basic_options, interaction_options, validate_interaction_config
from src.tasks.AutoPveBattleTask import AutoPveBattleTask
from src.tasks.MyBaseTask import MyBaseTask
from src.tasks.MyOneTimeTask import MyOneTimeTask
from src.tasks.MyTriggerTask import MyTriggerTask


class TestInteractionWait(unittest.TestCase):
    def setUp(self):
        self.settings = dict(interaction_options.default_config)
        self.executor = MagicMock()
        self.executor.scene = None
        self.executor.global_config.get_config.return_value = self.settings
        self.executor.method.width = 5120
        self.executor.method.height = 2160
        self.task = MyBaseTask(self.executor, None)

    def test_click_routes_wait_once_after_actual_input(self):
        box = Box(100, 100, 100, 100, name="test")
        for action in (lambda: self.task.click(100, 200), lambda: self.task.click(box),
                       lambda: self.task.click([box]), lambda: self.task.click_box(box),
                       lambda: self.task.click(.5, .5), lambda: self.task.click_relative(.5, .5),
                       lambda: self.task.right_click(100, 200), lambda: self.task.middle_click(100, 200),
                       lambda: self.task.wait_click_feature("test")):
            events = MagicMock()
            with patch.object(self.task, "sleep", events.sleep), \
                    patch.object(self.task, "out_of_ratio", return_value=False), \
                    patch.object(self.task, "wait_until", return_value=box), \
                    patch.object(self.executor.interaction, "click", events.input):
                action()
            self.assertEqual(["input", "sleep"], [c[0] for c in events.mock_calls])
            events.sleep.assert_called_once_with(3.0)

    def test_all_project_task_types_share_live_settings(self):
        for task_type in (MyBaseTask, MyOneTimeTask, MyTriggerTask, AutoPveBattleTask):
            task = task_type(self.executor, None)
            with self.subTest(task=task_type.__name__), patch.object(task, "sleep") as sleep:
                self.settings[BUTTON_WAIT] = 2.5
                task.click(100, 200, after_sleep=1)
                self.settings[BUTTON_WAIT] = 4.0
                task.send_key("esc", after_sleep=1)
                self.assertEqual([call(2.5), call(4.0)], sleep.call_args_list)

    def test_existing_longer_waits_and_zero_setting(self):
        with patch.object(self.task, "sleep") as sleep:
            self.task.click(100, 200, after_sleep=5)
            self.task.send_key("m", after_sleep=8)
            self.settings[BUTTON_WAIT] = 0
            self.task.click(100, 200, after_sleep=1)
            self.task.send_key("w", after_sleep=.05)
            self.task.click(100, 200)
            self.assertEqual([call(5), call(8), call(1), call(.05)], sleep.call_args_list)

    def test_held_inputs_wait_on_release_and_back_uses_global_wait(self):
        with patch.object(self.task, "sleep") as sleep, patch.object(self.task, "out_of_ratio", return_value=False):
            self.task.send_key_down("w")
            self.task.mouse_down(100, 200)
            sleep.assert_not_called()
            self.task.send_key_up("w")
            self.task.mouse_up()
            self.task.back()
            self.assertEqual([call(3.0)] * 3, sleep.call_args_list)

    def test_skipped_inputs_do_not_add_wait(self):
        with patch.object(self.task, "check_interval", return_value=False), patch.object(self.task, "sleep") as sleep:
            self.assertFalse(self.task.click(100, 200, interval=10))
            self.assertFalse(self.task.send_key("w", interval=10))
            sleep.assert_not_called()
        self.executor.interaction.click.assert_not_called()
        self.executor.interaction.send_key.assert_not_called()

    def test_global_registration_validation_and_translations(self):
        self.assertIn(interaction_options, config["global_configs"])
        self.assertEqual(3.0, self.settings[BUTTON_WAIT])
        for value in (-1, True, "3", None, float("inf"), float("nan")):
            self.assertFalse(validate_interaction_config(BUTTON_WAIT, value)[0])
        for value in (0, 2.5, 3):
            self.assertTrue(validate_interaction_config(BUTTON_WAIT, value)[0])
        self.settings.clear()
        self.assertEqual(3.0, self.task._input_wait(0))
        for locale in ("zh_CN", "en_US"):
            with Path(f"i18n/{locale}/LC_MESSAGES/ok.mo").open("rb") as stream:
                catalog = gettext.GNUTranslations(stream)
            expected = "按钮等待时间（秒）" if locale == "zh_CN" else BUTTON_WAIT
            self.assertEqual(expected, catalog.gettext(BUTTON_WAIT))

    def test_trigger_default_survives_framework_registration_and_respects_saved_value(self):
        self.assertIn(basic_options, config["global_configs"])
        for saved, expected in ((None, 100), (250, 250)):
            with self.subTest(saved=saved), TemporaryDirectory() as folder, patch.object(Config, "config_folder", folder):
                if saved is not None:
                    Path(folder, "Basic Options.json").write_text(json.dumps({"Trigger Interval": saved}), encoding="utf-8")
                settings = register_basic_options(GlobalConfig([basic_options]))
                self.assertEqual(100, settings.get_default("Trigger Interval"))
                self.assertEqual(expected, settings["Trigger Interval"])
                executor = MagicMock()
                executor.basic_options = settings
                TaskExecutor.trigger_sleep(executor)
                executor.sleep.assert_called_once_with(expected / 1000)

    def test_battle_keeps_entry_delay_forward_burst_and_one_second_actions(self):
        task = AutoPveBattleTask(self.executor, None)
        task.config = dict(task.default_config)
        self.settings[BUTTON_WAIT] = 6.0  # 设置比默认值更长的菜单等待，确保战斗输入确实绕过它。
        elapsed = [0.0]
        with patch("src.tasks.AutoPveBattleTask.time.monotonic", side_effect=lambda: elapsed[0]), \
                patch.object(task, "_detect_scene", side_effect=["battle"] * 6 + ["result"]), \
                patch.object(task, "_handle_map", return_value=True), \
                patch.object(task, "out_of_ratio", return_value=False), \
                patch.object(task, "sleep", side_effect=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds)) as sleep:
            self.assertTrue(task._run_until_result())
            self.assertEqual([call(25)] + [call(.05)] * 10 + [call(2)] + [call(1)] * 4, sleep.call_args_list)
            self.assertEqual([call("w", .02)] * 10 + [call("m", .02)] +
                             [call(key, .02) for key in ("r", "t", "f")], self.executor.interaction.send_key.call_args_list)
            self.executor.interaction.click.assert_called_once()
            task.click(100, 200)  # 战斗操作结束后恢复菜单等待。
            self.assertEqual(call(6.0), sleep.call_args)

    def test_battle_exception_restores_global_wait(self):
        task = AutoPveBattleTask(self.executor, None)
        self.executor.interaction.send_key.side_effect = RuntimeError("input failed")
        with self.assertRaisesRegex(RuntimeError, "input failed"):
            task._send_battle_action(1)
        self.assertEqual(3.0, task._input_wait(0))

    def test_nested_battle_navigation_restores_global_wait(self):
        task = AutoPveBattleTask(self.executor, None)
        task.config = dict(task.default_config)
        self.settings[BUTTON_WAIT] = 6.0
        with patch.object(task, "wait_until", return_value=True), patch.object(task, "sleep") as sleep:
            self.assertTrue(task._close_map())
        sleep.assert_called_once_with(1)
        self.assertEqual(6.0, task._input_wait(0))
