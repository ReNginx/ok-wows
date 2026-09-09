import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

from src.uu_annotations import DEFAULT_ANNOTATIONS, UUAnnotations
from src.uu_recognition import TextBox, decide, navigation_target


def ocr_result(text, left, top, right, bottom, confidence=0.99):
    return [[[[[left, top], [right, top], [right, bottom], [left, bottom]], (text, confidence)]]]


class TestUUAnnotations(unittest.TestCase):
    def setUp(self):
        self.annotations = UUAnnotations()
        self.game = TextBox('战舰世界国际服', 551, 432, 682, 453)
        self.button = TextBox('立即加速', 580, 310, 654, 336)

    def modified(self, change):
        data = json.loads(DEFAULT_ANNOTATIONS.read_text(encoding='utf-8'))
        change(data)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'coco_annotations.json'
            path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            return UUAnnotations(path)

    def test_ocr_uses_title_then_target_card_and_restores_offsets(self):
        engine = Mock()
        engine.ocr.side_effect = [
            ocr_result('战舰世界国际服', 521, 14, 652, 35),
            ocr_result('立即加速', 72, 216, 146, 242),
        ]
        frame = np.zeros((688, 1000, 3), dtype=np.uint8)
        boxes = self.annotations.recognize(frame, engine, '战舰世界国际服')
        self.assertEqual([self.game, self.button], boxes)
        self.assertEqual([(50, 940, 3), (320, 218, 3)],
                         [call.args[0].shape for call in engine.ocr.call_args_list])
        decision = decide(boxes, '战舰世界国际服', 1000, 688, self.annotations)
        self.assertEqual(('click', (617, 254)), (decision.action, decision.point))

    def test_scales_to_actual_175_percent_window(self):
        boxes = [TextBox(b.text, b.left * 1.75, b.top * 1.75, b.right * 1.75, b.bottom * 1.75)
                 for b in (self.game, self.button)]
        decision = decide(boxes, '战舰世界国际服', 1750, 1204, self.annotations)
        self.assertEqual('click', decision.action)
        self.assertEqual((1079.5, 444), decision.point)

    def test_follows_game_when_home_cards_are_reordered(self):
        game = TextBox(self.game.text, 310, 432, 460, 453)
        button = TextBox('立即加速', 340, 310, 420, 336)
        decision = decide([game, self.button, button], game.text, 1000, 688, self.annotations)
        self.assertEqual((383, 254), decision.point)

    def test_game_name_alone_selects_icon_without_acceleration_text(self):
        decision = decide([self.game], self.game.text, 1000, 688, self.annotations)
        self.assertEqual(('click', (617, 254)), (decision.action, decision.point))
        self.assertLess(decision.point[1], self.game.top)

    def test_custom_ready_words_still_prevent_repeated_icon_click(self):
        annotations = self.modified(lambda data: data['uu_ocr']['texts'].update(ready=['已连接']))
        ready = TextBox('已连接', 580, 310, 654, 336)
        self.assertEqual('ready', decide([self.game, ready], self.game.text, 1000, 688, annotations).action)

    def test_changed_json_icon_bbox_changes_click_center(self):
        annotations = self.modified(lambda data: data['annotations'][6].update(bbox=[508, 94, 218, 150]))
        self.assertEqual((617, 169), decide([self.game, self.button], self.game.text, 1000, 688, annotations).point)

    def test_confidence_threshold_comes_from_json(self):
        annotations = self.modified(lambda data: data['uu_ocr'].update(min_confidence=0.98))
        engine = Mock()
        engine.ocr.return_value = ocr_result('战舰世界国际服', 521, 14, 652, 35, 0.90)
        self.assertEqual([], annotations.recognize(np.zeros((688, 1000, 3), dtype=np.uint8), engine, self.game.text))

    def test_aspect_mismatch_fails_before_ocr(self):
        engine = Mock()
        with self.assertRaisesRegex(ValueError, '比例'):
            self.annotations.recognize(np.zeros((720, 1280, 3), dtype=np.uint8), engine, self.game.text)
        engine.ocr.assert_not_called()
        self.assertEqual('unsupported', decide([self.game, self.button], self.game.text, 1280, 720).action)

    def test_navigation_requires_annotated_region(self):
        outside = TextBox('我的游戏', 300, 220, 400, 250)
        inside = TextBox('我的游戏 (20)', 795, 517, 940, 550)
        self.assertIsNone(navigation_target([outside], 1000, 688))
        self.assertEqual(inside.center, navigation_target([outside, inside], 1000, 688))

    def test_rejects_invalid_regions_and_missing_references(self):
        for change in (
            lambda data: data['annotations'][0].update(bbox=[0, 0, 1001, 688]),
            lambda data: data['uu_ocr'].update(home_titles='missing'),
            lambda data: data['uu_ocr'].update(detail_reference_image_id=99),
            lambda data: data['categories'][1].update(name=data['categories'][0]['name']),
            lambda data: data['uu_ocr']['home_cards'][2].update(click_region='UU-Home-Title-3'),
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.modified(change)

    def test_conflicting_ready_and_start_text_never_clicks(self):
        ready = TextBox('停止加速', 580, 350, 654, 375)
        self.assertEqual('wait', decide([self.game, self.button, ready], self.game.text, 1000, 688).action)

    def test_detail_without_icon_annotation_never_clicks_button_text(self):
        game = TextBox(self.game.text, 85, 280, 230, 305)
        button = TextBox('立即加速', 700, 500, 780, 525)
        decision = decide([game, button], game.text, 1000, 688)
        self.assertEqual('wait', decision.action)
        self.assertIsNone(decision.point)


if __name__ == '__main__':
    unittest.main()
