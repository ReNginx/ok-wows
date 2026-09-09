"""Activate the selected game window from the task worker thread."""

import logging

import win32api
import win32con
import win32gui
import win32process


logger = logging.getLogger(__name__)


def is_window_focused(hwnd):
    return bool(hwnd and win32gui.IsWindow(hwnd) and not win32gui.IsIconic(hwnd)
                and win32gui.IsWindowVisible(hwnd) and win32gui.GetForegroundWindow() == hwnd)


def focus_window(hwnd):
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    if is_window_focused(hwnd):
        return True
    attached = []
    current_thread = win32api.GetCurrentThreadId()
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        elif not win32gui.IsWindowVisible(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        except win32gui.error:
            pass
        if is_window_focused(hwnd):
            return True

        # Share input queues only during activation, then detach even on failure.
        foreground = win32gui.GetForegroundWindow()
        threads = {win32process.GetWindowThreadProcessId(window)[0]
                   for window in (foreground, hwnd) if window}
        for thread in sorted(threads - {current_thread}):
            win32process.AttachThreadInput(current_thread, thread, True)
            attached.append(thread)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        win32gui.SetFocus(hwnd)
        return is_window_focused(hwnd)
    except win32gui.error as error:
        logger.warning("Could not focus window %s: %s", hwnd, error)
        return False
    finally:
        for thread in reversed(attached):
            try:
                win32process.AttachThreadInput(current_thread, thread, False)
            except win32gui.error as error:
                logger.warning("Could not detach input thread %s: %s", thread, error)
