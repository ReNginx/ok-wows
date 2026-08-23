import os  # 导入路径工具以判断本地忽略的原始模板目录是否存在。
import unittest  # 导入标准库单元测试框架。
from unittest.mock import MagicMock, call, patch  # 导入方法替身、调用记录和临时补丁工具。

import cv2  # 导入 OpenCV 以读取完整标注参考截图。
import numpy as np  # 导入数组工具以构造颜色模板测试数据。
from ok import Box  # 导入模板匹配结果使用的矩形框类型。
from ok import FeatureSet  # 导入真实模板引擎以验证场景标注。

from src.config import config, make_bottom_right_black  # 导入应用配置和正式截图预处理器。
from src.tasks.AutoPveBattleTask import AutoPveBattleTask  # 导入本次新增的自动 PVE 任务。


class TestAutoPveBattleTask(unittest.TestCase):  # 定义不共享全局应用状态的自动 PVE 任务测试集合。

    def setUp(self):  # 为每个测试创建完全隔离的轻量任务实例。
        executor = MagicMock()  # 构造不连接真实游戏窗口的执行器替身。
        executor.scene = None  # 提供任务基类初始化所需的场景属性。
        self.task = AutoPveBattleTask(executor, None)  # 使用替身执行器创建待测任务。
        self.task.config = dict(self.task.default_config)  # 使用普通字典模拟任务保存后的有效配置。

    def test_task_is_registered_with_safe_defaults(self):  # 验证应用能发现任务且默认配置安全。
        self.assertIn(["src.tasks.AutoPveBattleTask", "AutoPveBattleTask"], config["onetime_tasks"])  # 确认任务已注册到一次性任务列表。
        self.assertEqual(1, self.task.default_config["Battle Count"])  # 确认默认只执行一场战斗。
        self.assertEqual(0.8, self.task.default_config["Template Threshold"])  # 确认默认匹配阈值与项目一致。

    def test_config_validation_rejects_invalid_values(self):  # 验证危险或无效输入会被配置界面拒绝。
        self.assertIsNotNone(self.task.validate_config("Battle Count", 0))  # 零场战斗必须视为无效。
        self.assertIsNotNone(self.task.validate_config("Battle Count", True))  # 布尔值不能被当作整数战斗场数。
        self.assertIsNotNone(self.task.validate_config("Template Threshold", 1.1))  # 大于一的匹配阈值必须视为无效。
        self.assertIsNone(self.task.validate_config("Battle Count", 2))  # 正整数战斗场数应该通过校验。
        self.assertIsNone(self.task.validate_config("Template Threshold", 0.85))  # 合法置信度应该通过校验。

    def test_scene_detection_uses_unique_main_screen_elements(self):  # 验证主界面需要两个独特元素共同确认。
        boxes = {  # 构造只包含主界面两个特有元素的匹配结果。
            "Join-Battle": Box(10, 10, 20, 20, name="Join-Battle"),  # 模拟加入战斗按钮。
            "Select-Battle-Mode": Box(40, 10, 20, 20, name="Select-Battle-Mode"),  # 模拟模式选择按钮。
        }  # 完成模拟匹配结果定义。
        with patch.object(self.task, "next_frame"), patch.object(self.task, "find_one", side_effect=lambda name, **kwargs: boxes.get(name)):  # 使用同一张模拟截图执行场景识别。
            self.assertEqual("main", self.task._detect_scene())  # 两个主界面元素同时存在时应识别为主界面。

    def test_scene_detection_prioritizes_menu(self):  # 验证菜单覆盖其他页面时优先识别菜单。
        menu_box = Box(10, 10, 20, 20, name="Menu")  # 构造菜单特有元素的匹配结果。
        with patch.object(self.task, "next_frame"), patch.object(self.task, "find_one", return_value=menu_box):  # 模拟截图中所有查询都能看到菜单元素。
            self.assertEqual("menu", self.task._detect_scene())  # 菜单应以最高优先级返回。

    def test_scene_detection_prioritizes_leave_battle_over_battle(self):  # 验证舰船被击沉时优先处理离开战斗而不是继续开火。
        boxes = {  # 构造同时包含离开入口和普通战斗罗盘的匹配结果。
            "Leave-Battle": Box(10, 10, 20, 20, name="Leave-Battle"),  # 模拟十二号截图中的离开战斗入口。
            "In-Battle-Compass": Box(40, 10, 20, 20, name="In-Battle-Compass"),  # 模拟击沉页面仍然保留的战斗罗盘。
        }  # 完成模拟匹配结果定义。
        with patch.object(self.task, "next_frame"), patch.object(self.task, "find_one", side_effect=lambda name, **kwargs: boxes.get(name)):  # 使用同一张模拟截图执行场景识别。
            self.assertEqual("leave_battle", self.task._detect_scene())  # 离开入口出现时必须进入离开处理分支。

    def test_nameplate_and_tutorial_together_identify_map(self):  # 验证舰船铭牌和教程元素共同确认大地图状态。
        boxes = {"Libertadad-Nameplate": Box(10, 10, 20, 20, name="Libertadad-Nameplate"), "Map-Tutorial": Box(40, 10, 20, 20, name="Map-Tutorial")}  # 构造同一帧中的舰船铭牌和大地图教程元素。
        with patch.object(self.task, "next_frame"), patch.object(self.task, "find_one", side_effect=lambda name, **kwargs: boxes.get(name)):  # 模拟两个组合模板同时命中的大地图画面。
            self.assertEqual("map", self.task._detect_scene())  # 两个元素同时命中时应判断为大地图。

    def test_nameplate_without_tutorial_identifies_battle(self):  # 验证只有舰船铭牌时判断为普通战斗页面。
        nameplate_box = Box(10, 10, 20, 20, name="Libertadad-Nameplate")  # 构造普通战斗界面的舰船铭牌匹配结果。
        with patch.object(self.task, "next_frame"), patch.object(self.task, "find_one", side_effect=lambda name, **kwargs: nameplate_box if name == "Libertadad-Nameplate" else None):  # 模拟铭牌存在但教程元素不存在的战斗画面。
            self.assertEqual("battle", self.task._detect_scene())  # 缺少教程元素时应判断为普通战斗。

    def test_tutorial_without_nameplate_identifies_battle(self):  # 验证缺少铭牌时按用户指定的否则分支判断为战斗。
        tutorial_box = Box(10, 10, 20, 20, name="Map-Tutorial")  # 构造只有教程元素命中的异常画面。
        with patch.object(self.task, "next_frame"), patch.object(self.task, "find_one", side_effect=lambda name, **kwargs: tutorial_box if name == "Map-Tutorial" else None):  # 模拟舰船铭牌没有匹配成功。
            self.assertEqual("battle", self.task._detect_scene())  # 缺少任一组合元素时应进入普通战斗分支。

    @unittest.skipUnless(os.path.isdir("ok_templates"), "Local reference screenshots are not available.")  # 仅在本地原始模板目录存在时运行截图集成验证。
    def test_annotated_reference_screens_have_expected_scenes(self):  # 用完整标注截图验证全部页面都能被状态机识别。
        expected_scenes = {  # 按工作流截图编号定义预期页面状态。
            "0.png": "battle_mode",  # 零号截图是战斗模式选择页。
            "1.png": "queue",  # 一号截图是战斗排队页。
            "2.png": "main",  # 二号截图是游戏主界面。
            "3.png": "battle_start",  # 三号截图是等待战斗开始页。
            "4.png": "battle",  # 四号截图是战斗界面。
            "5.png": "battle",  # 五号旧地图截图缺少新铭牌时按新组合规则归入战斗分支。
            "6.png": "result",  # 六号截图是战斗结束页。
            "7.png": "addon",  # 七号截图是未装备加成状态页。
            "8.png": "addon",  # 八号截图是已装备加成状态页。
            "9.png": "equipment",  # 九号截图是未装备旗子状态页。
            "10.png": "equipment",  # 十号截图是已装备旗子状态页。
            "11.png": "menu",  # 十一号截图是菜单页面。
            "12.png": "leave_battle",  # 十二号截图是舰船被击沉后的离开战斗页面。
            "14.png": "map",  # 十四号截图使用 Map-Tutorial 正确识别为大地图。
            "15.png": "battle",  # 十五号截图只有舰船铭牌时识别为普通战斗。
            "16.png": "battle",  # 十六号截图只有舰船铭牌时识别为普通战斗。
        }  # 完成截图与状态的对应关系定义。
        matching_config = config["template_matching"]  # 读取应用真实模板引擎参数。
        feature_set = FeatureSet(False, matching_config["coco_feature_json"], default_horizontal_variance=matching_config["default_horizontal_variance"], default_vertical_variance=matching_config["default_vertical_variance"], default_threshold=matching_config["default_threshold"])  # 创建不依赖 GUI 生命周期的真实模板引擎。
        current_frame = {"value": None}  # 使用可变容器保存当前子测试对应的截图。

        def find_one(feature_name, threshold=0, **kwargs):  # 定义并兼容全屏查询参数的轻量模板查询函数。
            boxes = feature_set.find_feature(current_frame["value"], feature_name, threshold=threshold, limit=1)  # 在当前参考截图中查找指定特有元素。
            return boxes[0] if boxes else None  # 有匹配时返回第一个矩形框，否则返回空值。

        for image_name, expected_scene in expected_scenes.items():  # 逐张加载用户已标注的参考截图。
            with self.subTest(image=image_name):  # 在失败信息中保留具体截图名称。
                current_frame["value"] = make_bottom_right_black(cv2.imread(f"ok_templates/{image_name}"))  # 按正式截图处理方式加载参考图片。
                with patch.object(self.task, "next_frame", return_value=current_frame["value"]), patch.object(self.task, "find_one", side_effect=find_one):  # 把任务场景判断连接到真实模板查询函数。
                    self.assertEqual(expected_scene, self.task._detect_scene())  # 确认特有元素能够判断出预期页面。

    @unittest.skipUnless(os.path.isdir("ok_templates"), "Local reference screenshots are not available.")  # 仅在本地原始模板目录存在时运行确认按钮验证。
    def test_leave_confirmation_template_matches_reference_screen(self):  # 验证十三号截图中的确认离开按钮可以被真实模板识别。
        matching_config = config["template_matching"]  # 读取应用真实模板引擎参数。
        feature_set = FeatureSet(False, matching_config["coco_feature_json"], default_horizontal_variance=matching_config["default_horizontal_variance"], default_vertical_variance=matching_config["default_vertical_variance"], default_threshold=matching_config["default_threshold"])  # 创建不依赖 GUI 生命周期的真实模板引擎。
        frame = make_bottom_right_black(cv2.imread("ok_templates/13.png"))  # 按正式截图预处理方式加载十三号参考图。
        boxes = feature_set.find_feature(frame, "Confirm-Leaving-Battle", threshold=self.task.threshold, limit=1)  # 在确认页面中匹配确认离开按钮。
        self.assertTrue(boxes)  # 确认模板能够稳定找到用户标注的按钮。

    def test_map_selects_nearest_recognized_area_without_requiring_all_four(self):  # 验证只识别到部分区域时也会选择其中最近的一个。
        map_overview = Box(0, 0, 300, 300, name="Map-Overview")  # 构造十九号截图标注对应的主地图范围。
        cursor = Box(0, 0, 10, 10, name="My-Ship-Cursor")  # 构造舰船光标位置。
        area_a = Box(10, 0, 10, 10, name="Area-A")  # 构造距离舰船最近但不应导航的绿色 A 区。
        area_b = Box(100, 0, 10, 10, name="Area-B")  # 构造距离舰船较远的红色 B 区。
        area_d = Box(20, 0, 10, 10, name="Area-D")  # 构造距离舰船最近的 D 区。
        areas = {"Area-A": (area_a, "green"), "Area-B": (area_b, "red"), "Area-D": (area_d, "gray")}  # 提供绿色、红色和灰色结果以验证导航过滤规则。
        with patch.object(self.task, "wait_until", return_value=True), patch.object(self.task, "next_frame"), patch.object(self.task, "get_box_by_name", return_value=map_overview), patch.object(self.task, "_find_rotated_ship_cursor", return_value=cursor) as find_cursor, patch.object(self.task, "_find_area", side_effect=lambda name, box: areas.get(name, (None, None))) as find_area, patch.object(self.task, "find_one", return_value=None), patch.object(self.task, "click") as click, patch.object(self.task, "_close_map"), patch.object(self.task, "log_info") as log_info:  # 隔离地图处理中的截图和输入操作。
            self.task._handle_map()  # 执行一次地图航点选择。
        find_cursor.assert_called_once_with(map_overview)  # 确认舰船光标只在十九号截图框定的主地图范围内查找。
        for feature_name in ("Area-A", "Area-B", "Area-C", "Area-D"):  # 逐一检查四个区域的颜色识别范围。
            find_area.assert_any_call(feature_name, map_overview)  # 确认每个区域都限制在主地图范围内并返回颜色。
        click.assert_called_once_with(area_d, after_sleep=1)  # 确认任务点击实际识别结果中距离最近的 D 区。
        log_info.assert_called_once_with("选择最近占领区 Area-D，颜色为 gray。")  # 确认导航日志包含识别到的字母颜色。

    def test_area_recognition_returns_highest_scoring_color(self):  # 验证单个区域会比较三种颜色并返回最高分颜色。
        map_overview = Box(0, 0, 300, 300, name="Map-Overview")  # 构造颜色模板搜索使用的主地图范围。
        feature = MagicMock()  # 构造包含原始模板矩阵的正式特征替身。
        feature.mat = np.zeros((20, 12, 3), dtype=np.uint8)  # 提供可由 OpenCV 转换颜色的三通道模板。
        matches = [Box(10, 10, 12, 20, confidence=0.91, name="Area-A"), None, Box(10, 10, 12, 20, confidence=0.95, name="Area-A")]  # 模拟绿色、红色和灰色依次得到的结果。
        with patch.object(self.task, "get_feature_by_name", return_value=feature), patch.object(self.task, "find_one", side_effect=matches) as find_one:  # 隔离正式模板资源并控制三种颜色的匹配分数。
            area_box, area_color = self.task._find_area("Area-A", map_overview)  # 识别单个字母并取得其最高分颜色。
        self.assertIs(area_box, matches[2])  # 确认返回三种颜色候选中置信度最高的匹配框。
        self.assertEqual("gray", area_color)  # 确认返回值同时包含最高分模板对应的颜色。
        self.assertEqual(3, find_one.call_count)  # 确认绿色、红色和灰色模板都参与比较。
        for match_call in find_one.call_args_list:  # 检查每一种颜色调用都使用正式匹配范围和阈值。
            self.assertEqual("Area-A", match_call.args[0])  # 确认颜色变体仍使用原字母特征名称。
            self.assertEqual(0.8, match_call.kwargs["threshold"])  # 确认颜色识别遵循任务配置阈值。
            self.assertIs(map_overview, match_call.kwargs["box"])  # 确认颜色识别限制在主地图范围内。
            self.assertIsInstance(match_call.kwargs["template"], np.ndarray)  # 确认每次调用都把转换后的模板交给框架原生接口。

    @unittest.skipUnless(os.path.isfile("ok_templates/14.png"), "Map reference screenshot is not available.")  # 仅在本地十四号地图截图存在时运行颜色识别集成验证。
    def test_area_colors_match_reference_map(self):  # 用十四号真实截图验证四个字母及颜色能够同时识别。
        matching_config = config["template_matching"]  # 读取应用真实模板引擎参数。
        feature_set = FeatureSet(False, matching_config["coco_feature_json"], default_horizontal_variance=matching_config["default_horizontal_variance"], default_vertical_variance=matching_config["default_vertical_variance"], default_threshold=matching_config["default_threshold"])  # 创建与正式任务一致的模板引擎。
        frame = make_bottom_right_black(cv2.imread("ok_templates/14.png"))  # 按正式截图预处理方式加载十四号大地图。
        self.task.executor.feature_set = feature_set  # 将任务连接到真实模板引擎以执行颜色变体匹配。
        self.task.executor.frame = frame  # 把十四号截图设置为任务正在处理的最新帧。
        self.task.executor.method.width = frame.shape[1]  # 提供框架全屏搜索框计算所需的画面宽度。
        self.task.executor.method.height = frame.shape[0]  # 提供框架全屏搜索框计算所需的画面高度。
        map_overview = self.task.get_box_by_name("Map-Overview")  # 读取会随截图分辨率缩放的正式主地图范围。
        results = {area_name: self.task._find_area(area_name, map_overview)[1] for area_name in ("Area-A", "Area-B", "Area-C", "Area-D")}  # 使用正式任务接口识别四个字母对应的颜色。
        self.assertEqual({"Area-A": "green", "Area-B": "red", "Area-C": "gray", "Area-D": "gray"}, results)  # 确认十四号截图返回绿、红、灰、灰四种状态。

    def test_map_selects_enemy_base_when_no_area_is_recognized(self):  # 验证没有占领区时会使用识别到的敌方基地。
        map_overview = Box(100, 100, 800, 600, name="Map-Overview")  # 构造主地图范围。
        enemy_base = Box(700, 150, 20, 20, name="Enemy-Base")  # 构造敌方基地匹配结果。
        with patch.object(self.task, "wait_until", return_value=True), patch.object(self.task, "next_frame"), patch.object(self.task, "get_box_by_name", return_value=map_overview), patch.object(self.task, "_find_rotated_ship_cursor", return_value=None), patch.object(self.task, "_find_area", return_value=(None, None)), patch.object(self.task, "find_one", side_effect=lambda name, **kwargs: enemy_base if name == "Enemy-Base" else None), patch.object(self.task, "click") as click, patch.object(self.task, "_close_map"):  # 模拟只识别到敌方基地的地图。
            self.task._handle_map()  # 执行一次地图航点选择。
        click.assert_called_once_with(enemy_base, after_sleep=1)  # 确认任务直接点击敌方基地。

    @unittest.skipUnless(all(os.path.isfile(f"ok_templates/{name}.png") for name in (14, 17, 19)), "Rotated cursor reference screenshots are not available.")  # 仅在三张地图参考截图齐全时运行旋转匹配验证。
    def test_rotated_ship_cursor_matches_reference_maps(self):  # 验证不同朝向的舰船光标都能通过旋转模板识别。
        matching_config = config["template_matching"]  # 读取应用真实模板引擎参数。
        feature_set = FeatureSet(False, matching_config["coco_feature_json"], default_horizontal_variance=matching_config["default_horizontal_variance"], default_vertical_variance=matching_config["default_vertical_variance"], default_threshold=matching_config["default_threshold"])  # 创建与正式任务一致的模板引擎。
        expected_centers = {14: (1852, 827), 17: (2118, 1430), 19: (2970, 1398)}  # 记录三张截图中主地图舰船光标的预期中心坐标。
        self.task.executor.feature_set = feature_set  # 将任务连接到真实模板引擎以执行旋转匹配。
        self.task.executor.device_manager.supported_ratio = 5120 / 2160  # 模拟正式配置使用的六十四比二十七画面比例。
        for image_number, expected_center in expected_centers.items():  # 逐张验证三种不同朝向的地图截图。
            with self.subTest(image=f"{image_number}.png"):  # 在测试失败信息中保留具体截图编号。
                frame = make_bottom_right_black(cv2.imread(f"ok_templates/{image_number}.png"))  # 按正式截图预处理方式读取完整参考画面。
                self.task.executor.frame = frame  # 把当前参考截图设置为任务正在处理的最新帧。
                self.task.executor.method.width = frame.shape[1]  # 提供全屏搜索框计算所需的画面宽度。
                self.task.executor.method.height = frame.shape[0]  # 提供全屏搜索框计算所需的画面高度。
                cursor = self.task._find_rotated_ship_cursor()  # 使用正式旋转模板逻辑查找舰船光标。
                self.assertIsNotNone(cursor)  # 每张参考截图都必须成功识别出一个舰船光标。
                self.assertGreaterEqual(cursor.confidence, 0.7)  # 确认原始分辨率匹配结果达到旋转光标的专用阈值。
                center_x, center_y = cursor.center()  # 读取匹配框中心以排除右下角小地图中的相似图标。
                self.assertAlmostEqual(expected_center[0], center_x, delta=40)  # 确认匹配结果位于主地图光标的水平位置附近。
                self.assertAlmostEqual(expected_center[1], center_y, delta=40)  # 确认匹配结果位于主地图光标的垂直位置附近。

    def test_map_uses_center_opposite_point_when_no_target_is_recognized(self):  # 验证没有区域或基地时会导航到舰船所在位置的地图另一侧。
        map_overview = Box(100, 100, 800, 600, name="Map-Overview")  # 构造左上角为一百且大小为八百乘六百的主地图范围。
        cases = ((Box(495, 590, 10, 10, name="bottom"), (500, 205)), (Box(195, 195, 10, 10, name="top-left"), (800, 600)))  # 定义下方去上方以及左上去右下的中心对称坐标。
        for cursor, expected_point in cases:  # 逐一验证用户指定的两个方向示例。
            with self.subTest(cursor=cursor.name):  # 在失败信息中标明当前舰船起始方位。
                with patch.object(self.task, "wait_until", return_value=True), patch.object(self.task, "next_frame"), patch.object(self.task, "get_box_by_name", return_value=map_overview), patch.object(self.task, "_find_rotated_ship_cursor", return_value=cursor), patch.object(self.task, "_find_area", return_value=(None, None)), patch.object(self.task, "find_one", return_value=None), patch.object(self.task, "click") as click, patch.object(self.task, "_close_map"):  # 模拟没有任何区域或基地匹配的地图。
                    self.task._handle_map()  # 执行地图对侧航点选择。
                click.assert_called_once_with(*expected_point, name="opposite-map-side", after_sleep=1)  # 确认点击主地图内与舰船中心对称的位置。

    def test_close_map_uses_m_when_escape_does_not_close_it(self):  # 验证 ESC 未关闭大地图时使用 M 键兜底。
        with patch.object(self.task, "send_key") as send_key, patch.object(self.task, "next_frame"), patch.object(self.task, "_map_is_visible", return_value=True), patch.object(self.task, "log_warning"):  # 模拟按下 ESC 后独特大地图组合仍然存在。
            self.task._close_map()  # 执行带结果确认的地图关闭流程。
        self.assertEqual([call("esc", after_sleep=2), call("m", after_sleep=2)], send_key.call_args_list)  # 确认先遵循工作流按 ESC 再用 M 恢复。

    def test_leave_battle_confirms_and_rejoins_without_preparation(self):  # 验证击沉后确认离开并直接加入下一场战斗。
        with patch.object(self.task, "wait_click_feature", side_effect=[True, True, True]) as wait_click, patch.object(self.task, "_prepare_and_join_first_battle") as prepare, patch.object(self.task, "log_error"):  # 模拟离开、确认和直接加入都成功。
            self.assertTrue(self.task._leave_battle_and_rejoin())  # 执行击沉后的恢复流程并确认成功。
        self.assertEqual([  # 确认三个按钮严格按页面出现顺序点击。
            call("Leave-Battle", threshold=0.8, time_out=10, raise_if_not_found=False, after_sleep=1),  # 先点击十二号截图中的离开战斗入口。
            call("Confirm-Leaving-Battle", threshold=0.8, time_out=10, raise_if_not_found=False, after_sleep=3),  # 再点击十三号截图中的确认按钮。
            call("Join-Battle", threshold=0.8, time_out=30, raise_if_not_found=False, after_sleep=2),  # 回到二号截图后直接点击加入战斗。
        ], wait_click.call_args_list)  # 对比实际按钮调用顺序和参数。
        prepare.assert_not_called()  # 确认恢复流程没有重新执行选船、模式、加成和旗子准备。

    def test_navigation_sends_exactly_ten_forward_keys_once(self):  # 验证单次航行初始化只发送十次前进键。
        with patch.object(self.task, "send_key") as send_key, patch.object(self.task, "_handle_map", return_value=True):  # 隔离真实键盘输入和地图处理。
            self.task._initialize_battle_navigation()  # 执行一次战斗航行初始化。
        forward_calls = [call for call in send_key.call_args_list if call.args == ("w",)]  # 筛选所有发送 W 键的调用。
        self.assertEqual(10, len(forward_calls))  # 确认前进键严格发送十次。
        send_key.assert_any_call("m", after_sleep=2)  # 确认十次前进后仍会发送 M 键打开地图。

    def test_start_button_time_fallback_initializes_dynamic_battle_hud(self):  # 验证不同舰船导致 HUD 模板失配时仍能执行前进初始化。
        scenes = iter(("battle_start", "unknown", "result"))  # 模拟点击开始后 HUD 一直无法模板识别再进入结算的状态序列。
        with patch.object(self.task, "_detect_scene", side_effect=lambda: next(scenes)), patch.object(self.task, "wait_click_feature", return_value=True), patch.object(self.task, "_initialize_battle_navigation") as initialize, patch("src.tasks.AutoPveBattleTask.time.monotonic", side_effect=(0, 31)):  # 模拟三十秒加载回退并隔离真实输入。
            self.assertTrue(self.task._run_until_result())  # 确认状态机最终能够继续运行到结算页。
        initialize.assert_called_once_with()  # 确认回退逻辑只执行一次十次前进初始化。

    def test_rejoined_battle_runs_navigation_initialization_again(self):  # 验证离开击沉页面并重新加入后会初始化新一场战斗。
        scenes = iter(("battle", "leave_battle", "battle", "result"))  # 模拟当前战斗、击沉离开、新战斗和最终结算的状态序列。
        with patch.object(self.task, "_detect_scene", side_effect=lambda: next(scenes)), patch.object(self.task, "_leave_battle_and_rejoin", return_value=True) as rejoin, patch.object(self.task, "_initialize_battle_navigation") as initialize:  # 隔离实际按钮点击和键盘地图操作。
            self.assertTrue(self.task._run_until_result())  # 执行包含击沉重开的完整状态机片段。
        rejoin.assert_called_once_with()  # 确认击沉页面只执行一次离开并直接重开流程。
        self.assertEqual(2, initialize.call_count)  # 确认新一场战斗不会沿用上一场的航行初始化状态。

    def test_run_counts_results_and_only_continues_when_needed(self):  # 验证战斗计数达到目标前才点击继续战斗。
        self.task.config["Battle Count"] = 2  # 将本次测试目标设置为两场战斗。
        run_until_result = MagicMock(return_value=True)  # 模拟每一场战斗都成功到达结算页。
        with patch.object(self.task, "_return_to_main", return_value=True), patch.object(self.task, "_prepare_and_join_first_battle", return_value=True), patch.object(self.task, "_run_until_result", run_until_result), patch.object(self.task, "wait_click_feature", return_value=True) as wait_click, patch.object(self.task, "log_info"), patch.object(self.task, "log_error"):  # 隔离真实游戏输入和日志状态并运行计数逻辑。
            self.task.run()  # 执行设置为两场的任务主流程。
        self.assertEqual(2, run_until_result.call_count)  # 确认两场战斗都被计入并处理。
        wait_click.assert_called_once_with("continue-battle-button", threshold=0.8, time_out=30, raise_if_not_found=False, after_sleep=2)  # 确认只在第一场结束后点击一次继续战斗。


if __name__ == "__main__":  # 支持直接运行本测试文件。
    unittest.main()  # 启动标准库单元测试运行器。
