import unittest  # 导入标准库单元测试框架。
from unittest.mock import MagicMock, call, patch  # 导入执行器替身、调用对象和临时补丁工具。

from ok import TriggerTask  # 导入后台触发任务类型以确认本任务采用与诊断任务相同的一次性生命周期。
from src.config import config  # 导入应用配置以验证测试任务已经注册。
from src.tasks.ScreenRecognitionTestTask import ScreenRecognitionTestTask  # 导入只读屏幕识别测试任务。

SCREEN_RECOGNITION_TASK = ["src.tasks.ScreenRecognitionTestTask", "ScreenRecognitionTestTask"]  # 保存识别测试的标准注册项。
REGISTERED_ONETIME_TASKS = list(config["onetime_tasks"])  # 保存正式一次性任务注册表以验证任务采用诊断任务式注册。


class TestScreenRecognitionTestTask(unittest.TestCase):  # 定义屏幕识别测试任务的无输入行为测试集合。

    def setUp(self):  # 为每个测试创建不连接真实游戏窗口的任务实例。
        executor = MagicMock()  # 构造轻量任务执行器替身。
        executor.scene = None  # 提供任务基类初始化需要的场景属性。
        self.task = ScreenRecognitionTestTask(executor, None)  # 创建待测的只读识别任务。
        self.task.config = dict(self.task.default_config)  # 使用普通字典模拟任务配置加载结果。

    def test_task_uses_diagnosis_style_onetime_lifecycle_without_battle_count(self):  # 验证测试任务采用诊断任务式持续循环且没有自动战斗配置。
        self.assertNotIsInstance(self.task, TriggerTask)  # 确认任务不是由后台触发器间歇调度，而是在一次启动中持续运行。
        self.assertIn(SCREEN_RECOGNITION_TASK, REGISTERED_ONETIME_TASKS)  # 确认任务与 DiagnosisTask 一样注册在一次性任务列表。
        self.assertNotIn("Battle Count", self.task.default_config)  # 确认测试任务不会显示无关的战斗场数配置。
        self.assertEqual(0.8, self.task.default_config["Template Threshold"])  # 确认测试任务沿用正式模板阈值。

    def test_feature_names_come_from_formal_template_json(self):  # 验证任务会动态覆盖正式模板中的全部元素。
        feature_names = self.task._load_feature_names()  # 从当前正式模板配置读取分类名称。
        self.assertIn("Map-Tutorial", feature_names)  # 确认大地图教程元素包含在检查范围中。
        self.assertIn("Libertad-Nameplate", feature_names)  # 确认新增舰船铭牌元素包含在检查范围中。
        self.assertEqual(len(feature_names), len(set(feature_names)))  # 确认元素列表没有重复分类名称。

    def test_inspection_checks_one_frame_and_never_sends_input(self):  # 验证单轮检查只截图识别且不会操作游戏。
        scored_box = MagicMock()  # 构造模板引擎返回的最佳匹配框替身。
        scored_box.confidence = 0.95  # 设置一个高于正式阈值的测试置信度。
        with patch.object(self.task, "next_frame", return_value=object()) as next_frame, patch.object(self.task, "_load_feature_names", return_value=["Feature-A", "Feature-B"]), patch.object(self.task, "find_one", return_value=scored_box) as find_one, patch.object(self.task, "_detect_scene", return_value="map") as detect_scene, patch.object(self.task, "clear_box"), patch.object(self.task, "draw_boxes"), patch.object(self.task, "click") as click, patch.object(self.task, "click_relative") as click_relative, patch.object(self.task, "send_key") as send_key, patch.object(self.task, "log_info"), patch.object(self.task, "log_error"), patch.object(self.task, "info_set") as info_set:  # 隔离截图、识别、绘框、日志和所有可能的输入接口。
            self.task._inspect_once()  # 执行一轮完整的当前屏幕识别测试。
        next_frame.assert_called_once_with()  # 确认任务只主动获取了一张截图。
        self.assertEqual([call("Feature-A", threshold=-1.0), call("Feature-B", threshold=-1.0)], find_one.call_args_list)  # 确认全部元素都在同一缓存帧中取得原始分数。
        detect_scene.assert_called_once_with(refresh=False)  # 确认最终场景判断不会刷新为另一张截图。
        info_set.assert_called_once_with("Detected Scene", "大地图 (map)")  # 确认界面上会展示最终场景判断。
        click.assert_not_called()  # 确认任务没有点击任何模板位置。
        click_relative.assert_not_called()  # 确认任务没有执行坐标点击。
        send_key.assert_not_called()  # 确认任务没有发送任何键盘输入。

    def test_overlay_only_draws_boxes_at_or_above_threshold(self):  # 验证覆盖层不会保留低于阈值的候选框或搜索区域。
        matched_box = MagicMock()  # 构造达到阈值的模板候选框。
        matched_box.confidence = 0.95  # 设置高于默认阈值的置信度。
        unmatched_box = MagicMock()  # 构造低于阈值的模板候选框。
        unmatched_box.confidence = 0.50  # 设置低于默认阈值的置信度。
        with patch.object(self.task, "next_frame", return_value=object()), patch.object(self.task, "_load_feature_names", return_value=["Matched", "Unmatched"]), patch.object(self.task, "find_one", side_effect=[matched_box, unmatched_box]), patch.object(self.task, "_detect_scene", return_value="unknown"), patch.object(self.task, "clear_box") as clear_box, patch.object(self.task, "draw_boxes") as draw_boxes, patch.object(self.task, "log_info"), patch.object(self.task, "log_error"), patch.object(self.task, "info_set"):  # 隔离真实截图、模板引擎和覆盖层事件。
            self.task._inspect_once()  # 完成一轮包含高低两种置信度结果的识别。
        clear_box.assert_called_once_with()  # 确认自动产生的全部候选框和搜索区域先被清除。
        draw_boxes.assert_called_once_with("screen_recognition_matches", [matched_box], color="red")  # 确认只重新绘制超过阈值的候选框。

    def test_area_inspection_reports_recognized_color(self):  # 验证诊断任务识别占领区时会同时显示颜色。
        area_box = MagicMock()  # 构造已经通过三种颜色比较的区域匹配框。
        area_box.confidence = 0.98  # 设置用于日志展示的区域匹配置信度。
        with patch.object(self.task, "next_frame", return_value=object()), patch.object(self.task, "_load_feature_names", return_value=["Area-A"]), patch.object(self.task, "_find_area", return_value=(area_box, "green")) as find_area, patch.object(self.task, "find_one") as find_one, patch.object(self.task, "_detect_scene", return_value="map"), patch.object(self.task, "clear_box"), patch.object(self.task, "draw_boxes"), patch.object(self.task, "log_info") as log_info, patch.object(self.task, "log_error"), patch.object(self.task, "info_set"):  # 隔离截图、模板匹配、绘框与状态输出。
            self.task._inspect_once()  # 执行一轮只包含单个占领区的颜色识别。
        find_area.assert_called_once_with("Area-A")  # 确认区域元素改用返回颜色的专用识别入口。
        find_one.assert_not_called()  # 确认不会再用原始灰色模板重复识别同一区域。
        self.assertIn(call("[命中] Area-A: 98.00% (green)"), log_info.call_args_list)  # 确认诊断日志包含字母、分数和颜色。

    def test_run_continues_into_a_second_inspection_after_three_seconds(self):  # 验证任务不会在第一轮识别后正常返回。
        with patch.object(self.task, "_inspect_once") as inspect_once, patch.object(self.task, "sleep", side_effect=[None, RuntimeError("manual stop")]) as sleep:  # 在第二次等待时模拟用户手动停止。
            with self.assertRaisesRegex(RuntimeError, "manual stop"):  # 确认循环只因模拟的停止信号结束。
                self.task.run()  # 启动诊断任务式持续循环。
        self.assertEqual(2, inspect_once.call_count)  # 确认等待三秒后确实进入第二轮屏幕识别。
        self.assertEqual([call(3), call(3)], sleep.call_args_list)  # 确认每轮识别后都使用任务睡眠等待三秒。


if __name__ == "__main__":  # 支持直接运行本测试文件。
    unittest.main()  # 启动标准库测试运行器。
