"""覆盖 OCR 迁移的截图命中、错误页面拒绝和等待点击兼容性。"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from ok import Box, FeatureSet

from src.config import config, make_bottom_right_black
from src.tasks.AutoPveBattleTask import AutoPveBattleTask
from src.tasks.MyBaseTask import MyBaseTask
from src.tasks.feature_ocr import OCR_TEXTS, SHIP_NAME_FEATURES, annotated_box, find_text, search_box
from tests.ocr_support import bind_ocr


class TestFeatureOCR(unittest.TestCase):
    def setUp(self):
        self.executor = MagicMock()
        self.executor.scene = None
        self.executor.frame = np.zeros((1080, 2560, 3), dtype=np.uint8)
        self.task = AutoPveBattleTask(self.executor, None)
        self.task.config = dict(self.task.default_config)

    def test_ocr_never_falls_back_to_template_on_miss(self):
        with patch.object(self.task, "ocr", return_value=[]), patch.object(MyBaseTask, "find_one") as template:
            for name in OCR_TEXTS:
                with self.subTest(name=name):
                    self.assertIsNone(self.task.find_one(name))
        template.assert_not_called()

    def test_unselected_features_keep_template_recognition(self):
        names = ("Addon-Selector", "In-Battle-Compass", "Map-M-Button", "Map-B-Button", "Enemy-Base")
        with patch.object(self.task, "ocr") as ocr, patch.object(MyBaseTask, "find_one", return_value=None) as template:
            for name in names:
                self.task.find_one(name)
        ocr.assert_not_called()
        self.assertEqual(list(names), [c.kwargs.get("feature_name", c.args[0]) for c in template.call_args_list])

    def test_list_wait_click_routes_ocr_and_preserves_feature_name(self):
        frame = self.executor.frame
        region = search_box("Remove-All-Buff", frame)
        result = Box(region.x + 40, region.y + 30, 65, 20, .99, "全部移除")
        with patch.object(self.task, "ocr", return_value=[result]), \
                patch.object(self.task, "wait_until", side_effect=lambda predicate, **kw: predicate()), \
                patch.object(self.task, "click_box") as click:
            self.assertTrue(self.task.wait_click_feature(["Remove-All-Buff", "Install-Best-Buff"], threshold=.8))
        self.assertEqual("Remove-All-Buff", click.call_args.args[0].name)
        self.assertEqual(result.center(), click.call_args.args[0].center())
        self.assertEqual("全部移除", result.name)  # 不修改引擎返回的原始文本。

    def test_exact_matching_rejects_noisy_yes_duplicate_and_low_confidence(self):
        for results in ([Box(10, 20, 20, 10, .99, "是否")],
                        [Box(10, 20, 20, 10, .7, "是")],
                        [Box(10, 20, 20, 10, .99, "是"), Box(40, 20, 20, 10, .99, "是")]):
            with self.subTest(results=results), patch.object(self.task, "ocr", return_value=results):
                self.assertIsNone(find_text(self.task, "Leave-Battle-Confirm", self.executor.frame, .8))

    def test_title_required_even_for_explicit_region_and_diagnostic_threshold(self):
        with patch.object(self.task, "ocr", return_value=[Box(10, 20, 20, 10, .99, "是")]):
            for name in ("Leave-Battle-Confirm", "Confirm-Container", "Continue-Battle-After-Sunk", "Continue-Battle"):
                self.assertIsNone(self.task.find_one(name, box=Box(0, 0, 2560, 1080), threshold=-1))

    def test_explicit_frame_and_out_of_bounds_region(self):
        frame = np.zeros((2160, 5120, 3), dtype=np.uint8)
        with patch.object(self.task, "ocr", return_value=[]) as ocr:
            self.task.find_one("Join-Battle", frame=frame, box=Box(-10, -20, 100, 100))
            self.assertIs(frame, ocr.call_args.kwargs["frame"])
            region = ocr.call_args.kwargs["box"]
            self.assertEqual((0, 0, 90, 80), (region.x, region.y, region.width, region.height))
            ocr.reset_mock()
            self.task.find_one("Join-Battle", frame=frame, box=Box(6000, 3000, 10, 10))
            ocr.assert_not_called()

    def test_english_and_punctuation_variants(self):
        with patch.object(self.task, "ocr", return_value=[Box(1200, 100, 100, 30, .99, "  TO BATTLE!  ")]):
            self.assertIsNotNone(self.task.find_one("Join-Battle"))

    def bind_frame(self, frame):
        bind_ocr(self.executor)
        matching = config["template_matching"]
        self.executor.feature_set = FeatureSet(False, matching["coco_feature_json"], .002, .002)
        self.executor.frame = frame
        self.executor.method.width = frame.shape[1]
        self.executor.method.height = frame.shape[0]

    @unittest.skipUnless(Path("ok_templates/21x9/coco_annotations.json").is_file(), "Local reference screenshots unavailable")
    def test_all_27_features_on_native_and_half_size_screens(self):
        root = Path("ok_templates/21x9")
        data = json.loads((root / "coco_annotations.json").read_text(encoding="utf-8"))
        names = {c["id"]: c["name"] for c in data["categories"]}
        images = {i["id"]: i for i in data["images"]}
        tested = set()
        for annotation in data["annotations"]:
            name = names[annotation["category_id"]]
            if name not in OCR_TEXTS or name in SHIP_NAME_FEATURES:  # 舰名迁移另用原始尺寸测试，不加入缩放用例。
                continue
            frame = make_bottom_right_black(cv2.imread(str(root / images[annotation["image_id"]]["file_name"])))
            for scale in (1, .5):
                with self.subTest(name=name, scale=scale):
                    resized = frame if scale == 1 else cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                    self.bind_frame(resized)
                    with patch.object(MyBaseTask, "find_one", side_effect=AssertionError("OCR must not call template matching")):
                        match = self.task.find_one(name, threshold=.8)
                    self.assertIsNotNone(match)
                    self.assertEqual(name, match.name)
                    # 文字按钮的点击中心仍在原按钮内；两个状态提示使用图标旁文字。
                    if name not in ("Control-Camera", "Leave-Battlefield"):
                        target = annotated_box(name, resized)
                        cx, cy = match.center()
                        self.assertTrue(target.x <= cx <= target.x + target.width)
                        self.assertTrue(target.y <= cy <= target.y + target.height)
            tested.add(name)
        self.assertEqual(27, len(tested))

    @unittest.skipUnless(Path("ok_templates/21x9/29.png").is_file(), "Local dialog screenshots unavailable")
    def test_same_word_buttons_reject_other_pages_at_both_sizes(self):
        cases = {"6.png": ("Continue-Battle",),
                 "23.png": ("Leave-Battle-Confirm", "Continue-Battle-After-Sunk"),
                 "29.png": ("Confirm-Container",), "2.png": ()}
        names = ("Continue-Battle", "Leave-Battle-Confirm", "Continue-Battle-After-Sunk", "Confirm-Container")
        for filename, accepted in cases.items():
            source = make_bottom_right_black(cv2.imread(str(Path("ok_templates/21x9") / filename)))
            for scale in (1, .5):
                frame = source if scale == 1 else cv2.resize(source, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                self.bind_frame(frame)
                for name in names:
                    with self.subTest(page=filename, scale=scale, name=name):
                        self.assertEqual(name in accepted, self.task.find_one(name) is not None)
        # 港口顶部也写着“联合作战”，不能误判为模式选择页。
        self.bind_frame(make_bottom_right_black(cv2.imread("ok_templates/21x9/2.png")))
        self.assertIsNone(self.task.find_one("PVE-Battle"))
        self.assertEqual("main", self.task._detect_scene(refresh=False))


if __name__ == "__main__":
    unittest.main()
