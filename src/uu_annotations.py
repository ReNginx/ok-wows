"""COCO image/category/bbox data plus declarative UU OCR rules."""

from functools import lru_cache
import json
import math
from pathlib import Path

from src.uu_recognition import normalize, text_boxes


DEFAULT_ANNOTATIONS = Path(__file__).resolve().parents[1] / 'assets/uu/coco_annotations.json'


class UUAnnotations:
    def __init__(self, path=DEFAULT_ANNOTATIONS):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding='utf-8'))
        self.rules = data['uu_ocr']
        if self.rules['version'] != 1:
            raise ValueError('不支持的 UU 标注版本。')
        references = [item for item in data['images'] if item['id'] == self.rules['reference_image_id']]
        if len(references) != 1:
            raise ValueError('UU 标注必须指定唯一参考截图。')
        self.image = references[0]
        self.width, self.height = self.image['width'], self.image['height']
        if self.width <= 0 or self.height <= 0:
            raise ValueError('UU 参考截图尺寸必须大于零。')
        categories = {item['id']: item['name'] for item in data['categories']}
        if len(categories) != len(data['categories']) or len(set(categories.values())) != len(categories):
            raise ValueError('UU 标注类别名称和 ID 不能重复。')
        self.regions = {}
        reference_ids = {self.rules['reference_image_id'],
                         self.rules.get('detail_reference_image_id', self.rules['reference_image_id'])}
        region_images = {item['id']: item for item in data['images'] if item['id'] in reference_ids}
        if set(region_images) != reference_ids:
            raise ValueError('UU 标注引用了不存在的参考截图。')
        for item in data['annotations']:
            if item['image_id'] not in region_images:
                continue
            source = region_images[item['image_id']]
            source_width, source_height = source['width'], source['height']
            name = categories[item['category_id']]
            x, y, w, h = item['bbox']
            if name in self.regions:
                raise ValueError(f'UU 区域名称重复：{name}')
            if not all(math.isfinite(v) for v in (x, y, w, h)) or not (
                    0 <= x < source_width and 0 <= y < source_height and
                    w > 0 and h > 0 and x + w <= source_width and y + h <= source_height):
                raise ValueError(f'UU 区域超出参考截图：{name}')
            self.regions[name] = (x * self.width / source_width, y * self.height / source_height,
                                  w * self.width / source_width, h * self.height / source_height)
        self.min_confidence = self.rules['min_confidence']
        self.aspect_tolerance = self.rules['aspect_ratio_tolerance']
        if not 0 < self.min_confidence <= 1 or not 0 <= self.aspect_tolerance <= 0.2:
            raise ValueError('UU OCR 置信度或比例容差无效。')
        self.cards = self.rules['home_cards']
        self.detail = self.rules['detail']
        references = [self.rules['home_titles'], self.rules['navigation_region']]
        for region in [*self.cards, self.detail]:
            references.extend((region['title'], region['content']))
        references.extend(card['click_region'] for card in self.cards)
        if not self.cards or any(name not in self.regions for name in references):
            raise ValueError('UU OCR 规则引用了不存在的标注区域。')
        for card in self.cards:
            x, y, w, h = self.regions[card['click_region']]
            title_x, title_y, title_w, _ = self.regions[card['title']]
            if y + h > title_y or not title_x <= x + w / 2 < title_x + title_w:
                raise ValueError('UU 点击区域必须位于对应游戏名称上方。')
        self.texts = {}
        for role in ('accelerate', 'ready', 'blocked', 'navigation'):
            words = self.rules['texts'][role]
            if not words or not all(isinstance(word, str) and word.strip() for word in words):
                raise ValueError(f'UU OCR 匹配文字无效：{role}')
            self.texts[role] = {normalize(word) for word in words}
        if self.texts['accelerate'] & self.texts['ready']:
            raise ValueError('UU 加速按钮与成功状态不能使用相同文字。')

    def valid_size(self, width, height):
        return (width > 0 and height > 0 and
                abs((width / height) / (self.width / self.height) - 1) <= self.aspect_tolerance)

    def rect(self, name, width, height):
        x, y, w, h = self.regions[name]
        return (round(x * width / self.width), round(y * height / self.height),
                round((x + w) * width / self.width), round((y + h) * height / self.height))

    def contains(self, name, box, width, height):
        left, top, right, bottom = self.rect(name, width, height)
        x, y = box.center
        return left <= x < right and top <= y < bottom

    def game_region(self, boxes, game_name, width, height):
        games = [b for b in boxes if normalize(b.text) == normalize(game_name)]
        if len(games) != 1:
            return None
        matches = [r for r in [*self.cards, self.detail]
                   if self.contains(r['title'], games[0], width, height)]
        return matches[0] if len(matches) == 1 else None

    def recognize(self, frame, engine, game_name):
        """OCR the title strip first, then its card, restoring crop offsets."""
        height, width = frame.shape[:2]
        if not self.valid_size(width, height):
            raise ValueError('UU 窗口比例与 JSON 标注不符，请更新 assets/uu/coco_annotations.json。')

        def read(name):
            left, top, right, bottom = self.rect(name, width, height)
            return text_boxes(engine.ocr(frame[top:bottom, left:right], cls=False),
                              self.min_confidence, (left, top))

        boxes = read(self.rules['home_titles'])
        game = self.game_region(boxes, game_name, width, height)
        if game:
            return boxes + read(game['content'])
        # The calibrated detail title identifies the game; the broad content crop
        # also covers visible login/acceleration errors, without using latency.
        boxes.extend(read(self.detail['title']))
        boxes.extend(read(self.detail['content']))
        unique = []
        for box in boxes:
            if not any(normalize(box.text) == normalize(other.text) and
                       abs(box.center[0] - other.center[0]) < width * 0.01 and
                       abs(box.center[1] - other.center[1]) < height * 0.01 for other in unique):
                unique.append(box)
        return unique


@lru_cache(maxsize=1)
def default_annotations():
    return UUAnnotations()
