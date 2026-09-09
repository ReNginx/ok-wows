"""Pure OCR decisions: every click must be grounded in the current UU frame."""

from dataclasses import dataclass
import re


def normalize(text):
    return re.sub(r'\s+', '', text).casefold()


@dataclass(frozen=True)
class TextBox:
    text: str
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center(self):
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)


@dataclass(frozen=True)
class Decision:
    action: str
    point: tuple | None = None


def text_boxes(result, min_confidence=0.65, offset=(0, 0)):
    boxes = []
    for polygon, (text, confidence) in (result[0] if result else []) or []:
        if confidence >= min_confidence:
            xs, ys = zip(*polygon)
            boxes.append(TextBox(text, min(xs) + offset[0], min(ys) + offset[1],
                                 max(xs) + offset[0], max(ys) + offset[1]))
    return boxes


def decide(boxes, game_name, width, height, annotations=None):
    """Use OCR to identify the game, then click its annotated icon above the title."""
    from src.uu_annotations import default_annotations

    annotations = annotations or default_annotations()
    if not annotations.valid_size(width, height):
        return Decision('unsupported')
    labels = {normalize(b.text) for b in boxes}
    if labels & annotations.texts['blocked']:
        return Decision('blocked')
    game = annotations.game_region(boxes, game_name, width, height)
    if game is None:
        return Decision('missing')

    def matches(role):
        return [b for b in boxes if normalize(b.text) in annotations.texts[role]
                and annotations.contains(game['content'], b, width, height)]

    active, buttons = matches('ready'), matches('accelerate')
    if len(active) == 1 and not buttons:
        return Decision('ready')
    if not active and len(buttons) <= 1 and game in annotations.cards:
        left, top, right, bottom = annotations.rect(game['click_region'], width, height)
        return Decision('click', ((left + right) / 2, (top + bottom) / 2))
    # Detail pages have no verified icon annotation; never fall back to text clicks.
    return Decision('wait')


def navigation_target(boxes, width, height, annotations=None):
    from src.uu_annotations import default_annotations

    annotations = annotations or default_annotations()
    if not annotations.valid_size(width, height):
        return None
    matches = [b for b in boxes
               if any(normalize(b.text).startswith(word) for word in annotations.texts['navigation'])
               and annotations.contains(annotations.rules['navigation_region'], b, width, height)]
    return matches[0].center if len(matches) == 1 else None
