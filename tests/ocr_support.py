"""为离线截图测试连接与应用相同的 OCR，不接触游戏窗口。"""

import logging
from functools import lru_cache

from onnxocr.onnx_paddleocr import ONNXPaddleOcr


@lru_cache(maxsize=1)
def engine():
    return ONNXPaddleOcr(use_angle_cls=False, use_openvino=True, use_npu=True,
                         logger=logging.getLogger("ocr_tests"))


def bind_ocr(executor):
    executor.paused = False
    executor.config = {"ocr": {"default": {"lib": "onnxocr"}, "auto_simplify": True}}
    executor.ocr_lib.side_effect = lambda name="default": engine()
    executor.ocr_po_translation = None
    executor.text_fix = {}
    executor.locale = "zh_CN"
