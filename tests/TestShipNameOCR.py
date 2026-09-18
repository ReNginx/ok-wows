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
        ship = search_box("Pick-First-Ship" if in_port else "Libertad-Nameplate", self.executor.frame)

        def recognize(*, box, **kwargs):
            if (box.x, box.y, box.width, box.height) == (port.x, port.y, port.width, port.height):
                return [Box(port.x + 80, port.y + 25, 140, 40, .99, "加入战斗")] if in_port else []
            return [Box(ship.x + 40, ship.y + 25, 120, 25, .99, text)] if box.x <= ship.x + 40 < box.x + box.width else []
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
            responses = iter([[[[polygon, ("加入战斗", .99)]]] if name == "Pick-First-Ship" else [[]],
                              [[[polygon, ("自由", .99)]]]])
            engine.ocr.side_effect = lambda image, **kwargs: next(responses, [[]])
            self.executor.ocr_lib.side_effect = lambda lib="default": engine
            with self.subTest(name=name), patch.object(cv2, "resize", side_effect=AssertionError("No image resize")), \
                    patch.object(self.task, "ocr", wraps=self.task.ocr) as ocr:
                self.assertIsNotNone(self.task.find_one(name, target_height=480))
            self.assertGreaterEqual(engine.ocr.call_count, 2)
            for engine_call, ocr_call in zip(engine.ocr.call_args_list, ocr.call_args_list):
                region = ocr_call.kwargs["box"]
                crop = engine_call.args[0]
                self.assertEqual((region.height, region.width, 3), crop.shape)
                self.assertLessEqual(max(crop.shape[:2]), 960)
                self.assertTrue(np.shares_memory(frame, crop))
                np.testing.assert_array_equal(frame[region.y:region.y + region.height, region.x:region.x + region.width], crop)
            self.assertTrue(all(call.kwargs["target_height"] == 0 for call in ocr.call_args_list))

    def test_battle_nameplate_accepts_logged_tier_icon_noise_but_port_does_not(self):
        self.task.config["Ship Name"] = "瓦尔帕莱索"
        port = search_box("Join-Battle", self.executor.frame)
        nameplate = search_box("Libertad-Nameplate", self.executor.frame)
        for confidence in (.87, .88, .89, .91):  # 直接复现最近两场等待结束时的 OCR 文本及置信度。
            def recognize(*, box, **kwargs):
                if box.y == port.y:
                    return []
                return [Box(nameplate.x + 20, nameplate.y + 30, 220, 30, confidence, "VIX瓦尔帕莱索")]
            with self.subTest(confidence=confidence), patch.object(self.task, "ocr", side_effect=recognize), \
                    patch.object(self.task, "get_feature_by_name", return_value=object()), \
                    patch.object(MyBaseTask, "find_one", return_value=None):
                self.assertEqual("battle", self.task._detect_battle_view())
        with patch.object(self.task, "ocr", side_effect=self.fake_ocr("VIX瓦尔帕莱索", True)):
            self.assertIsNone(self.task.find_one("Pick-First-Ship"))

    def test_battle_substring_matching_requires_nonempty_complete_ship_name(self):
        for text in ("VIX瓦尔帕莱索", "Ｖ IX 瓦尔帕莱索", "IX瓦尔帕莱索", "瓦尔帕莱索",
                     "VIX瓦尔帕莱索B", "ABCIX瓦尔帕莱索", "瓦尔帕莱索85500/85500"):
            self.assertTrue(matches_ship_name(text, "瓦尔帕莱索", allow_substring=True), text)
        for text in ("VIX瓦尔帕莱", "VIX大和", ""):
            self.assertFalse(matches_ship_name(text, "瓦尔帕莱索", allow_substring=True), text)
        for wanted in ("", " ", "!?"):
            self.assertFalse(matches_ship_name("VIX瓦尔帕莱索", wanted, allow_substring=True))
        self.assertFalse(matches_ship_name("VIX瓦尔帕莱索", "瓦尔帕莱索"))

    def test_battle_nameplate_accepts_logged_health_suffix_but_port_does_not(self):
        self.task.config["Ship Name"] = "阿达尔伯特亲王"
        for text in ("X阿达尔伯特亲王 63", "X 阿达尔伯特亲王63 900/63 900"):
            with self.subTest(text=text), \
                    patch.object(self.task, "ocr", side_effect=self.fake_ocr(text, False)), \
                    patch.object(self.task, "get_feature_by_name", return_value=object()), \
                    patch.object(MyBaseTask, "find_one", return_value=None):
                self.assertEqual("battle", self.task._detect_battle_view())
            with patch.object(self.task, "ocr", side_effect=self.fake_ocr(text, True)):
                self.assertIsNone(self.task.find_one("Pick-First-Ship"))

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

    def test_port_covers_bottom_thirty_percent_and_battle_stays_local(self):
        for width, height in ((5120, 2160), (2560, 1600), (1920, 1080)):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            region = search_box("Pick-First-Ship", frame)
            self.assertEqual((0, round(height * .7), width, height - round(height * .7)),
                             (region.x, region.y, region.width, region.height))
            original = annotated_box("Libertad-Nameplate", frame)
            expanded = search_box("Libertad-Nameplate", frame)
            if original is None:
                self.assertIsNone(expanded)
                continue
            self.assertGreater(expanded.width, original.width)
            self.assertGreater(expanded.height, original.height)
            self.assertLess(expanded.width, width * .2)

    def test_port_finds_far_right_and_deduplicates_overlapping_tiles(self):
        frame = self.executor.frame
        self.task.config["Ship Name"] = "瓦尔帕莱索"
        for left in (760, 4800):
            target = Box(left, 2020, 140, 30, .99, "瓦尔帕莱索")
            def recognize(*, box, **kwargs):
                if box.y == 0:
                    return [Box(2450, 30, 150, 30, .99, "加入战斗")]
                return [target] if box.x <= left and left + 140 <= box.x + box.width else []
            with self.subTest(left=left), patch.object(self.task, "ocr", side_effect=recognize) as ocr:
                match = self.task.find_one("Pick-First-Ship")
                self.assertIsNotNone(match)
                self.assertEqual(left, match.x)
                tiles = [call.kwargs["box"] for call in ocr.call_args_list if call.kwargs["box"].y > 0]
                self.assertEqual(0, tiles[0].x)
                self.assertEqual(frame.shape[1], tiles[-1].x + tiles[-1].width)
                self.assertTrue(all(b.y == 1512 and b.height == 648 for b in tiles))
                self.assertTrue(all(a.x + a.width > b.x for a, b in zip(tiles, tiles[1:])))

    def test_distinct_same_name_cards_are_still_ambiguous(self):
        def recognize(*, box, **kwargs):
            if box.y == 0:
                return [Box(2450, 30, 150, 30, .99, "加入战斗")]
            return [Box(x, 1800, 90, 30, .99, "自由") for x in (300, 4100)
                    if box.x <= x and x + 90 <= box.x + box.width]
        with patch.object(self.task, "ocr", side_effect=recognize):
            self.assertIsNone(self.task.find_one("Pick-First-Ship"))

    @unittest.skipUnless(Path("logs/task_failures/2026-09-13/18-00-31-844564_Auto PVE Battle_418886e3.png").is_file(),
                         "Valparaiso failure screenshot unavailable")
    def test_valparaiso_failure_frame_is_recognized_at_native_size(self):
        frame = cv2.imread("logs/task_failures/2026-09-13/18-00-31-844564_Auto PVE Battle_418886e3.png")
        self.executor.frame = frame
        self.task.config["Ship Name"] = "瓦尔帕莱索"
        bind_ocr(self.executor)
        match = self.task.find_one("Pick-First-Ship")
        self.assertIsNotNone(match)
        self.assertGreaterEqual(match.confidence, .8)
        self.assertTrue(250 <= match.x <= 280)
        self.assertTrue(1810 <= match.y <= 1840)


if __name__ == "__main__":
    unittest.main()
