"""游戏文字元素的 OCR 规则；保留 COCO 坐标作为搜索区域，不做像素模板匹配。"""

import json  # 读取各比例现有标注的位置。
import re  # 规范空格、标点和英文大小写。
from functools import lru_cache  # 缓存只读标注，避免每次识别重复读取文件。
from pathlib import Path  # 从项目根目录解析资源路径。

from ok import Box  # 返回框架可直接点击及绘制的识别框。

from src.resolution_assets import coco_json_for_size  # 沿用当前分辨率的资源包选择。


OCR_TEXTS = {  # 仅替换用户确认的二十七个元素，英文文案同时作为候选。
    "Leave-Queue": ("离开队列", "Leave queue"),
    "Start-Battle": ("开始战斗", "Start battle"),
    "Back-To-Port": ("回到港口", "Back to port", "Return to port"),
    "Continue-Battle": ("继续战斗", "Battle on", "Continue battle"),
    "Equipment": ("装备", "Equipment"),
    "Join-Battle": ("加入战斗", "Battle", "To battle"),
    "Install-Best-Buff": ("安装最佳", "Mount best"),
    "Remove-All-Buff": ("全部移除", "Remove all"),
    "Select-Battle-Mode": ("更改战斗模式", "Change battle type", "Change battle mode"),
    "Install-Recommended-Flag": ("安装推荐", "Mount recommended"),
    "Remove-All-Flag": ("拆卸全部", "Demount all"),
    "PVE-Battle": ("联合作战", "Co-op battle", "Co-op battles"),
    "In-Battle-Queue": ("您已加入准备战斗的队列中", "You are in the queue for battle"),
    "Menu": ("菜单", "Menu"),
    "Leave-Battlefield": ("离开战斗", "Leave battle"),
    "Leave-Battle-Confirm": ("是", "Yes"),
    "Leave-Battle-Title": ("离开战斗", "Leave battle"),
    "Map-Tutorial": ("自动驾驶控制", "Autopilot controls"),
    "Continue-Battle-After-Sunk": ("继续战斗", "Battle on", "Continue battle"),
    "Claim-Reward": ("收集您的奖励", "Collect your reward", "Collect your rewards"),
    "Close-Reward-Screen": ("关闭", "Close"),
    "Login-Game": ("登录", "Log in", "Login"),
    "Control-Camera": ("镜头控制说明", "Camera controls"),
    "Asymmetry-Battle": ("非对称战斗", "Asymmetric battle", "Asymmetric battles"),
    "Confirm-Container": ("是", "Yes"),
    "Pick-Container": ("每日补给箱", "Daily containers", "Daily container"),
    "Container-Menu": ("补给箱", "Containers", "Container"),
}


def normalized(text):  # 完整文字匹配允许空白、大小写和标点差异，不使用单字模糊匹配。
    return re.sub(r"[\W_]+", "", text.casefold())


@lru_cache(maxsize=3)
def annotations(relative_path):  # 只加载坐标，不依赖模板图像内容。
    path = Path(__file__).resolve().parents[2] / relative_path
    if not path.is_file():  # 缺少该比例标注时不猜测位置。
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    names = {item["id"]: item["name"] for item in data["categories"]}
    images = {item["id"]: item for item in data["images"]}
    return {names[item["category_id"]]: (item["bbox"], images[item["image_id"]])
            for item in data["annotations"]}


def annotated_box(name, frame):  # 按实际传入截图缩放标注，支持原尺寸与半尺寸。
    height, width = frame.shape[:2]
    entry = annotations(coco_json_for_size(width, height)).get(name)
    if entry is None:
        return None
    (x, y, w, h), image = entry
    sx, sy = width / image["width"], height / image["height"]
    return Box(x * sx, y * sy, w * sx, h * sy, name=name)


def clipped_box(frame, left, top, right, bottom):  # 所有 OCR 区域先裁到画面内，避免负数切片。
    height, width = frame.shape[:2]
    left, top = max(0, round(left)), max(0, round(top))
    right, bottom = min(width, round(right)), min(height, round(bottom))
    return Box(left, top, right - left, bottom - top) if right > left and bottom > top else None


