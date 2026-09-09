"""Bind ok-script's Pynput input to the exact UU screenshot coordinates."""

from dataclasses import dataclass

import win32gui
from ok.device.interaction_methods.pynput import PynputInteraction
from src.window_focus import is_window_focused


@dataclass(frozen=True)
class UUInputTarget:
    hwnd: int
    rect: tuple

    def is_foreground(self):
        return is_window_focused(self.hwnd) and win32gui.GetWindowRect(self.hwnd) == self.rect

    def get_abs_cords(self, x, y):
        if not self.is_foreground():
            raise RuntimeError('UU 窗口已移动或失去焦点，取消 Pynput 点击。')
        return round(self.rect[0] + x), round(self.rect[1] + y)


def click_uu(hwnd, rect, point):
    target = UUInputTarget(hwnd, rect)
    if not target.is_foreground():
        raise RuntimeError('UU 窗口未获得焦点，取消 Pynput 点击。')
    interaction = PynputInteraction(target, target)
    interaction.click(x=point[0], y=point[1], key='left', move_back=False, down_time=0.05)
