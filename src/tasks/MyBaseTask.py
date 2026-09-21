import re
from functools import wraps

from ok import BaseTask
from src.window_focus import focus_window, is_window_focused
from src.interaction_config import BUTTON_WAIT, DEFAULT_BUTTON_WAIT, interaction_options, validate_interaction_config


def preserve_input_timing(method):  # 战斗操作暂时沿用原始等待，返回或异常后恢复全局菜单等待。
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        previous = self._preserve_input_timing
        self._preserve_input_timing = True
        try:
            return method(self, *args, **kwargs)
        finally:
            self._preserve_input_timing = previous
    return wrapped


class MyBaseTask(BaseTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._preserve_input_timing = False

    def _input_wait(self, after_sleep):  # 每次读取全局设置，修改后对所有任务的后续操作生效。
        if self._preserve_input_timing:
            return after_sleep  # 不改变战斗开火、技能、连续前进键和地图操作的原始节奏。
        value = self.get_global_config(interaction_options).get(BUTTON_WAIT, DEFAULT_BUTTON_WAIT)
        if not validate_interaction_config(BUTTON_WAIT, value)[0]:
            value = DEFAULT_BUTTON_WAIT  # 无效的旧配置使用默认值，避免操作过快或永久等待。
        return max(after_sleep, float(value))  # 保留原有更长的等待，避免重复叠加。

    def click(self, x=-1, y=-1, move_back=False, name=None, interval=-1, move=True,
              down_time=0.02, after_sleep=0, key='left', hcenter=False, vcenter=False):
        return super().click(x, y, move_back=move_back, name=name, interval=interval, move=move,
                             down_time=down_time, after_sleep=self._input_wait(after_sleep), key=key,
                             hcenter=hcenter, vcenter=vcenter)  # 相对坐标、识图点击和左右键最终共用此入口。

    def send_key(self, key, down_time=0.02, interval=-1, after_sleep=0):
        return super().send_key(key, down_time=down_time, interval=interval,
                                after_sleep=self._input_wait(after_sleep))  # 完成按键后等待，不改变按住时长。

    def send_key_up(self, key, after_sleep=0):
        return super().send_key_up(key, after_sleep=self._input_wait(after_sleep))  # 组合键在释放后等待，按下时不额外延长持键。

    def mouse_up(self, name=None, key="left"):
        result = super().mouse_up(name=name, key=key)
        delay = self._input_wait(0)
        if delay > 0:
            self.sleep(delay)  # 拖拽等手动按住操作在释放鼠标后等待。
        return result

    def back(self, *args, after_sleep=0, **kwargs):
        return super().back(*args, after_sleep=self._input_wait(after_sleep), **kwargs)

    def ensure_in_front(self):  # 在启动阶段确认游戏真正获得焦点，不忽略激活失败。
        for _ in range(3):  # 对启动界面抢焦点或窗口切换给予有限重试。
            window = self.hwnd  # 使用框架绑定的游戏窗口，不按标题猜测其他窗口。
            if window is None:  # 尚未绑定游戏时不能继续发送输入。
                return False  # 交给调用方显示启动失败。
            hwnd = window.top_hwnd or window.hwnd  # 优先激活游戏顶层窗口。
            if not hwnd:  # 窗口句柄尚未刷新时通过框架重新查找。
                window.do_update_window_size()  # 刷新已绑定游戏的窗口信息。
                hwnd = window.top_hwnd or window.hwnd  # 读取刷新后的顶层句柄。
            if focus_window(hwnd):  # 尝试恢复最小化窗口并切换前台。
                self.sleep(0.2)  # 等待启动界面事件处理结束，避免短暂激活后立刻失焦。
                if is_window_focused(hwnd):  # 再次向 Windows 确认实际前台窗口。
                    return True  # 焦点稳定后才允许开始截图与操作。
            else:  # 激活没有生效时让出短暂时间后重试。
                self.sleep(0.2)  # 使用框架等待以响应用户停止任务。
        return False  # 重试结束仍未获得焦点时明确报告失败。