def search_box(name, frame):  # 采用实测过的邻近扩展范围，保留上下文文字。
    feature = annotated_box(name, frame)
    if feature is None:
        return None
    height, width = frame.shape[:2]
    dx, dy = max(width * .035, feature.width * .35), max(height * .025, feature.height * .5)
    if name in ("Continue-Battle", "Continue-Battle-After-Sunk"):
        dx, dy = feature.width * 1.5, feature.height * 1.5  # 同名按钮仍使用原有四倍局部范围。
    right = feature.x + feature.width + dx
    if name == "Control-Camera":
        right += width * .05  # F1 右侧需要容纳完整的“镜头控制说明”。
    return clipped_box(frame, feature.x - dx, feature.y - dy, right, feature.y + feature.height + dy)


def read_text(task, frame, region):  # 通过框架 OCR 处理繁简转换和坐标恢复，不刷新截图。
    if region is None:
        return []
    return task.ocr(box=region, frame=frame, threshold=.5)


def find_text(task, name, frame, threshold, box=None):  # 将文字匹配结果转换回原元素名，兼容等待和点击流程。
    region = box or search_box(name, frame)
    if region is None:
        return None
    region = clipped_box(frame, region.x, region.y, region.x + region.width, region.y + region.height)
    if region is None:
        return None
    accepted = {normalized(text) for text in OCR_TEXTS[name]}
    matches = [item for item in read_text(task, frame, region)
               if item.confidence >= threshold and
               (normalized(item.name) in accepted or
                (name == "Control-Camera" and any(text in normalized(item.name) for text in accepted)))]  # F1 可能与完整提示合成同一行，仅该状态提示允许包含匹配。
    if len(matches) != 1:  # 同一区域存在多个同名文字时不选择可能错误的点击目标。
        return None
    result = matches[0]
    return Box(result.x, result.y, result.width, result.height, confidence=result.confidence, name=name)


def find_ocr_feature(task, name, frame, threshold=0, box=None):  # 对同文案按钮添加同一帧中的场景约束。
    if frame is None or annotated_box(name, frame) is None:
        return None
    threshold = threshold if threshold else task.threshold
    context_threshold = max(.8, threshold)  # 诊断的低阈值不能绕过确认弹窗的上下文检查。
    if name in ("Leave-Battle-Confirm", "Continue-Battle-After-Sunk"):
        if find_text(task, "Leave-Battle-Title", frame, context_threshold) is None:
            return None
    elif name == "Continue-Battle":
        if find_text(task, "Leave-Battle-Title", frame, context_threshold) is not None:
            return None
        if find_text(task, "Back-To-Port", frame, context_threshold) is None:
            return None
    elif name == "Confirm-Container":
        if find_text(task, "Leave-Battle-Title", frame, context_threshold) is not None:
            return None
        feature = annotated_box(name, frame)
        height, width = frame.shape[:2]
        context = clipped_box(frame, feature.x - width * .09, feature.y - height * .17,
                              feature.x + feature.width + width * .09, feature.y + feature.height + height * .03)
        if not any(item.confidence >= context_threshold and
                   ("补给箱" in item.name or "container" in item.name.casefold())
                   for item in read_text(task, frame, context)):
            return None
    if name in ("PVE-Battle", "Asymmetry-Battle"):
        if (find_text(task, "Join-Battle", frame, context_threshold) is not None and
                find_text(task, "Select-Battle-Mode", frame, context_threshold) is not None):
            return None  # 港口顶部当前模式同名文字不属于模式选择按钮。
        if box is None:
            match = find_text(task, name, frame, threshold)
            if match is not None:
                return match
            height, width = frame.shape[:2]
            for top in range(0, height, max(1, round(height / 4))):  # 分块搜索保持小字清晰，并兼容模式按钮换位。
                for left in range(0, width, max(1, round(width / 4))):
                    region = clipped_box(frame, left - width * .025, top - height * .025,
                                         left + width * .275, top + height * .275)
                    match = find_text(task, name, frame, threshold, region)
                    if match is not None:
                        return match
            return None
    return find_text(task, name, frame, threshold, box)
