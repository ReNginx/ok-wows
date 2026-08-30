import math  # 导入数学函数以计算旋转后模板的完整边界尺寸。
import random  # 导入随机数模块以生成战斗中的开火间隔。
import time  # 导入时间模块以限制无法识别界面的等待时长。

import cv2  # 导入 OpenCV 以旋转舰船光标模板。
import numpy as np  # 导入数组工具以计算模板边缘的地图背景色。
from qfluentwidgets import FluentIcon  # 导入任务列表中使用的内置图标。

from src.tasks.MyBaseTask import MyBaseTask  # 导入项目本地任务基类。


class AutoPveBattleTask(MyBaseTask):  # 定义自动完成 PVE 战斗的一次性任务。

    AREA_COLOR_HSV = {"green": (78, 171), "red": (6, 255), "gray": (0, 0)}  # 定义占领区绿色、红色和灰色模板使用的 OpenCV 色相与饱和度。

    def __init__(self, *args, **kwargs):  # 初始化任务元数据和可配置参数。
        super().__init__(*args, **kwargs)  # 首先初始化 ok-script 的基础任务能力。
        self.name = "Auto PVE Battle"  # 设置任务列表中显示的名称。
        self.description = "Automatically prepares the selected ship and completes a configured number of PVE battles."  # 设置任务用途说明。
        self.icon = FluentIcon.GAME  # 使用游戏图标标识该自动战斗任务。
        self.default_config.update({  # 添加任务运行时可由用户调整的配置。
            "Battle Count": 1,  # 默认完成一场战斗后停止。
            "Template Threshold": 0.8,  # 默认使用与项目一致的模板匹配阈值。
        })  # 完成默认配置定义。
        self.config_description.update({  # 添加配置项在界面中的帮助说明。
            "Battle Count": "Number of completed battles before the task stops.",  # 说明战斗场数的含义。
            "Template Threshold": "Minimum confidence required for template matching.",  # 说明匹配阈值的含义。
        })  # 完成配置说明定义。

    def validate_config(self, key, value):  # 在用户保存配置时检查输入是否合法。
        if key == "Battle Count" and (not isinstance(value, int) or isinstance(value, bool) or value < 1):  # 要求战斗场数是至少为一的整数。
            return "Battle Count must be an integer greater than or equal to 1."  # 返回战斗场数的校验提示。
        if key == "Template Threshold" and (not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 < value <= 1):  # 要求阈值位于有效置信度范围内。
            return "Template Threshold must be greater than 0 and less than or equal to 1."  # 返回匹配阈值的校验提示。
        return None  # 输入合法时不返回错误信息。

    @property  # 将匹配阈值暴露为便于内部调用的只读属性。
    def threshold(self):  # 读取并转换当前模板匹配阈值。
        return float(self.config.get("Template Threshold", 0.8))  # 从任务配置中取得匹配阈值。

    def run(self):  # 按工作流准备舰船并循环完成指定数量的战斗。
        target_count = int(self.config.get("Battle Count", 1))  # 读取本次任务需要完成的战斗场数。
        completed_count = 0  # 初始化本次任务已完成的战斗计数器。
        self.log_info(f"准备执行 {target_count} 场 PVE 战斗。")  # 记录任务开始和目标场数。
        if not self._return_to_main():  # 尝试从当前可返回的页面回到游戏主界面。
            self.log_error("无法回到游戏主界面，任务停止。")  # 记录无法开始准备流程的原因。
            return  # 无法确认主界面时安全结束任务。
        if not self._prepare_and_join_first_battle():  # 为第一场战斗选择模式、处理加成和旗子并加入队列。
            self.log_error("第一场战斗准备失败，任务停止。")  # 记录准备流程失败。
            return  # 准备失败时安全结束任务。
        while completed_count < target_count:  # 持续运行战斗循环直到达到用户设置的场数。
            outcome = self._run_until_result(completed_count, target_count)  # 进行一场战斗直到结算页或处理舰船被击沉。
            if outcome == "error":  # 无法继续识别界面时判定为流程失败。
                self.log_error("等待战斗结算超时，任务停止。")  # 记录无法继续识别界面的错误。
                return  # 无法到达结算页时安全结束任务。
            completed_count += 1  # 本场战斗无论正常结算还是被击沉都计入已完成数量。
            self.log_info(f"已完成 {completed_count}/{target_count} 场 PVE 战斗。")  # 更新战斗完成进度日志。
            if completed_count >= target_count:  # 检查是否已经达到用户设定的战斗场数。
                self.log_info("已达到设定战斗场数，任务完成。", notify=True)  # 通知用户任务已经完成。
                return  # 无论停在结算页还是已确认离开返回港口都结束任务。
            if outcome == "result":  # 仅正常结算页需要点击继续战斗按钮进入下一次排队。
                if not self.wait_click_feature("continue-battle-button", threshold=self.threshold, time_out=30, raise_if_not_found=False, after_sleep=2):  # 未达到目标时点击继续战斗进入下一次排队。
                    self.log_error("没有找到继续战斗按钮，任务停止。")  # 记录无法进入下一场战斗的原因。
                    return  # 无法继续战斗时安全结束任务。
            # outcome 为 sunk_continue 时击沉后已点击继续按钮回到排队界面，无需再点击继续战斗按钮，直接进入下一轮循环。

    def _prepare_and_join_first_battle(self):  # 在主界面完成首场战斗的全部准备动作。
        if not self.wait_click_feature("Pick-First-Ship", threshold=self.threshold, time_out=15, raise_if_not_found=False, after_sleep=1):  # 点击第一个舰船选择入口。
            return False  # 找不到舰船入口时报告准备失败。
        if not self.wait_click_feature("Select-Battle-Mode", threshold=self.threshold, time_out=15, raise_if_not_found=False, after_sleep=1):  # 打开战斗模式选择页面。
            return False  # 找不到战斗模式入口时报告准备失败。
        if not self.wait_click_feature("PVE-Battle", threshold=self.threshold, time_out=15, raise_if_not_found=False, after_sleep=2):  # 在模式页面选择 PVE 战斗。
            return False  # 找不到 PVE 模式时报告准备失败。
        if not self._return_to_main():  # 确认模式选择完成后已经回到主界面。
            return False  # 无法回到主界面时报告准备失败。
        if not self.wait_click_feature("Addon-Selector", threshold=self.threshold, time_out=15, raise_if_not_found=False, after_sleep=1):  # 打开加成选择页面。
            return False  # 找不到加成入口时报告准备失败。
        if not self._remove_optional_item("Remove-All-Buff", ("Remove-All-Buff", "Install-Best-Buff")):  # 如果当前装备了加成则全部卸载。
            return False  # 无法识别加成页面时报告准备失败。
        if not self._return_to_main():  # 从加成页面返回主界面。
            return False  # 无法回到主界面时报告准备失败。
        if not self.wait_click_feature("Equipment", threshold=self.threshold, time_out=15, raise_if_not_found=False, after_sleep=1):  # 打开旗子装备页面。
            return False  # 找不到装备入口时报告准备失败。
        if not self._remove_optional_item("Remove-All-Flag", ("Remove-All-Flag", "Install-Recommended-Flag")):  # 如果当前装备了旗子则全部卸载。
            return False  # 无法识别旗子页面时报告准备失败。
        if not self._return_to_main():  # 从装备页面返回主界面。
            return False  # 无法回到主界面时报告准备失败。
        return self.wait_click_feature("Join-Battle", threshold=self.threshold, time_out=15, raise_if_not_found=False, after_sleep=2)  # 点击加入战斗并返回操作结果。

    def _remove_optional_item(self, remove_feature, page_features):  # 在加成或旗子页面按当前状态决定是否卸载。
        page_feature = self.wait_feature(list(page_features), threshold=self.threshold, time_out=15, raise_if_not_found=False)  # 等待任一页面状态元素出现。
        if page_feature is None:  # 检查页面状态是否成功识别。
            return False  # 页面无法识别时报告失败以避免误点击。
        if page_feature.name == remove_feature:  # 仅在卸载按钮存在时执行点击。
            self.click(page_feature, after_sleep=1)  # 点击识别到的卸载按钮并等待页面更新。
        return True  # 页面已识别且可选卸载动作已处理完成。

    def _return_to_main(self, max_attempts=8):  # 按工作流使用 ESC 逐层返回并关闭最外层菜单。
        for _ in range(max_attempts):  # 限制返回次数以避免在异常界面无限循环。
            scene = self._detect_scene()  # 识别当前截图对应的界面。
            if scene == "main":  # 主界面同时包含加入战斗和模式选择两个特有元素。
                return True  # 已回到主界面时完成返回流程。
            self.send_key("esc", after_sleep=1)  # 返回上一层；若是菜单页面则关闭菜单。
        return False  # 达到最大尝试次数仍未识别主界面时报告失败。

    def _run_until_result(self, completed_count, target_count):  # 进行一场战斗直到出现结算页面或舰船被击沉后完成处理。
        battle_initialized = False  # 标记当前战斗是否已经完成前进和地图导航初始化。
        battle_start_clicked_at = None  # 记录点击开始战斗按钮的时间以提供模板识别失败时的回退。
        unknown_since = None  # 记录连续无法识别界面的起始时间。
        while True:  # 持续轮询战斗状态直到结算或超时。
            scene = self._detect_scene()  # 使用当前最新截图判断所在界面。
            if scene != "unknown":  # 成功识别任一已知界面时清除未知计时。
                unknown_since = None  # 重置连续未知界面计时器。
            if scene == "result":  # 结算页包含继续战斗或返回港口按钮。
                return "result"  # 把结算页交回外层进行计数和续战判断。
            if scene == "menu":  # ESC 打开的菜单不属于工作流目标界面。
                self.send_key("esc", after_sleep=1)  # 再按一次 ESC 关闭最外层菜单。
                continue  # 关闭菜单后重新截图识别。
            if scene == "queue":  # 排队页面只需要等待系统匹配战斗。
                self.sleep(2)  # 等待两秒后再检查排队状态。
                continue  # 排队期间不执行任何游戏操作。
            if scene == "leave_battle":  # 舰船被击沉后出现离开战斗入口时立即停止开火并处理击沉页面。
                return self._handle_sunk_battle(completed_count, target_count)  # 按 ESC 识别离开页面后按剩余场数继续战斗或确认离开。
            if scene == "main":  # 加入战斗后仍停在主界面时视为按钮未成功生效。
                self.wait_click_feature("Join-Battle", threshold=self.threshold, time_out=10, raise_if_not_found=False, after_sleep=2)  # 再次点击加入战斗以恢复流程。
                continue  # 点击后重新截图识别游戏状态。
            if scene in ("battle_mode", "addon", "equipment"):  # 意外停留在准备子页面时按通用返回规则处理。
                self.send_key("esc", after_sleep=1)  # 按 ESC 返回上一层页面。
                continue  # 返回后重新截图识别游戏状态。
            if scene == "battle_start":  # 等待战斗开始页面出现开始按钮。
                if self.wait_click_feature("start-battle-button", threshold=self.threshold, time_out=10, raise_if_not_found=False, after_sleep=2):  # 点击开始战斗按钮进入战斗界面。
                    battle_start_clicked_at = time.monotonic()  # 保存成功点击时间用于等待战斗资源加载。
                continue  # 点击后重新截图识别游戏状态。
            delayed_battle_ready = battle_start_clicked_at is not None and time.monotonic() - battle_start_clicked_at >= 30 and scene == "unknown"  # 点击开始三十秒后允许从未知画面回退判定为战斗已加载。
            if (scene == "battle" or delayed_battle_ready) and not battle_initialized:  # 首次进入战斗界面或达到加载回退时间时执行航行初始化。
                self._initialize_battle_navigation()  # 连按前进键并进入地图完成航点选择。
                battle_initialized = True  # 确保同一场战斗只初始化一次航行路线。
                continue  # 回到战斗界面后重新识别状态。
            if scene == "map":  # 处理可能已经打开但尚未完成选择的地图页面。
                if battle_initialized:  # 已经选过航点却仍停留在地图时只处理关闭动作。
                    self._close_map()  # 避免重复点击地图目标并尝试可靠返回战斗界面。
                else:  # 尚未完成本场航行初始化时正常选择一次航点。
                    self._handle_map()  # 根据舰船光标和区域距离选择目标航点。
                    battle_initialized = True  # 地图处理完成后视为本场已初始化。
                continue  # 返回战斗界面后重新识别状态。
            if scene == "battle" or (scene == "unknown" and battle_initialized):  # 初始化后把动态 HUD 无法匹配的未知画面也视为战斗过程。
                self.click_relative(0.5, 0.5, move=False, name="battle_fire")  # 在屏幕中心发送一次鼠标左键点击。
                self.sleep(random.uniform(1, 5))  # 按工作流随机等待一到五秒后再次开火。
                continue  # 继续检查战斗是否结束。
            if unknown_since is None:  # 第一次进入无法识别的过渡画面时开始计时。
                unknown_since = time.monotonic()  # 保存单调时钟时间以避免系统时间变化影响。
            elif time.monotonic() - unknown_since >= 60:  # 连续一分钟无法识别任何界面时判定异常。
                return "error"  # 报告战斗流程超时并交由外层停止任务。
            self.sleep(1)  # 对加载画面和短暂动画留出一秒缓冲。

    def _handle_sunk_battle(self, completed_count, target_count):  # 舰船被击沉后停止开火并按已完成场数决定继续战斗或离开。
        self.log_info("舰船被击沉，已停止鼠标左键开火，准备离开当前战斗。")  # 记录已离开开火分支并停止左键点击。
        self.send_key("esc", after_sleep=1)  # 按 ESC 打开离开战斗确认界面。
        leaving_feature = self.wait_feature("Leaving-Battle", threshold=self.threshold, time_out=10, raise_if_not_found=False)  # 等待识别离开战斗确认界面元素。
        if leaving_feature is None:  # 离开确认界面没有出现时报告失败以避免误点击。
            self.log_error("没有找到离开战斗确认界面。")  # 记录无法进入击沉处理决策的原因。
            return "error"  # 无法识别离开界面时停止流程。
        if completed_count + 1 < target_count:  # 把被击沉的本场计入后仍未达到目标场数时继续下一场战斗。
            if not self.wait_click_feature("Continue-Battle-Button-After-Sunk", threshold=self.threshold, time_out=10, raise_if_not_found=False, after_sleep=2):  # 点击击沉后的继续战斗按钮回到排队或开战界面。
                self.log_error("没有找到击沉后的继续战斗按钮。")  # 记录无法继续下一场战斗的原因。
                return "error"  # 无法继续战斗时停止流程。
            return "sunk_continue"  # 已回到排队界面并交由外层把本场计入后重新开始下一场。
        if not self.wait_click_feature("Confirm-Leaving-Battle", threshold=self.threshold, time_out=10, raise_if_not_found=False, after_sleep=3):  # 场数已达标时点击确认离开按钮返回港口。
            self.log_error("没有找到确认离开战斗按钮。")  # 记录无法确认离开当前战斗的原因。
            return "error"  # 无法确认离开时停止流程。
        return "sunk_left"  # 已确认离开并交由外层把本场计入后结束任务。

    def _initialize_battle_navigation(self):  # 在战斗开始时完成前进输入并打开地图。
        for _ in range(10):  # 按工作流向游戏发送十次前进键。
            self.send_key("w", after_sleep=0.05)  # 短按一次 W 键并留出极短输入间隔。
        self.send_key("m", after_sleep=2)  # 按 M 键打开地图模式并等待地图绘制。
        self._handle_map()  # 在地图上选择最近区域、敌方基地或地图另一侧。

    def _handle_map(self):  # 在大地图范围内按区域、基地和对侧位置的优先级选择航点。
        map_anchor = self.wait_until(self._map_is_visible, time_out=15, raise_if_not_found=False)  # 等待同一帧同时出现舰船铭牌和大地图教程元素。
        if map_anchor is None:  # 检查 M 键是否成功打开了大地图。
            self.log_warning("没有识别到大地图锚点，跳过本次地图选点。")  # 记录地图未成功打开或仍处于加载中的情况。
            return False  # 未确认大地图时不发送 ESC 以免误开战斗菜单。
        self.next_frame()  # 获取同一时刻的新截图供全部地图元素共同判断。
        map_overview = self.get_box_by_name("Map-Overview")  # 使用十九号截图标注的矩形确定主地图实际边界。
        ship_cursor = self._find_rotated_ship_cursor(map_overview)  # 仅在主地图内旋转匹配当前舰船光标以排除右下角小地图。
        target_areas = []  # 收集主地图内实际识别到且不是绿色的占领区匹配框及其颜色。
        for area_name in ("Area-A", "Area-B", "Area-C", "Area-D"):  # 逐个识别四个字母及其绿色、红色或灰色状态。
            area_box, area_color = self._find_area(area_name, map_overview)  # 同时取得当前字母的最佳匹配框和颜色。
            if area_box is not None and area_color in ("gray", "red"):  # 仅把可占领的灰色或敌方红色区域作为导航候选。
                target_areas.append((area_box, area_color))  # 保存匹配框和颜色供选点及日志共同使用。
        enemy_base = self.find_one("Enemy-Base", threshold=self.threshold, box=map_overview)  # 查找没有占领区时可以使用的敌方基地航点。
        if ship_cursor is not None and target_areas:  # 舰船位置和至少一个非绿色占领区存在时计算最近目标。
            nearest_area, nearest_color = min(target_areas, key=lambda area: ship_cursor.center_distance(area[0]))  # 用元素中心点距离选出最近的灰色或红色区域并保留其颜色。
            self.log_info(f"选择最近占领区 {nearest_area.name}，颜色为 {nearest_color}。")  # 记录最终选中的字母和识别颜色以便核对导航判断。
            self.click(nearest_area, after_sleep=1)  # 点击距离舰船光标最近的区域。
        elif enemy_base is not None:  # 没有可选择的占领区但识别到敌方基地时直接进攻基地。
            self.click(enemy_base, after_sleep=1)  # 点击识别到的敌方基地作为航点。
        elif ship_cursor is not None:  # 没有识别到占领区或敌方基地时根据舰船位置选择地图另一侧。
            cursor_x, cursor_y = ship_cursor.center()  # 读取当前舰船在主地图中的中心坐标。
            opposite_x = map_overview.x + map_overview.width - (cursor_x - map_overview.x)  # 以主地图中心为轴把舰船水平位置映射到另一侧。
            opposite_y = map_overview.y + map_overview.height - (cursor_y - map_overview.y)  # 以主地图中心为轴把舰船垂直位置映射到另一侧。
            self.click(opposite_x, opposite_y, name="opposite-map-side", after_sleep=1)  # 点击中心对称点，使下方去上方、左上去右下。
        else:  # 舰船光标也缺失时无法可靠判断地图的另一侧。
            self.log_warning("没有识别到舰船光标、占领区或敌方基地，跳过本次地图选点。")  # 避免在无法确定当前位置时误点地图。
        self._close_map()  # 关闭大地图并在 ESC 未生效时使用地图切换键兜底。
        return True  # 报告本次大地图已经成功识别并关闭。

    def _find_area(self, area_name, search_box=None):  # 在指定范围内识别占领区字母并同时返回它当前显示的颜色。
        area_feature = self.get_feature_by_name(area_name)  # 取得该字母正式标注生成的原始模板。
        if area_feature is None:  # 检查字母模板资源是否成功加载。
            return None, None  # 缺少模板时明确返回未识别到匹配框和颜色。
        if search_box is None:  # 独立调用没有传入范围时仍限制在正式主地图区域内搜索。
            search_box = self.get_box_by_name("Map-Overview")  # 从正式标注读取可随截图分辨率缩放的主地图边界。
        color_matches = []  # 收集三种颜色中达到正式阈值的匹配结果。
        for color_name, (hue, saturation) in self.AREA_COLOR_HSV.items():  # 分别生成绿色、红色和灰色模板进行完整比较。
            color_template = self._colorize_area_template(area_feature.mat, hue, saturation)  # 保留字母明暗结构并替换成当前候选颜色。
            color_box = self.find_one(area_name, threshold=self.threshold, box=search_box, template=color_template)  # 使用框架原生模板参数匹配当前颜色变体。
            if color_box is not None:  # 仅收集达到正式模板阈值的候选颜色。
                color_matches.append((color_box, color_name))  # 保存候选框和对应颜色供最终按置信度排序。
        return max(color_matches, key=lambda item: item[0].confidence, default=(None, None))  # 返回三种颜色中的最高分匹配框和颜色。

    @staticmethod  # 颜色转换只依赖原始模板与目标 HSV 参数。
    def _colorize_area_template(template, hue, saturation):  # 把占领区字母模板转换成指定颜色并保留原始亮度细节。
        template_hsv = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)  # 将 BGR 模板转换为便于独立修改颜色的 HSV 空间。
        color_hsv = template_hsv.copy()  # 复制模板以避免修改 FeatureSet 缓存中的正式原图。
        color_hsv[:, :, 0] = hue  # 将模板全部像素统一设置为目标色相。
        color_hsv[:, :, 1] = saturation  # 将模板全部像素统一设置为目标饱和度。
        return cv2.cvtColor(color_hsv, cv2.COLOR_HSV2BGR)  # 转回框架模板匹配需要的 BGR 图像。

    def _find_rotated_ship_cursor(self, search_box=None):  # 在指定主地图范围内旋转模板以识别不同朝向的舰船光标。
        cursor_feature = self.get_feature_by_name("My-Ship-Cursor")  # 取得正式标注生成的原始舰船光标模板。
        if cursor_feature is None:  # 检查模板资源是否成功加载。
            return None  # 缺少模板时交给其他地图目标或安全跳过逻辑处理。
        if search_box is None:  # 独立调用没有传入范围时仍使用正式主地图标注。
            search_box = self.get_box_by_name("Map-Overview")  # 从十九号截图标注读取可随分辨率缩放的主地图边界。
        cursor_threshold = min(self.threshold, 0.7)  # 旋转插值会降低相关系数，因此为光标使用更宽松的专用上限阈值。
        matches = []  # 收集所有达到阈值的旋转模板匹配结果。
        for angle in range(0, 360, 45):  # 每隔四十五度匹配一次，仅检查八个主要方向以缩短导航识别耗时。
            rotated_template = self._rotate_template(cursor_feature.mat, angle)  # 生成当前朝向且不裁切边角的光标模板。
            match = self.find_one("My-Ship-Cursor", threshold=cursor_threshold, box=search_box, template=rotated_template)  # 使用原始截图分辨率在完整主地图区域匹配当前旋转方向。
            if match is not None:  # 仅保留达到旋转光标专用阈值的候选结果。
                matches.append(match)  # 保存候选结果供最终比较置信度。
        return max(matches, key=lambda box: box.confidence, default=None)  # 返回全部旋转方向中置信度最高的唯一光标。

    @staticmethod  # 该旋转操作只依赖输入模板，不读取任务状态。
    def _rotate_template(template, angle):  # 在不裁切内容的前提下按指定角度旋转模板。
        if angle == 0:  # 零度方向无需插值处理。
            return template  # 直接复用原始模板以保留全部像素细节。
        height, width = template.shape[:2]  # 读取原始模板尺寸以计算旋转边界。
        center = (width / 2, height / 2)  # 使用模板中心作为旋转中心。
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)  # 创建不缩放的二维旋转矩阵。
        cosine = abs(matrix[0, 0])  # 取得旋转矩阵中的余弦绝对值。
        sine = abs(matrix[0, 1])  # 取得旋转矩阵中的正弦绝对值。
        rotated_width = int(math.ceil(height * sine + width * cosine))  # 计算容纳完整旋转模板的新宽度。
        rotated_height = int(math.ceil(height * cosine + width * sine))  # 计算容纳完整旋转模板的新高度。
        matrix[0, 2] += rotated_width / 2 - center[0]  # 将旋转后的模板水平移动到新画布中心。
        matrix[1, 2] += rotated_height / 2 - center[1]  # 将旋转后的模板垂直移动到新画布中心。
        edge_pixels = np.concatenate((template[0], template[-1], template[:, 0], template[:, -1]))  # 汇总模板四条边上的地图背景像素。
        border_color = tuple(int(channel) for channel in np.median(edge_pixels, axis=0))  # 使用边缘中位色填充旋转产生的空白角落。
        return cv2.warpAffine(template, matrix, (rotated_width, rotated_height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=border_color)  # 生成完整且背景连续的旋转模板。

    def _close_map(self):  # 关闭大地图并确认是否已经回到动态战斗画面。
        self.send_key("esc", after_sleep=2)  # 优先按工作流要求使用 ESC 返回战斗界面。
        self.next_frame()  # 获取按键生效后的最新截图用于确认大地图是否仍然可见。
        if self._map_is_visible():  # 只要大地图教程区域仍然存在就确认地图尚未关闭。
            self.log_warning("ESC 后大地图仍然可见，改用 M 键关闭地图。")  # 记录地图没有被 ESC 关闭的恢复动作。
            self.send_key("m", after_sleep=2)  # 使用地图模式切换键兜底返回战斗界面。

    def _detect_scene(self, refresh=True):  # 根据当前截图中的特有元素判断游戏所处界面。
        if refresh:  # 普通调用需要在判断场景前刷新截图。
            self.next_frame()  # 主动获取一张最新截图供本次场景识别使用。
        if self.find_one("Menu", threshold=self.threshold) is not None:  # 菜单元素具有最高优先级以便正确关闭菜单。
            return "menu"  # 返回菜单场景。
        if self._has_any(("continue-battle-button", "back-to-port-button")):  # 结算页包含两个可能出现的后续操作按钮。
            return "result"  # 返回战斗结算场景。
        if self.find_one("Leave-Battle", threshold=self.threshold) is not None:  # 击沉页面使用底部的离开战斗入口判断。
            return "leave_battle"  # 返回需要离开当前战斗的场景。
        if self.find_one("In-Battle-Queue", threshold=self.threshold) is not None:  # 排队页使用专用状态元素判断。
            return "queue"  # 返回战斗排队场景。
        if self.find_one("start-battle-button", threshold=self.threshold) is not None:  # 等待开战页使用开始按钮判断。
            return "battle_start"  # 返回等待战斗开始场景。
        battle_view = self._detect_battle_view()  # 使用舰船铭牌和教程元素组合区分大地图与普通战斗。
        if battle_view is not None:  # 只有舰船铭牌存在时组合判断才属于战斗生命周期页面。
            return battle_view  # 返回大地图或普通战斗场景。
        if self.find_one("In-Battle-Compass", threshold=self.threshold) is not None:  # 战斗界面使用罗盘元素判断。
            return "battle"  # 返回战斗场景。
        if self.find_one("PVE-Battle", threshold=self.threshold) is not None:  # 战斗模式选择页使用 PVE 模式元素判断。
            return "battle_mode"  # 返回战斗模式选择场景。
        if self._has_any(("Remove-All-Buff", "Install-Best-Buff")):  # 加成页根据装备或未装备状态按钮判断。
            return "addon"  # 返回加成选择场景。
        if self._has_any(("Remove-All-Flag", "Install-Recommended-Flag")):  # 旗子页根据装备或未装备状态按钮判断。
            return "equipment"  # 返回旗子装备场景。
        if self.find_one("Join-Battle", threshold=self.threshold) is not None and self.find_one("Select-Battle-Mode", threshold=self.threshold) is not None:  # 主界面必须同时存在两个特有元素以减少误判。
            return "main"  # 返回游戏主界面场景。
        return "unknown"  # 没有匹配到已知特有元素时返回未知场景。

    def _has_any(self, feature_names):  # 判断当前缓存截图中是否存在任一指定元素。
        return any(self.find_one(feature_name, threshold=self.threshold) is not None for feature_name in feature_names)  # 依次匹配并在发现首个元素时返回真。

    def _detect_battle_view(self):  # 使用同一帧中的舰船铭牌和教程元素区分两个战斗页面。
        nameplate_visible = self.find_one("Libertadad-Nameplate", threshold=self.threshold) is not None  # 检查两个页面都会出现的 Libertad 舰船铭牌。
        tutorial_visible = self.find_one("Map-Tutorial", threshold=self.threshold) is not None  # 检查仅在大地图出现的右侧教程区域。
        if not nameplate_visible and not tutorial_visible:  # 两个候选元素都不存在时说明当前并非需要区分的两个页面。
            return None  # 交给后续其他页面特征继续判断。
        return "map" if nameplate_visible and tutorial_visible else "battle"  # 铭牌与教程同时存在为大地图，否则为普通战斗。

    def _map_is_visible(self):  # 判断当前缓存截图是否同时包含大地图所需的两个元素。
        return self._detect_battle_view() == "map"  # 仅组合判断结果为地图时返回真。
