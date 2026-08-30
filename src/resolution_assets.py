import os

from ok.feature.FeatureSet import FeatureSet
from ok.task.TaskExecutor import TaskExecutor
from ok.util.file import get_path_relative_to_exe
from ok.util.window import ratio_text_to_number

ULTRAWIDE_RATIO = "21:9"
TALL_RATIO = "16:10"
WIDE_RATIO = "16:9"

ASSET_PACKS = (
    {
        "ratio": ULTRAWIDE_RATIO,
        "value": ratio_text_to_number(ULTRAWIDE_RATIO),
        "aliases": (ratio_text_to_number("64:27"),),
        "coco": os.path.join("assets", "21x9", "coco_annotations.json"),
        "assets": os.path.join("assets", "21x9"),
        "templates": os.path.join("ok_templates", "21x9"),
    },
    {
        "ratio": TALL_RATIO,
        "value": ratio_text_to_number(TALL_RATIO),
        "aliases": (),
        "coco": os.path.join("assets", "16x10", "coco_annotations.json"),
        "assets": os.path.join("assets", "16x10"),
        "templates": os.path.join("ok_templates", "16x10"),
    },
    {
        "ratio": WIDE_RATIO,
        "value": ratio_text_to_number(WIDE_RATIO),
        "aliases": (),
        "coco": os.path.join("assets", "16x9", "coco_annotations.json"),
        "assets": os.path.join("assets", "16x9"),
        "templates": os.path.join("ok_templates", "16x9"),
    },
)

_size_override = None
_pack_override = None


def pack_match_values(pack):
    return (pack["value"],) + pack["aliases"]


def pack_for_ratio(ratio):
    for pack in ASSET_PACKS:
        if pack["ratio"] == ratio:
            return pack
    return ASSET_PACKS[0]


def pack_for_size(width, height):
    if height <= 0:
        return ASSET_PACKS[0]
    actual = width / height
    return min(ASSET_PACKS, key=lambda pack: min(abs(actual - value) for value in pack_match_values(pack)))


def matched_ratio_value(width, height):
    actual = width / height if height else 0
    return min(pack_match_values(pack_for_size(width, height)), key=lambda value: abs(actual - value))


def coco_json_for_size(width, height):
    return pack_for_size(width, height)["coco"]


def template_folder_for_size(width, height):
    return pack_for_size(width, height)["templates"]


def asset_folder_for_size(width, height):
    return pack_for_size(width, height)["assets"]


def set_size_override(width, height):
    global _size_override
    _size_override = None if width is None or height is None else (width, height)


def set_pack_override(ratio):
    global _pack_override
    _pack_override = ratio


def current_frame_size():
    if _size_override is not None:
        return _size_override
    from ok import og
    method = getattr(getattr(og, "device_manager", None), "capture_method", None)
    if method is None:
        return 0, 0
    width = getattr(method, "width", 0) or 0
    height = getattr(method, "height", 0) or 0
    return width, height


def current_pack():
    if _pack_override:
        return pack_for_ratio(_pack_override)
    return pack_for_size(*current_frame_size())


def current_template_folder():
    return current_pack()["templates"]


def pack_for_template_folder(template_folder):
    abs_folder = os.path.normpath(os.path.abspath(template_folder))
    for pack in ASSET_PACKS:
        pack_folder = os.path.normpath(os.path.abspath(os.path.join(os.getcwd(), pack["templates"])))
        if abs_folder == pack_folder:
            return pack
    return ASSET_PACKS[0]


def redirect_asset_target(target_folder, image_folder):
    abs_target = os.path.normpath(os.path.abspath(target_folder))
    if abs_target != os.path.normpath(os.path.abspath("assets")):
        return target_folder
    return os.path.abspath(pack_for_template_folder(image_folder)["assets"])


def ratio_is_supported(width, height):
    if height <= 0:
        return False
    actual = width / height
    return any(abs(actual - value) <= 0.01 * value for pack in ASSET_PACKS for value in pack_match_values(pack))


def apply_feature_pack(feature_set, width, height):
    coco_json = get_path_relative_to_exe(coco_json_for_size(width, height))
    if feature_set.coco_json == coco_json or not os.path.isfile(coco_json):
        return False
    feature_set.coco_json = coco_json
    feature_set.width = 0
    feature_set.height = 0
    feature_set.feature_dict = {}
    feature_set.box_dict = {}
    feature_set._processed_images = set()
    return True


_original_check_size = FeatureSet.check_size
_original_check_frame_and_resolution = TaskExecutor.check_frame_and_resolution


def _check_size(self, frame):
    if frame is not None and getattr(frame, "shape", None) is not None:
        height, width = frame.shape[:2]
        apply_feature_pack(self, width, height)
        from ok import og
        if getattr(og, "device_manager", None) is not None:
            og.device_manager.supported_ratio = matched_ratio_value(width, height)
    return _original_check_size(self, frame)


