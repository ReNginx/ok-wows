"""验证可配置船名、港口/战斗隔离和原始像素 OCR 输入。"""

import gettext
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from ok import Box

from src.tasks.AutoPveBattleTask import AutoPveBattleTask
from src.tasks.MyBaseTask import MyBaseTask
from src.tasks.ScreenRecognitionTestTask import ScreenRecognitionTestTask
from src.tasks.feature_ocr import SHIP_NAME_FEATURES, annotated_box, matches_ship_name, search_box
from tests.ocr_support import bind_ocr


class TestShipNameOCR(unittest.TestCase):
    def setUp(self):
        self.executor = MagicMock()
        self.executor.scene = None
        self.executor.frame = np.zeros((2160, 5120, 3), dtype=np.uint8)
        self.task = AutoPveBattleTask(self.executor, None)
        self.task.config = dict(self.task.default_config)

    def fake_ocr(self, text, in_port):
        port = search_box("Join-Battle", self.executor.frame)

        def recognize(*, box, **kwargs):
            if (box.x, box.y, box.width, box.height) == (port.x, port.y, port.width, port.height):
                return [Box(port.x + 80, port.y + 25, 140, 40, .99, "加入战斗")] if in_port else []
            return [Box(box.x + 40, box.y + 25, 120, 25, .99, text)]
        return recognize

    def test_ui_default_validation_and_diagnostic_option(self):
        self.assertEqual("自由", self.task.default_config["Ship Name"])
        self.assertEqual({"type": "line_edit"}, self.task.config_type["Ship Name"])
        diagnostic = ScreenRecognitionTestTask(self.executor, None)
        self.assertEqual("自由", diagnostic.default_config["Ship Name"])
        self.assertEqual({"type": "line_edit"}, diagnostic.config_type["Ship Name"])
        for value in ("", "   ", None, 12, "!?", "自由\n大和"):
            self.assertIsNotNone(self.task.validate_config("Ship Name", value))
        for value in ("自由", "  大和  ", "Kremlin", "G. KURFÜRST"):
            self.assertIsNone(self.task.validate_config("Ship Name", value))
        with Path("i18n/zh_CN/LC_MESSAGES/ok.mo").open("rb") as stream:
            translations = gettext.GNUTranslations(stream)
        self.assertEqual("舰船名称", translations.gettext("Ship Name"))
        self.assertNotEqual("Ship Name must be a non-empty single-line name.",
                            translations.gettext("Ship Name must be a non-empty single-line name."))

    def test_both_features_follow_edited_name_and_never_use_template(self):
        for name in SHIP_NAME_FEATURES:
            with self.subTest(name=name), \
                    patch.object(self.task, "ocr", side_effect=self.fake_ocr("X 大和", name == "Pick-First-Ship")), \
                    patch.object(MyBaseTask, "find_one", side_effect=AssertionError("No template fallback")):
                self.assertIsNone(self.task.find_one(name))
                self.task.config["Ship Name"] = " 大和 "
                match = self.task.find_one(name)
                self.assertIsNotNone(match)
                self.assertEqual(name, match.name)
                self.task.config["Ship Name"] = "蒙大拿"
                self.assertIsNone(self.task.find_one(name))
                self.task.config["Ship Name"] = "自由"

    def test_empty_name_does_not_fall_back_but_old_config_does(self):
        for name in SHIP_NAME_FEATURES:
            with self.subTest(name=name), patch.object(self.task, "ocr", side_effect=self.fake_ocr("自由", name == "Pick-First-Ship")):
                for value in ("", " ", None, 1):
                    self.task.config["Ship Name"] = value
                    self.assertIsNone(self.task.find_one(name))
                self.task.config.pop("Ship Name")
                self.assertIsNotNone(self.task.find_one(name))

    def test_ship_matching_does_not_accept_other_ship_with_same_substring(self):
        for text in ("自由", "X 自由", "Ｘ 自由", "自由！"):
            self.assertTrue(matches_ship_name(text, "自由"), text)
        for text in ("自由之翼", "自由 B", "新自由", "自由85500", "大和"):
            self.assertFalse(matches_ship_name(text, "自由"), text)
        self.assertTrue(matches_ship_name("X G. KURFÜRST", "G. Kurfürst"))

    def test_engine_receives_original_crop_without_resize(self):
        frame = self.executor.frame
        bind_ocr(self.executor)
        engine = MagicMock()
        polygon = [[15, 10], [75, 10], [75, 35], [15, 35]]
        for name in SHIP_NAME_FEATURES:
            engine.reset_mock()
            engine.ocr.side_effect = [[[[polygon, ("加入战斗", .99)]]] if name == "Pick-First-Ship" else [[]],
                                      [[[polygon, ("自由", .99)]]]]
            self.executor.ocr_lib.side_effect = lambda lib="default": engine
            with self.subTest(name=name), patch.object(cv2, "resize", side_effect=AssertionError("No image resize")), \
                    patch.object(self.task, "ocr", wraps=self.task.ocr) as ocr:
                self.assertIsNotNone(self.task.find_one(name, target_height=480))
            self.assertEqual(2, engine.ocr.call_count)
            region = search_box(name, frame)
            crop = engine.ocr.call_args.args[0]
            self.assertEqual((region.height, region.width, 3), crop.shape)
            self.assertTrue(np.shares_memory(frame, crop))
            np.testing.assert_array_equal(frame[region.y:region.y + region.height, region.x:region.x + region.width], crop)
            self.assertTrue(all(call.kwargs["target_height"] == 0 for call in ocr.call_args_list))

    @unittest.skipUnless(Path("ok_templates/21x9/28.png").is_file(), "Native ship screenshots unavailable")
    def test_native_screens_port_and_battle_are_not_confused(self):
        bind_ocr(self.executor)
        for filename, expected in (("2.png", "Pick-First-Ship"), ("28.png", "Pick-First-Ship"),
                                   ("14.png", "Libertad-Nameplate"), ("15.png", "Libertad-Nameplate"),
                                   ("16.png", "Libertad-Nameplate")):
            frame = cv2.imread(str(Path("ok_templates/21x9") / filename))  # 直接使用原始截图，不生成缩放版本。
            self.executor.frame = frame
            for name in SHIP_NAME_FEATURES:
                with self.subTest(image=filename, name=name):
                    match = self.task.find_one(name)
                    self.assertEqual(name == expected, match is not None)
            self.task.config["Ship Name"] = "不存在的舰船名称"
            self.assertIsNone(self.task.find_one(expected))
            self.task.config["Ship Name"] = "自由"

    def test_both_search_regions_are_larger_and_stay_local(self):
        for name in SHIP_NAME_FEATURES:
            original = annotated_box(name, self.executor.frame)
            expanded = search_box(name, self.executor.frame)
            self.assertGreater(expanded.width, original.width)
            self.assertGreater(expanded.height, original.height)
            self.assertLess(expanded.width, self.executor.frame.shape[1] * .2)
            self.assertGreaterEqual(expanded.x, 0)
            self.assertGreaterEqual(expanded.y, 0)


if __name__ == "__main__":
    unittest.main()
