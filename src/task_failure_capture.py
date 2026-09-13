"""在框架禁用报错任务前持久保存现场，覆盖内置和自定义任务。"""

import re  # 清理任务名称中的 Windows 文件名特殊字符。
import sys  # 获取框架异常处理分支正在处理的原始异常。
from datetime import datetime  # 按日期归档并记录错误发生时间。
from functools import wraps  # 保留框架方法的名称及签名信息。
from pathlib import Path  # 使用支持中文的文件路径。
from uuid import uuid4  # 避免同名任务短时间重复失败时覆盖截图。

import cv2  # 无损编码 PNG，不经过会被清理的调试截图目录。
import numpy as np  # 检查捕获结果是否为有效画面。
from ok import BaseTask, Logger  # 在项目内安装框架任务统一退出钩子。
from ok.task.exceptions import FinishedException, TaskDisabledException  # 正常结束和用户停止不属于错误退出。


logger = Logger.get_logger(__name__)
FAILURE_DIRECTORY = Path(__file__).resolve().parents[1] / "logs" / "task_failures"


def valid_frame(frame):  # 空画面不能编码为有效的故障截图。
    return isinstance(frame, np.ndarray) and frame.size > 0 and frame.ndim in (2, 3)


def save_failure_screenshot(task, reason, *, frame=None, directory=None, label=None):  # 截图失败只能记录警告，不能覆盖原始任务错误。
    try:
        executor = task.executor
        if frame is None:  # 特定按钮故障可传入已经确认的错误帧，统一出口则采集当前画面。
            cached = executor.nullable_frame()  # 直接读取已有帧，不走暂停等待或重新采集循环。
            try:
                method = executor.method
                if method is not None:
                    frame = method.get_frame()  # 只尝试一次当前游戏截图，不发送输入、不等待任务重新启用。
            except Exception as error:
                logger.warning(f"获取错误现场失败，尝试保存缓存帧：{error}")
            if not valid_frame(frame):
                frame = cached  # 游戏窗口或捕获器失效时保留最后可用画面。
        if not valid_frame(frame):
            logger.warning(f"任务错误截图未保存：{task.name} 没有可用的游戏画面；错误：{reason}")
            return None
        timestamp = datetime.now()
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(label or task.name)).strip(" .")[:80] or "task"
        path = Path(directory or FAILURE_DIRECTORY) / timestamp.strftime("%Y-%m-%d") / f"{timestamp:%H-%M-%S-%f}_{name}_{uuid4().hex[:8]}.png"
        encoded, data = cv2.imencode(".png", frame)  # 保存原始像素，不缩放或叠加识别框。
        if not encoded:
            raise ValueError("PNG 编码失败")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:  # 唯一命名之外再禁止覆盖已有文件。
            stream.write(data.tobytes())
        if executor.current_task is task:
            task._persistent_failure_capture_run = task.start_time  # 专用按钮已保存现场时，退出钩子不再重复保存。
        logger.info(f"任务错误截图已保存：{path}；错误：{reason}")
        return path
    except Exception as error:
        logger.warning(f"保存任务错误截图失败：{error}；原始错误：{reason}")
        return None


def install_failure_capture():  # 复用框架统一 disable 出口，避免每个任务及返回分支单独加截图。
    original = BaseTask.disable
    if getattr(original, "_persistent_failure_capture", False):
        return  # 配置重复加载时只安装一次。

    @wraps(original)
    def disable(task, *args, **kwargs):
        error = sys.exception()  # execute 的 except 分支调用 disable 时，异常仍处于活动状态。
        try:
            executor = task.executor
            already_saved = task.__dict__.get("_persistent_failure_capture_run", object()) == task.start_time
            if executor.current_task is task and executor.is_executor_thread() and not already_saved:  # 仅处理执行线程的任务退出，不把 UI 手动停止当成错误。
                if error is not None and not isinstance(error, (FinishedException, TaskDisabledException)):
                    save_failure_screenshot(task, str(error))  # 包括 run 之前首次采集失败的异常。
                elif error is None and task.running and task.info.get("Error"):
                    save_failure_screenshot(task, str(task.info["Error"]))  # log_error 后正常 return 也会经过此出口。
        except Exception as capture_error:
            logger.warning(f"检查任务错误截图失败：{capture_error}")
        return original(task, *args, **kwargs)  # 无论截图是否成功，原来的停止和错误报告流程都继续执行。

    disable._persistent_failure_capture = True
    BaseTask.disable = disable