def _check_frame_and_resolution(self, supported_ratio, min_size, time_out=8.0):
    supported, resolution = _original_check_frame_and_resolution(self, supported_ratio, min_size, time_out=time_out)
    if supported or self.method is None:
        return supported, resolution
    width = self.method.width
    height = self.method.height
    if not ratio_is_supported(width, height):
        return supported, resolution
    if min_size is not None and (width < min_size[0] or height < min_size[1]):
        return False, resolution
    return True, resolution


FeatureSet.check_size = _check_size
TaskExecutor.check_frame_and_resolution = _check_frame_and_resolution


def _install_dev_tool_patches():
    from ok.core.template_store import CocoTemplateStore
    from ok.feature import FeatureSet as feature_set_mod
    from ok.ui.qt.tasks import TemplateTab as template_tab
    from ok.ui.web.app import WebRuntime

    def ensure_template_folder():
        folder = os.path.join(os.getcwd(), current_template_folder())
        os.makedirs(folder, exist_ok=True)
        return str(CocoTemplateStore(folder).folder)

    def load_coco():
        return CocoTemplateStore(ensure_template_folder()).load()

    def save_coco(coco_data):
        return CocoTemplateStore(ensure_template_folder()).save(coco_data)

    def get_image_files():
        store = CocoTemplateStore(ensure_template_folder())
        return [str(item["path"]) for item in store.list_images()]

    def get_coco_path():
        return os.path.join(ensure_template_folder(), "coco_annotations.json")

    template_tab.ensure_template_folder = ensure_template_folder
    template_tab.load_coco = load_coco
    template_tab.save_coco = save_coco
    template_tab.get_image_files = get_image_files
    template_tab.get_coco_path = get_coco_path

    _original_init_ui = template_tab.TemplateTab.init_ui
    _original_load_grid = template_tab.TemplateTab.load_initial_grid

    def load_initial_grid(self):
        self._resolution_template_folder = os.path.abspath(ensure_template_folder())
        return _original_load_grid(self)

    def _select_ratio(self, ratio):
        pack = pack_for_ratio(ratio)
        folder = os.path.abspath(os.path.join(os.getcwd(), pack["templates"]))
        if _pack_override == pack["ratio"] and getattr(self, "_resolution_template_folder", None) == folder:
            return
        set_pack_override(pack["ratio"])
        if getattr(self, "ratio_btn", None) is not None:
            self.ratio_btn.setText(pack["ratio"])
        os.makedirs(folder, exist_ok=True)
        self._resolution_template_folder = folder
        self.coco_data = CocoTemplateStore(folder).load()
        self.selected_image = None
        self.load_initial_grid()

    def init_ui(self):
        from qfluentwidgets import Action, DropDownPushButton, FluentIcon, RoundMenu

        _original_init_ui(self)
        if _pack_override is None:
            set_pack_override(pack_for_size(*current_frame_size())["ratio"])
        ratio_btn = DropDownPushButton(FluentIcon.PHOTO, _pack_override, self)
        ratio_menu = RoundMenu(parent=ratio_btn)
        for pack in ASSET_PACKS:
            action = Action(pack["ratio"])
            action.triggered.connect(lambda checked=False, ratio=pack["ratio"]: self._select_ratio(ratio))
            ratio_menu.addAction(action)
        ratio_btn.setMenu(ratio_menu)
        self.ratio_btn = ratio_btn
        toolbar = self.layout().itemAt(0).layout()
        toolbar.insertWidget(1, ratio_btn)

    template_tab.TemplateTab.init_ui = init_ui
    template_tab.TemplateTab._select_ratio = _select_ratio
    template_tab.TemplateTab.load_initial_grid = load_initial_grid

    _original_compress = feature_set_mod.compress_copy_coco

    def compress_copy_coco(coco_json, target_folder, image_folder, generate_label_enmu=None):
        target_folder = redirect_asset_target(target_folder, image_folder)
        return _original_compress(coco_json, target_folder, image_folder, generate_label_enmu)

    feature_set_mod.compress_copy_coco = compress_copy_coco

    def template_store(self):
        folder = os.path.join(os.getcwd(), current_template_folder())
        store = getattr(self, "_template_store", None)
        if store is None or os.path.normpath(str(store.folder)) != os.path.normpath(os.path.abspath(folder)):
            self._template_store = CocoTemplateStore(folder)
        return self._template_store

    _original_capture_template = WebRuntime.capture_template

    def capture_template(self):
        method = getattr(self.ok.device_manager, "capture_method", None)
        frame = method.get_frame() if method is not None else None
        if frame is not None:
            height, width = frame.shape[:2]
            set_size_override(width, height)
            self._template_store = None
        result = _original_capture_template(self)
        set_size_override(None)
        return result

    WebRuntime.template_store = property(template_store)
    WebRuntime.capture_template = capture_template


_install_dev_tool_patches()
