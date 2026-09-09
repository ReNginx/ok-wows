import json
from dataclasses import replace
from pathlib import Path
import unittest

from src.uu_recognition import TextBox, decide, text_boxes


def box(text, x, y):
    return TextBox(text, x - 40, y - 10, x + 40, y + 10)


class TestUURecognition(unittest.TestCase):
    def decide(self, boxes):
        return decide(boxes, '战舰世界国际服', 1000, 688)

    def test_real_home_ocr_targets_wows_card(self):
        fixture = Path(__file__).parent / 'fixtures/uu/home.json'
        boxes = [TextBox(**b) for b in json.loads(fixture.read_text(encoding='utf-8'))]
        action = self.decide(boxes)
        self.assertEqual('click', action.action)
        self.assertEqual((617, 254), action.point)

    def test_only_clicks_acceleration_in_correct_card(self):
        boxes = [box('战舰世界国际服', 616, 440), box('立即加速', 616, 330), box('立即加速', 383, 330)]
        self.assertEqual((617, 254), self.decide(boxes).point)

    def test_another_games_stop_button_does_not_mean_ready(self):
        boxes = [box('战舰世界国际服', 616, 440), box('停止加速', 383, 330)]
        self.assertEqual('click', self.decide(boxes).action)

    def test_start_game_button_is_not_acceleration_confirmation(self):
        boxes = [box('战舰世界国际服', 157, 296), box('启动游戏', 220, 346)]
        self.assertEqual('wait', self.decide(boxes).action)

    def test_detail_stop_button_confirms_success(self):
        boxes = [box('战舰世界国际服', 157, 296), box('停止加速', 220, 346)]
        self.assertEqual('ready', self.decide(boxes).action)

    def test_different_game_or_server_never_clicks(self):
        boxes = [box('战舰世界国服', 157, 296), box('立即加速', 220, 346)]
        self.assertEqual('missing', self.decide(boxes).action)

    def test_multiple_buttons_are_ambiguous(self):
        boxes = [box('战舰世界国际服', 157, 296), box('加速', 700, 500), box('加速', 500, 500)]
        self.assertEqual('wait', self.decide(boxes).action)

    def test_explicit_failure_overrides_stop_button(self):
        boxes = [box('战舰世界国际服', 157, 296), box('停止加速', 220, 346), box('加速失败', 500, 300)]
        self.assertEqual('blocked', self.decide(boxes).action)

    def test_real_accelerated_page_ignores_latency_and_dynamic_status(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/uu/accelerated.json').read_text(encoding='utf-8'))
        boxes = [TextBox(**b) for b in fixture['boxes']]
        for scale in (1, 1 / 1.75):
            for latency in ('0 ms', '63 ms', '136 ms', '999 ms', '-- ms'):
                with self.subTest(scale=scale, latency=latency):
                    changed = [replace(b, text=latency) if b.text == '136' else b for b in boxes]
                    scaled = [TextBox(b.text, b.left * scale, b.top * scale,
                                      b.right * scale, b.bottom * scale) for b in changed]
                    result = decide(scaled, '战舰世界国际服', round(fixture['width'] * scale),
                                    round(fixture['height'] * scale))
                    self.assertEqual('ready', result.action)
                    self.assertIsNone(result.point)
        stable = [b for b in boxes if b.text in {'战舰世界国际服', '停止加速'}]
        self.assertEqual('ready', decide(stable, '战舰世界国际服', fixture['width'], fixture['height']).action)
        without_stop = [b for b in boxes if b.text != '停止加速']
        self.assertEqual('wait', decide(without_stop, '战舰世界国际服', fixture['width'], fixture['height']).action)
        self.assertEqual('missing', decide(boxes, '战舰世界国服', fixture['width'], fixture['height']).action)

    def test_filters_low_confidence_text(self):
        polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
        self.assertEqual([], text_boxes([[[polygon, ('加速成功', 0.3)]]]))


if __name__ == '__main__':
    unittest.main()
