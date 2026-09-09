import re

from ok import BaseTask
from src.window_focus import focus_window, is_window_focused

class MyBaseTask(BaseTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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




