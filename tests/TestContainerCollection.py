import json  # 读取正式标注及参考截图位置。
import unittest  # 使用标准库测试领取流程。
from pathlib import Path  # 解析项目资源路径。
from unittest.mock import MagicMock, patch  # 隔离游戏输入并记录执行顺序。

import cv2  # 读取真实截图验证模板。
from ok import FeatureSet  # 使用正式模板匹配引擎。

from src.config import config, make_bottom_right_black  # 复用实际模板参数和截图预处理。
from src.tasks.AutoPveBattleTask import AutoPveBattleTask  # 测试自动战斗任务的领取收尾。
from tests.ocr_support import bind_ocr  # 将实图验证连接到应用使用的 OCR。


class TestContainerCollection(unittest.TestCase):  # 覆盖领取耗尽、异常和完成顺序。
    def setUp(self):  # 每个测试使用隔离的执行器。
        self.executor = MagicMock()  # 禁止连接真实游戏。
        self.executor.scene = None  # 满足基类初始化要求。
        self.task = AutoPveBattleTask(self.executor, None)  # 同时验证任务可以导入并实例化。
        self.task.config = dict(self.task.default_config)  # 使用默认配置副本。

    def test_collects_until_pick_has_no_response(self):  # 验证零个和多个集装箱都会在无反应时停止。
        for count in (0, 3):  # 覆盖首次即耗尽和连续成功领取。
            with self.subTest(count=count):  # 区分两种耗尽场景。
                results = [True] + [True, True] * count + [True, False]  # 菜单成功，每次领取确认成功，最后一次领取无确认。
                with patch.object(self.task, "get_feature_by_name", return_value=object()), patch.object(self.task, "wait_click_feature", side_effect=results) as click, patch.object(self.task, "wait_until", return_value=True), patch.object(self.task, "sleep"), patch.object(self.task, "log_info"):  # 隔离输入和动画等待。
                    self.assertTrue(self.task._collect_containers())  # 点击无反应应正常完成。
                expected = ["Container-Menu"] + ["Pick-Container", "Confirm-Container"] * (count + 1)  # 最后一轮也必须实际点击领取后才判断无反应。
                self.assertEqual(expected, [entry.args[0] for entry in click.call_args_list])  # 严格检查点击顺序且没有多余操作。

    def test_stuck_confirmation_stops_collection(self):  # 避免确认按钮卡住时无限重复领取。
        with patch.object(self.task, "get_feature_by_name", return_value=object()), patch.object(self.task, "wait_click_feature", return_value=True) as click, patch.object(self.task, "wait_until", return_value=False), patch.object(self.task, "log_error") as error:  # 模拟确认按钮始终未消失。
            self.assertFalse(self.task._collect_containers())  # 卡住必须报告失败。
        self.assertEqual(3, click.call_count)  # 只点击菜单、领取和确认一次。
        error.assert_called_once()  # 向用户提供失败原因。

    def test_missing_template_stops_before_clicking(self):  # 模板缺失不能等价于集装箱耗尽。
        with patch.object(self.task, "get_feature_by_name", return_value=None), patch.object(self.task, "wait_click_feature") as click, patch.object(self.task, "log_error"):  # 模拟当前比例没有标注。
            self.assertFalse(self.task._collect_containers())  # 明确返回失败。
        click.assert_not_called()  # 资源不齐时不发送输入。

    def test_missing_menu_or_pick_is_failure(self):  # 未成功点击领取按钮时不报告领取耗尽。
        for results in ([False], [True, False]):  # 分别模拟菜单缺失和领取按钮缺失。
            with self.subTest(results=results):  # 区分入口和领取页异常。
                with patch.object(self.task, "get_feature_by_name", return_value=object()), patch.object(self.task, "wait_click_feature", side_effect=results), patch.object(self.task, "log_error"):  # 提供有限点击结果。
                    self.assertFalse(self.task._collect_containers())  # 两种异常都必须报告失败。

    def test_finishes_and_closes_only_after_collection(self):  # 返回港口、领取、通知和关闭必须按顺序执行。
        self.task.config["Close Game After Completion"] = True  # 开启关闭游戏以验证收尾时序。
        events = MagicMock()  # 汇总跨方法调用顺序。
        with patch.object(self.task, "_return_to_main", return_value=True) as port, patch.object(self.task, "_collect_containers", return_value=True) as collect, patch.object(self.task, "log_info") as log:  # 模拟所有收尾操作成功。
            events.attach_mock(port, "port")  # 记录确认回港。
            events.attach_mock(collect, "collect")  # 记录领取操作。
            events.attach_mock(log, "log")  # 记录完成通知。
            events.attach_mock(self.executor.device_manager.stop_hwnd, "close")  # 记录实际关闭游戏接口。
            self.task._finish_successfully()  # 执行共用收尾入口。
        self.assertEqual(["port", "collect", "log", "log", "close"], [entry[0] for entry in events.mock_calls])  # 领取必须先于成功通知和关闭。

    def test_failure_does_not_close_or_notify_success(self):  # 收尾失败时保留现场。
        self.task.config["Close Game After Completion"] = True  # 确保失败能够阻止已开启的关闭功能。
        for port_ready in (False, True):  # 分别模拟回港失败和领取失败。
            with self.subTest(port_ready=port_ready):  # 标出失败阶段。
                with patch.object(self.task, "_return_to_main", return_value=port_ready), patch.object(self.task, "_collect_containers", return_value=False) as collect, patch.object(self.task, "log_info") as log, patch.object(self.task, "log_error"):  # 隔离真实游戏操作。
                    self.task._finish_successfully()  # 执行失败收尾。
                self.assertEqual(int(port_ready), collect.call_count)  # 只有确认回港才能开始领取。
                log.assert_not_called()  # 不错误报告成功。
                self.executor.device_manager.stop_hwnd.assert_not_called()  # 不关闭游戏。

    def test_container_templates_match_reference_screens(self):  # 用原始截图验证同步后的正式模板能够正确命中。
        bind_ocr(self.executor)  # 三个按钮均已迁移到文字识别。
        reference = Path("ok_templates/21x9/coco_annotations.json")  # 原始参考截图不进入版本库。
        if not reference.exists():  # 无本地截图的环境仍可运行流程单元测试。
            self.skipTest("Container reference screenshots are unavailable.")  # 明确跳过真实截图验证。
        raw = json.loads(reference.read_text(encoding="utf-8"))  # 读取原始标注定位页面。
        matching = config["template_matching"]  # 沿用正式匹配配置。
        feature_set = FeatureSet(False, "assets/21x9/coco_annotations.json", default_horizontal_variance=matching["default_horizontal_variance"], default_vertical_variance=matching["default_vertical_variance"], default_threshold=matching["default_threshold"])  # 加载刚同步的发布资源。
        self.executor.feature_set = feature_set  # 为任务连接真实模板引擎。
        for name in ("Container-Menu", "Pick-Container", "Confirm-Container"):  # 三个按钮均需实图验证。
            with self.subTest(name=name):  # 标出无法识别的具体按钮。
                category = next(item["id"] for item in raw["categories"] if item["name"] == name)  # 找到原始分类。
                annotation = next(item for item in raw["annotations"] if item["category_id"] == category)  # 找到对应位置。
                metadata = next(item for item in raw["images"] if item["id"] == annotation["image_id"])  # 找到原始截图。
                frame = make_bottom_right_black(cv2.imread(str(reference.parent / metadata["file_name"])))  # 读取真实截图并应用正式预处理。
                self.executor.frame = frame  # 使用实际截图供任务识别。
                self.executor.method.width = frame.shape[1]  # 提供真实画面宽度。
                self.executor.method.height = frame.shape[0]  # 提供真实画面高度。
                self.assertIsNotNone(self.task.find_one(name, threshold=self.task.threshold))  # 确认正式模板可以在默认阈值下识别。

    @unittest.skipUnless(Path("ok_templates/21x9/32.png").is_file(), "Container screenshot 32 unavailable")
    def test_pick_container_matches_shifted_daily_container_on_screen_32(self):  # 复现活动列表使每日补给箱下移后无法识别的问题。
        bind_ocr(self.executor)
        original = cv2.imread("ok_templates/21x9/32.png")
        for scale in (1, .5):
            with self.subTest(scale=scale):
                frame = original if scale == 1 else cv2.resize(original, None, fx=scale, fy=scale)
                self.executor.frame = make_bottom_right_black(frame)
                match = self.task.find_one("Pick-Container", threshold=self.task.threshold)
                self.assertIsNotNone(match)
                x, y = match.center()
                self.assertTrue(0 < x < frame.shape[1] * .1)
                self.assertTrue(frame.shape[0] * .39 < y < frame.shape[0] * .44)  # 点击必须落在左侧每日补给箱标题处。

    def test_restart_can_leave_container_screen(self):  # 领取结束停在集装箱页面时，下一次任务仍能回到主界面。
        for name in ("Pick-Container", "Confirm-Container"):  # 普通领取页和确认页都可以恢复。
            with self.subTest(name=name):  # 区分两种集装箱状态。
                with patch.object(self.task, "next_frame"), patch.object(self.task, "_detect_battle_view", return_value=None), patch.object(self.task, "find_one", side_effect=lambda feature, **kwargs: object() if feature == name else None):  # 只让集装箱特征命中。
                    self.assertEqual("container", self.task._detect_scene())  # 确认不会当成未知画面。
        with patch.object(self.task, "_detect_scene", side_effect=["container", "main"]), patch.object(self.task, "send_key") as key:  # 模拟按 ESC 后回到港口。
            self.assertTrue(self.task._return_to_main())  # 再次启动能正常完成回港。
        self.assertEqual("esc", key.call_args.args[0])  # 集装箱页通过返回键退出。
